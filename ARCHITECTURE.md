# DataModelerAgent — High-Level Architecture

**DataModelerAgent** is a Streamlit application that turns an unstructured **Business
Requirements Document (BRD, `.docx`)** into a formal **Conceptual Data Model (CDM)** and,
optionally, a **Logical Data Model (LDM)** with SQL DDL. It combines a local LLM (Ollama),
a knowledge graph (Neo4j Aura), a vector store (ChromaDB), and a rule engine (OWL/SHACL) to
extract entities, infer structure, and enforce dimensional-modeling conventions.

---

## 1. System Context

```mermaid
flowchart LR
    User([Data Modeler])
    BRD[/BRD .docx/]
    App[DataModelerAgent<br/>Streamlit App]
    Ollama[(Ollama<br/>Local LLM)]
    Neo4j[(Neo4j Aura<br/>Knowledge Graph)]
    Chroma[(ChromaDB<br/>Vector Store)]
    Out[/CDM + LDM<br/>Diagrams, SQL DDL, JSON-LD/]

    User -->|uploads| BRD --> App
    App -->|entity / relationship extraction| Ollama
    App -->|graph build & retrieval| Neo4j
    App -->|semantic concept & reference lookup| Chroma
    App -->|renders| Out --> User
```

| External service | Role | Configured in |
|---|---|---|
| **Ollama** (`localhost:11434`) | All LLM calls — domain extraction, entity/relationship detection, graph transform, LDM promotion, validation | [config.py](config.py), [agent/ollama_client.py](agent/ollama_client.py) |
| **Neo4j Aura** | Knowledge graph built from BRD chunks; queried for relationship context (GraphRAG) | [config.py](config.py), [agent/step2_graphrag.py](agent/step2_graphrag.py) |
| **ChromaDB** (`./chroma_db`) | Vector store with two collections: `ontology_concepts` (schema.org) and `oracle_retail_reference` | [ontology/seeder.py](ontology/seeder.py), [agent/ldm_seeder.py](agent/ldm_seeder.py) |

---

## 2. Layered Architecture

```mermaid
flowchart TB
    subgraph UI["UI Layer (Streamlit) — app.py"]
        SB[sidebar.py<br/>config] 
        UP[upload.py<br/>file + mode]
        PU[pipeline_ui.py<br/>progress]
        OUT[output.py / ldm_output.py / graph_view.py<br/>results]
    end

    subgraph ORCH["Orchestration Layer"]
        CDMP[pipeline_agent.py<br/>8-step CDM pipeline + cache]
        LDMP[ldm_pipeline.py<br/>3-step LDM pipeline + repair]
    end

    subgraph STEPS["Pipeline Steps"]
        S1[step1_parser] --> S1B[step1b_ontology_builder]
        S1B --> S2G[step2_graphrag]
        S2G --> S2E[step2_entities]
        S2E --> S3[step3_relationships]
        S3 --> S4[step4_ontology]
        S4 --> S4B[step4b_owl_rules]
        S4B --> CDM[cdm_builder]
        CDM --> PROM[step_ldm_promote]
        PROM --> VAL[ldm_validation_agent]
        VAL --> DDL[step_ldm_ddl]
    end

    subgraph SUPPORT["Support & Utilities"]
        OLL[ollama_client]
        RS[result_store]
        CONV[ldm_conventions]
        SEED[ldm_seeder]
        SKL[skill_loader]
    end

    subgraph KNOW["Knowledge & Rules"]
        RULES[ontology/rules.py + filter_inference.py<br/>OWL R1–R6 + SHACL]
        ONTSEED[ontology/seeder.py<br/>schema.org]
        SKILL[skills/SKILL.md<br/>entity guardrails]
        NAMES[skills/LDM_NAMING_CONVENTIONS.md<br/>table naming]
    end

    subgraph EXT["External Services"]
        E_OLL[(Ollama)]
        E_NEO[(Neo4j Aura)]
        E_CHR[(ChromaDB)]
    end

    UI --> ORCH --> STEPS
    STEPS --> SUPPORT
    STEPS --> KNOW
    SUPPORT --> EXT
    KNOW --> EXT
```

**Separation of concerns:** the UI never calls external services directly — it invokes the
orchestrators, which sequence the pipeline steps. Steps reach external services only through
the support layer (`ollama_client`, `ldm_seeder`) and apply rules from the knowledge layer.

---

## 3. End-to-End Data Flow

```mermaid
flowchart TD
    A[/BRD .docx/] --> B["Step 1 · Parse<br/>(LlamaParse → Unstructured → python-docx)"]
    B --> C["Step 1b · Ontology Build<br/>1 LLM call → domain, forbidden names,<br/>filter→dimension map; updates SKILL.md"]
    C --> D["Step 2 · GraphRAG<br/>chunk → LLMGraphTransformer → Neo4j → retrieve context"]
    D --> E["Step 3 · Entity Extraction<br/>2-pass: full-doc LLM + graph merge"]
    E --> F["Step 4 · Relationship Detection<br/>2-pass: full-doc LLM + graph merge"]
    F --> G["Step 5 · Ontology Enrichment<br/>ChromaDB semantic match (schema.org)"]
    G --> H["Step 6 · OWL/SHACL Rules<br/>R1–R6 inference + validation"]
    H --> I["Step 7 · CDM Assembly<br/>(no LLM) → entities, relationships,<br/>inferred, violations, domain"]

    I --> J{Pipeline mode}
    J -->|CDM only| K[/Render CDM<br/>Mermaid · JSON-LD · graph/]
    J -->|CDM + LDM| L["Step A · Seed Oracle reference (ChromaDB)"]
    L --> M["Step B · CDM→LDM Promotion<br/>2 LLM calls: expand dimensions + facts<br/>(grain, SCD, columns, FKs)"]
    M --> N["Step V · Validation Agent<br/>FR coverage · structural · grain<br/>≤3 repair iterations"]
    N --> O["Step F · DDL Generation<br/>(no LLM) → SQL (ANSI/Snowflake),<br/>Mermaid, FR-coverage matrix"]
    O --> P[/Render CDM + LDM/]

    I -.cache.-> Q[(ontology/generated/<br/>brd_hash_*.json)]
    M -.cache.-> Q
```

**Caching:** every BRD is hashed (SHA-256, 16 chars). Domain, GraphRAG context, CDM, and LDM
results are persisted to `ontology/generated/` by [agent/result_store.py](agent/result_store.py),
so re-runs are instant and **LDM-only** mode can reuse a prior CDM without re-extraction.

---

## 4. The Two Pipelines

### CDM Pipeline — [agent/pipeline_agent.py](agent/pipeline_agent.py)
`run_pipeline(file, ollama_url, model, chroma_path, ...)` → 8 steps (parse → ontology →
GraphRAG → entities → relationships → ontology enrichment → OWL/SHACL → assemble). Produces a
CDM dict of entities, relationships, inferred entities, SHACL violations, domain metadata, and
graph stats.

### LDM Pipeline — [agent/ldm_pipeline.py](agent/ldm_pipeline.py)
`run_ldm_pipeline(cdm_result, brd_text, ...)` → seed Oracle Retail reference → promote CDM
entities into `DIM_/FACT_/BRIDGE_/REF_` tables (grain, SCD type, surrogate/natural keys,
metric additivity) → validate-and-repair. DDL/diagram generation is rule-based in
[agent/step_ldm_ddl.py](agent/step_ldm_ddl.py).

---

## 5. Key Design Patterns

- **Tiered parser fallback** — best-quality parser first, always degrades to `python-docx`.
- **Two-pass extraction** — holistic full-document LLM read, then merge graph-discovered facts.
- **Hybrid rules + LLM** — deterministic OWL/SHACL rules (R1–R6, naming/pattern checks) guard
  creative LLM output; the validation agent combines both with a bounded repair loop.
- **RAG grounding** — ChromaDB supplies schema.org concepts (CDM) and Oracle Retail standards
  (LDM) so generated models follow established conventions.
- **Single source of truth for conventions** — [skills/SKILL.md](skills/SKILL.md) governs
  entity extraction; [skills/LDM_NAMING_CONVENTIONS.md](skills/LDM_NAMING_CONVENTIONS.md)
  governs table/column naming. Both are injected into prompts.
- **Hash-based caching & persistence** — results survive Streamlit reruns and session restarts.

---

## 6. Outputs

| Artifact | Produced by |
|---|---|
| CDM entity/relationship tables + interactive graph | [ui/output.py](ui/output.py), [ui/graph_view.py](ui/graph_view.py) |
| CDM Mermaid ER diagram & JSON-LD (RDF) | [agent/cdm_builder.py](agent/cdm_builder.py) |
| Inferred entities + SHACL violations | [ontology/rules.py](ontology/rules.py) |
| LDM table definitions (grain, SCD, columns) | [agent/step_ldm_promote.py](agent/step_ldm_promote.py) |
| SQL DDL (ANSI + Snowflake), LDM diagram, FR-coverage matrix | [agent/step_ldm_ddl.py](agent/step_ldm_ddl.py), [ui/ldm_output.py](ui/ldm_output.py) |
