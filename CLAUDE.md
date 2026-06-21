# DataModelerAgent

Transforms Business Requirements Documents (BRD `.docx`) into Conceptual Data Models (CDM) and Logical Data Models (LDM) with SQL DDL. Uses Ollama (local LLM), Neo4j Aura (knowledge graph), and ChromaDB (vector store).

## Run

```bash
streamlit run app.py
```

Requires Ollama running locally (`http://localhost:11434` by default) and Neo4j Aura credentials in `.env`.

## Key entry points

| Path | Role |
|---|---|
| `app.py` | Streamlit entry point — page config + routing |
| `src/agents/` | Pipeline orchestrators (CDM, LDM, validation) |
| `src/pipeline/` | Individual CDM/LDM steps (step1–step4b, cdm_builder, ldm steps) |
| `src/tools/` | Shared utilities: Ollama client, result cache, naming conventions |
| `src/knowledge/` | OWL/SHACL rules engine + ChromaDB seeders |
| `src/ui/` | Streamlit UI components |
| `skills/SKILL.md` | Entity extraction guardrails — injected into every LLM prompt |
| `skills/LDM_NAMING_CONVENTIONS.md` | Table/column naming rules for LDM promotion |
| `prompts/` | LLM system prompt templates (one file per pipeline step) |
| `rules/` | Declarative OWL inference rules and SHACL shapes |
| `ontology/generated/` | Hash-keyed JSON cache of CDM/LDM results (runtime, git-ignored) |

## Secrets

Copy `.env.example` to `.env` and fill in credentials. Never commit `.env`.

## CDM Pipeline (8 steps)

1. `step1_parser` — BRD parsing (LlamaParse → Unstructured → python-docx fallback)
2. `step1b_ontology_builder` — Domain ontology + SKILL.md update + OWL/SHACL stubs
3. `step2_graphrag` — Neo4j GraphRAG (chunk → LLMGraphTransformer → graph → retrieve)
4. `step2_entities` — Entity extraction (2-pass: full-doc LLM + GraphRAG merge)
5. `step3_relationships` — Relationship detection (2-pass)
6. `step4_ontology` — ChromaDB semantic enrichment (schema.org + Oracle Retail)
7. `step4b_owl_rules` — OWL/SHACL inference rules R1–R6 + SHACL validation
8. `cdm_builder` — Final CDM assembly (Mermaid ER + JSON-LD)

## LDM Pipeline (3 steps)

- **Step A** — Oracle Retail reference seeder (ChromaDB)
- **Step B** — CDM→LDM promotion via RAG + LLM (2 calls: dims + facts)
- **Step V** — Validation agent with auto-repair loop (≤3 iterations)

## Conventions

- All LLM calls go through `src/tools/ollama_client.py` (`chat()` / `extract_json()`)
- Results cached to `ontology/generated/{brd_hash}_{type}.json` via `src/tools/result_store.py`
- Entity types: `dimension`, `fact`, `reference`, `bridge` only (see `skills/SKILL.md`)
- Table prefixes: `DIM_`, `FACT_`, `BRIDGE_`, `REF_` (see `skills/LDM_NAMING_CONVENTIONS.md`)
