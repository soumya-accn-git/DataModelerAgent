# BRD → Conceptual Data Model Generator

A local-first Streamlit app that takes a Business Requirements Document (`.docx`)
and generates a Conceptual Data Model using **Ollama** (local LLM) and
**ChromaDB** (vector ontology store).

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Streamlit UI                                    │
│  ├── Upload (.docx)                              │
│  ├── Pipeline status panel                       │
│  └── CDM output (diagram · entities · JSON-LD)  │
└────────────────┬─────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────┐
│  Agent Pipeline                                  │
│  Step 1 → Document parser   (python-docx)        │
│  Step 2 → Entity extraction (Ollama LLM)         │
│  Step 3 → Relationship det. (Ollama LLM)         │
│  Step 4 → Ontology enrich.  (ChromaDB query)     │
│  Step 5 → CDM generation    (Mermaid / JSON-LD)  │
└────────────────┬─────────────────────────────────┘
                 │
     ┌───────────┴───────────┐
     │                       │
┌────▼────┐           ┌──────▼──────┐
│ Ollama  │           │  ChromaDB   │
│ (local) │           │  (local)    │
└─────────┘           └─────────────┘
```

## Prerequisites

### 1. Ollama
Install from https://ollama.com and pull a model:

```bash
ollama pull llama3.1:8b      # recommended minimum
# or
ollama pull mistral:7b
# or (best quality, needs ~10GB RAM)
ollama pull qwen2.5:14b
```

Start the server:
```bash
ollama serve
```

### 2. Python dependencies
```bash
pip install -r requirements.txt
```

## First run

### Step A — Seed the ontology
The sidebar has a **🌱 Seed ontology into ChromaDB** button.
Click it once before running any BRD. This loads ~70 schema.org concepts
(entities + relationship types) into ChromaDB as vector embeddings.

The database is persisted to `./chroma_db` by default.

### Step B — Run the app
```bash
streamlit run app.py
```

## Usage

1. Open `http://localhost:8501` in your browser.
2. In the sidebar, verify the Ollama URL and select your model.
3. Upload a `.docx` BRD file.
4. Click **▶ Run pipeline**.
5. Watch the 5-step pipeline progress in real time.
6. Review and export the CDM from the output tabs:
   - **🗺️ Diagram** — Mermaid ER diagram + download buttons
   - **📦 Entities** — editable entity table (CSV export)
   - **🔗 Relationships** — relationship table (CSV export)
   - **📋 JSON-LD** — machine-readable CDM

## Customising the ontology

Edit `ontology/seeder.py` to add domain-specific concepts.
Each entry is a tuple:

```python
("your:ConceptId", "Label", "Description of what this concept is.", "class")
```

Use `"class"` for entity concepts and `"property"` for relationship types.
Re-run the seed from the sidebar after editing.

## Project structure

```
brd_cdm_app/
├── app.py                    # Streamlit entry point
├── requirements.txt
├── ui/
│   ├── sidebar.py            # Config panel
│   ├── upload.py             # File upload widget
│   ├── pipeline.py           # Step-by-step progress UI
│   └── output.py             # CDM diagram + tables
├── agent/
│   ├── pipeline.py           # Orchestrator
│   ├── ollama_client.py      # Ollama HTTP wrapper
│   ├── step1_parser.py       # .docx parser
│   ├── step2_entities.py     # LLM entity extraction
│   ├── step3_relationships.py# LLM relationship detection
│   ├── step4_ontology.py     # ChromaDB enrichment
│   └── cdm_builder.py        # Mermaid + JSON-LD export
└── ontology/
    └── seeder.py             # Schema.org seed data
```

## Tips

- **Better results**: Use a 13B+ model for complex BRDs.
- **Speed**: `mistral:7b` is the fastest; `llama3.1:8b` is the best quality/speed balance.
- **Structured output**: Ollama's `format: "json"` mode is used automatically — this greatly improves extraction reliability.
- **Long BRDs**: The app clips to 6,000 chars for entity extraction and 4,000 for relationship detection to stay within model context. For very long documents, consider splitting the BRD into functional sections first.
