"""
Step B — CDM to LDM Promotion

Takes the CDM entity list as input and promotes each entity to a full
Logical Data Model table definition by:

1. Querying ChromaDB 'oracle_retail_reference' for Oracle-standard
   attribute definitions relevant to each entity
2. Calling the LLM (Ollama) with the entity + BRD context + Oracle
   reference to expand into a complete table definition

Two LLM calls:
  Call 1 — Expand all dimension entities into LDM dimension tables
  Call 2 — Expand all fact entities into LDM fact tables

Returns a structured LDM dict with full table definitions ready
for Steps C (SCD assignment), D (grain declaration), E (normalisation),
and F (DDL generation).
"""

import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from agent.ollama_client import chat, extract_json
from agent.ldm_seeder import query_oracle_reference
from agent.ri_metrics import query_ri_metrics

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_DIM = """You are an experienced subject matter expert in Data Modeling, specifically in Dimensional Modeling and able to precisely design data models Ontology and Graph RAG. Use your knowledge and experience in modeling the DWH schema for CDM and LDM.

You are designing a Logical Data Model (LDM) for a retail data warehouse.

Your task is to expand CDM dimension entities into full LDM dimension
table definitions, grounded in:
- The Oracle Retail Insights industry standard attribute definitions
- The BRD requirements for this specific subject area
- Dimensional modelling best practices (Kimball methodology)

For each dimension table produce:
- table_name: MUST start with DIM_ prefix — UPPER_SNAKE_CASE (e.g. DIM_PRODUCT, DIM_ORGANISATION, DIM_BUSINESS_CALENDAR)
  NEVER return a table name without the DIM_ prefix for dimension tables.
- grain: one sentence describing what one row represents
- scd_type: 1 (no history), 2 (full history), or 3 (limited history)
- columns: list of column definitions
- primary_key: the surrogate key column name
- natural_key: the business key column name(s)
- source_system: e.g. RMS / ReSA / MFP
- fr_references: list of BRD FR IDs this table satisfies

For each column provide:
- name: UPPER_SNAKE_CASE
- data_type: VARCHAR2(n) / NUMBER(p,s) / DATE / CHAR(1) / TIMESTAMP
- nullable: true or false
- description: one sentence from Oracle standard or BRD
- is_pk: true if surrogate key
- is_nk: true if natural/business key
- is_fk: true if foreign key

FORBIDDEN: Do not include report names, KPI names, or metric values
as dimension attributes. Attributes describe the dimension member itself.

Respond ONLY with valid JSON, no explanation, no markdown."""

SYSTEM_FACT = """You are an experienced subject matter expert in Data Modeling, specifically in Dimensional Modeling and able to precisely design data models Ontology and Graph RAG. Use your knowledge and experience in modeling the DWH schema for CDM and LDM.

You are designing a Logical Data Model (LDM) for a retail data warehouse.

Your task is to expand CDM fact entities into full LDM fact table
definitions, grounded in:
- The Oracle Retail Insights industry standard metric definitions
- The BRD requirements for this specific subject area
- Dimensional modelling best practices (Kimball methodology)

For each fact table produce:
- table_name: MUST start with FACT_ prefix — UPPER_SNAKE_CASE (e.g. FACT_SALES, FACT_MARKDOWN, FACT_SALES_FORECAST)
  NEVER return a table name without the FACT_ prefix for fact tables.
- grain: exact grain declaration (e.g. "item x location x day x price type")
- grain_columns: list of FK column names that define the grain
- columns: list of column definitions
- additive_metrics: list of metric names that are fully additive
- semi_additive_metrics: list of metrics additive across some but not all dims
- non_additive_metrics: list of ratio/percentage metrics (never SUM)
- source_system: e.g. ReSA / MFP / ReIM
- fr_references: list of BRD FR IDs this table satisfies

For each column provide:
- name: UPPER_SNAKE_CASE
- data_type: NUMBER(18,4) for amounts / NUMBER(12,2) for quantities /
  NUMBER(10,6) for ratios / VARCHAR2 for codes / DATE / CHAR(1)
- nullable: true or false
- description: definition from Oracle standard or BRD
- is_fk: true if foreign key to a dimension
- metric_type: 'additive' / 'semi_additive' / 'non_additive' / 'fk' / 'degenerate'

USING THE CANDIDATE METRIC COLUMNS:
The user prompt includes "CANDIDATE METRIC COLUMNS" — the Oracle Retail Insights
standard measures for the relevant fact area, each with an exact column name,
data type and additivity. For every candidate measure that the BRD requires,
include a column using that EXACT name, data_type and additivity, and place it in
the matching additive_metrics / semi_additive_metrics / non_additive_metrics list.
Do not invent a different name for a measure that already has a standard column.
Only include measures supported by the BRD; you may add BRD-specific measures not
in the candidate list when the BRD calls for them.

Respond ONLY with valid JSON, no explanation, no markdown."""

USER_DIM = """Expand these CDM dimension entities into full LDM dimension table definitions.

CDM ENTITIES (dimensions to expand):
{entities}

ORACLE RETAIL REFERENCE CONTEXT:
{oracle_context}

BRD CONTEXT:
{brd_context}

Return a JSON object:
{{
  "dimension_tables": [
    {{
      "table_name": "DIM_PRODUCT",
      "grain": "...",
      "scd_type": 2,
      "primary_key": "PRODUCT_KEY",
      "natural_key": ["ITEM_ID"],
      "source_system": "RMS",
      "fr_references": ["FR-010", "FR-018"],
      "columns": [
        {{"name": "PRODUCT_KEY", "data_type": "NUMBER(18)", "nullable": false,
          "description": "Surrogate key", "is_pk": true, "is_nk": false, "is_fk": false}},
        ...
      ]
    }},
    ...
  ]
}}
JSON:"""

USER_FACT = """Expand these CDM fact entities into full LDM fact table definitions.

CDM ENTITIES (facts to expand):
{entities}

ORACLE RETAIL REFERENCE CONTEXT:
{oracle_context}

CANDIDATE METRIC COLUMNS (Oracle Retail Insights standard measures —
use the exact column name / data_type / additivity for any the BRD requires):
{metric_candidates}

BRD CONTEXT:
{brd_context}

DIMENSION SURROGATE KEYS AVAILABLE:
{dim_keys}

Return a JSON object:
{{
  "fact_tables": [
    {{
      "table_name": "FACT_SALES",
      "grain": "item x location x day x retail price type",
      "grain_columns": ["PRODUCT_KEY", "ORG_KEY", "DATE_KEY", "PRICE_TYPE_KEY"],
      "source_system": "ReSA",
      "fr_references": ["FR-012"],
      "additive_metrics": ["NET_SALES_AMT", "GROSS_SALES_AMT"],
      "semi_additive_metrics": ["COMP_STORE_SALES"],
      "non_additive_metrics": ["SALES_AMT_CONTRIB_DIV"],
      "columns": [
        {{"name": "PRODUCT_KEY", "data_type": "NUMBER(18)", "nullable": false,
          "description": "FK to DIM_PRODUCT", "is_fk": true, "metric_type": "fk"}},
        ...
      ]
    }},
    ...
  ]
}}
JSON:"""


# ── Oracle RAG context builder ────────────────────────────────────────────────

def _build_oracle_context(
    entities: list[dict],
    chroma_path: str,
    entity_type: str,
) -> str:
    """Query ChromaDB for Oracle reference context relevant to these entities."""
    context_parts = []
    seen_ids = set()

    for entity in entities:
        name = entity.get("name", "")
        desc = entity.get("description", "")
        query = f"{name} {desc} {entity_type} attributes"

        results = query_oracle_reference(
            query=query,
            chroma_path=chroma_path,
            top_k=2,
        )
        for r in results:
            chunk_id = r["metadata"].get("table_hint", "")
            if chunk_id not in seen_ids:
                seen_ids.add(chunk_id)
                context_parts.append(
                    f"[{r['metadata']['table_hint']}]\n{r['text'][:600]}"
                )

    return "\n\n---\n\n".join(context_parts) if context_parts else "No Oracle reference found"


def _build_metric_candidates(fact_entities: list[dict], chroma_path: str) -> str:
    """
    Retrieve Oracle Retail Insights candidate metric columns relevant to the
    fact entities from the 'oracle_retail_metrics' collection. Returns the
    matched metric-area chunks (each lists exact column / type / additivity).
    """
    parts = []
    seen = set()
    for entity in fact_entities:
        name = entity.get("name", "")
        desc = entity.get("description", "")
        attrs = ", ".join(entity.get("attributes", []))
        query = f"{name} {desc} {attrs}".strip()

        for r in query_ri_metrics(query=query, chroma_path=chroma_path, top_k=2):
            hint = r["metadata"].get("fact_table_hint", "")
            if hint and hint not in seen:
                seen.add(hint)
                parts.append(r["text"])

    return "\n\n---\n\n".join(parts) if parts else "No standard metric catalog found (run the seeder)."


# ── Naming conventions — loaded from skills/LDM_NAMING_CONVENTIONS.md ─────────
from agent.ldm_conventions import (
    enforce_naming,
    enforce_ldm_naming,
    enforce_mandatory_fks,
    get_prompt_rules,
    SCHEMA,
    SCD_ASSIGNMENTS,
    GRAIN_DECLARATIONS,
    STANDARD_PK_NAMES,
    STANDARD_FK_NAMES,
    MANDATORY_FACT_FKS,
)

# ── Main entry point ──────────────────────────────────────────────────────────

def promote_cdm_to_ldm(
    cdm_result:  dict,
    brd_text:    str,
    ollama_url:  str,
    model:       str,
    chroma_path: str,
    temperature: float = 0.1,
    on_log       = None,
) -> dict:
    """
    Promote CDM entities to full LDM table definitions.

    Args:
        cdm_result:  Output from the CDM pipeline (has 'entities' key)
        brd_text:    Full BRD text for context
        ollama_url:  Ollama base URL
        model:       Ollama model name
        chroma_path: Path to ChromaDB
        temperature: LLM temperature
        on_log:      Logging callback

    Returns:
        ldm_result dict with dimension_tables and fact_tables
    """
    def log(msg):
        if on_log: on_log(msg)

    entities = cdm_result.get("entities", [])
    if not entities:
        raise ValueError("No CDM entities found — run CDM pipeline first")

    # Split by type
    dim_entities   = [e for e in entities if e.get("type") in ("dimension", "reference")]
    fact_entities  = [e for e in entities if e.get("type") == "fact"]
    bridge_entities = [e for e in entities if e.get("type") == "bridge"]

    log(f"Promoting {len(dim_entities)} dimensions, {len(fact_entities)} facts, "
        f"{len(bridge_entities)} bridges")

    # BRD context — first 3000 chars
    brd_ctx = brd_text[:3000] if len(brd_text) > 3000 else brd_text

    # ── Call 1 — Dimension tables ─────────────────────────────────────────────
    log("Call 1 — expanding dimension entities via Oracle RAG…")

    dim_oracle_ctx = _build_oracle_context(dim_entities, chroma_path, "dimension")
    log(f"  Oracle context: {len(dim_oracle_ctx)} chars from {chroma_path}")

    dim_entity_summary = "\n".join(
        f"- {e['name']} ({e['type']}): {e['description']}"
        + (f" | attributes: {', '.join(e.get('attributes', []))}" if e.get('attributes') else "")
        for e in dim_entities
    )

    dimension_tables = []
    try:
        # Inject naming conventions into system prompt at call time
        from agent.ldm_conventions import get_prompt_rules
        system_dim_with_rules = SYSTEM_DIM + "\n" + get_prompt_rules()
        raw_dim = chat(
            base_url=ollama_url,
            model=model,
            messages=[
                {"role": "system", "content": system_dim_with_rules},
                {"role": "user",   "content": USER_DIM.format(
                    entities=dim_entity_summary,
                    oracle_context=dim_oracle_ctx,
                    brd_context=brd_ctx,
                )},
            ],
            temperature=temperature,
            format="json",
        )
        data = extract_json(raw_dim)
        dimension_tables = data.get("dimension_tables", []) if isinstance(data, dict) else []
        log(f"  Expanded {len(dimension_tables)} dimension tables")
    except Exception as e:
        log(f"  Dimension expansion failed: {e}")

    # ── Call 2 — Fact tables ──────────────────────────────────────────────────
    log("Call 2 — expanding fact entities via Oracle RAG…")

    fact_oracle_ctx = _build_oracle_context(fact_entities, chroma_path, "fact_metrics")
    metric_candidates = _build_metric_candidates(fact_entities, chroma_path)
    log(f"  RI metric candidates: {len(metric_candidates)} chars")

    fact_entity_summary = "\n".join(
        f"- {e['name']} ({e['type']}): {e['description']}"
        + (f" | metrics: {', '.join(e.get('attributes', []))}" if e.get('attributes') else "")
        for e in fact_entities
    )

    # Build available dimension keys for FK references
    dim_keys = "\n".join(
        f"- {t.get('table_name','')}: {t.get('primary_key','')}"
        for t in dimension_tables
    ) if dimension_tables else "DIM_PRODUCT: PRODUCT_KEY\nDIM_ORGANISATION: ORG_KEY\nDIM_BUSINESS_CALENDAR: DATE_KEY\nDIM_RETAIL_PRICE_TYPE: PRICE_TYPE_KEY"

    fact_tables = []
    try:
        system_fact_with_rules = SYSTEM_FACT + "\n" + get_prompt_rules()
        raw_fact = chat(
            base_url=ollama_url,
            model=model,
            messages=[
                {"role": "system", "content": system_fact_with_rules},
                {"role": "user",   "content": USER_FACT.format(
                    entities=fact_entity_summary,
                    oracle_context=fact_oracle_ctx,
                    metric_candidates=metric_candidates,
                    brd_context=brd_ctx,
                    dim_keys=dim_keys,
                )},
            ],
            temperature=temperature,
            format="json",
        )
        data = extract_json(raw_fact)
        fact_tables = data.get("fact_tables", []) if isinstance(data, dict) else []
        log(f"  Expanded {len(fact_tables)} fact tables")
    except Exception as e:
        log(f"  Fact expansion failed: {e}")

    # ── Assemble bridge tables (rule-based, no LLM) ───────────────────────────
    bridge_tables = _build_bridge_tables(bridge_entities)
    log(f"  Built {len(bridge_tables)} bridge tables (rule-based)")

    # ── Assemble reference tables ─────────────────────────────────────────────
    reference_tables = _build_reference_tables()
    log(f"  Built {len(reference_tables)} reference tables (standard)")

    ldm = {
        "dimension_tables":  dimension_tables,
        "fact_tables":       fact_tables,
        "bridge_tables":     bridge_tables,
        "reference_tables":  reference_tables,
        "entity_count":      len(dimension_tables) + len(fact_tables) + len(bridge_tables) + len(reference_tables),
        "cdm_entities_used": len(entities),
    }

    # Enforce DIM_ / FACT_ / BRIDGE_ / REF_ naming convention
    enforce_ldm_naming(ldm)

    # Enforce mandatory conformed dimensions on all fact tables
    log("Validating mandatory conformed dimension connections…")
    enforce_mandatory_fks(ldm, on_log=log)
    log(f"LDM promotion complete: {ldm['entity_count']} tables total")

    # Log any naming corrections
    all_names = (
        [t["table_name"] for t in dimension_tables] +
        [t["table_name"] for t in fact_tables]
    )
    log(f"Table names: {', '.join(all_names)}")
    return ldm


# ── Rule-based table builders ─────────────────────────────────────────────────

def _build_bridge_tables(bridge_entities: list) -> list:
    """Build bridge table definitions from CDM bridge entities."""
    bridges = []
    for e in bridge_entities:
        name = e.get("name", "").upper()
        table_name = f"BRIDGE_{re.sub(r'BRIDGE$', '', name)}" if "BRIDGE" in name else f"BRIDGE_{name}"
        bridges.append({
            "table_name": table_name,
            "grain": f"Resolves M:N relationship for {e.get('name','')}",
            "description": e.get("description", ""),
            "columns": [
                {"name": "ITEM_ID",             "data_type": "VARCHAR2(25)", "nullable": False, "is_fk": True,  "description": "FK to DIM_PRODUCT item natural key"},
                {"name": "SEASON_KEY",          "data_type": "NUMBER(10)",   "nullable": False, "is_fk": True,  "description": "FK to DIM_PRODUCT_SEASON"},
                {"name": "PHASE_ID",            "data_type": "VARCHAR2(20)", "nullable": True,  "is_fk": False, "description": "Optional phase within season"},
                {"name": "WEIGHTING_FACTOR",    "data_type": "NUMBER(10,6)", "nullable": True,  "is_fk": False, "description": "Proportion allocation weight for double-counting prevention"},
                {"name": "PRIMARY_SEASON_FLAG", "data_type": "CHAR(1)",      "nullable": False, "is_fk": False, "description": "Y if this is the primary season for the item"},
            ],
            "fr_references": ["FR-013"],
        })
    # Always ensure BRIDGE_ITEM_SEASON exists if no bridge found
    if not bridges:
        bridges.append({
            "table_name": "BRIDGE_ITEM_SEASON",
            "grain": "One row per item per season phase assignment",
            "description": "Resolves M:N between DIM_PRODUCT items and DIM_PRODUCT_SEASON",
            "columns": [
                {"name": "ITEM_ID",             "data_type": "VARCHAR2(25)", "nullable": False, "is_fk": True,  "description": "FK to DIM_PRODUCT ITEM_ID (natural key)"},
                {"name": "SEASON_KEY",          "data_type": "NUMBER(10)",   "nullable": False, "is_fk": True,  "description": "FK to DIM_PRODUCT_SEASON surrogate key"},
                {"name": "PHASE_ID",            "data_type": "VARCHAR2(20)", "nullable": True,  "is_fk": False, "description": "Optional season phase identifier"},
                {"name": "WEIGHTING_FACTOR",    "data_type": "NUMBER(10,6)", "nullable": True,  "is_fk": False, "description": "Proportional weight for metrics across seasons"},
                {"name": "PRIMARY_SEASON_FLAG", "data_type": "CHAR(1)",      "nullable": False, "is_fk": False, "description": "Y=primary season for this item, N=secondary"},
            ],
            "fr_references": ["FR-013"],
        })
    return bridges


def _build_reference_tables() -> list:
    """Build standard reference table definitions (no LLM needed)."""
    return [
        {
            "table_name": "REF_CURRENCY",
            "grain": "One row per currency code",
            "description": "Currency lookup for multi-currency support (FR-009)",
            "columns": [
                {"name": "CURRENCY_KEY",   "data_type": "NUMBER(5)",     "nullable": False, "is_pk": True},
                {"name": "CURRENCY_CODE",  "data_type": "VARCHAR2(3)",   "nullable": False},
                {"name": "CURRENCY_DESC",  "data_type": "VARCHAR2(60)",  "nullable": True},
                {"name": "CURRENCY_TYPE",  "data_type": "VARCHAR2(15)",  "nullable": True,  "description": "LOCAL/DOCUMENT/GLOBAL1/GLOBAL2/GLOBAL3"},
                {"name": "EXCHANGE_RATE",  "data_type": "NUMBER(18,8)",  "nullable": True},
                {"name": "EFFECTIVE_DATE", "data_type": "DATE",          "nullable": True},
            ],
            "fr_references": ["FR-009"],
        },
        {
            "table_name": "REF_SOURCE_SYSTEM",
            "grain": "One row per source system",
            "description": "Source system registry (ReSA/RMS/MFP/ReIM/RPM)",
            "columns": [
                {"name": "SYSTEM_CODE",  "data_type": "VARCHAR2(10)",  "nullable": False, "is_pk": True},
                {"name": "SYSTEM_NAME",  "data_type": "VARCHAR2(60)",  "nullable": True},
                {"name": "SYSTEM_DESC",  "data_type": "VARCHAR2(250)", "nullable": True},
                {"name": "DATA_TYPE",    "data_type": "VARCHAR2(30)",  "nullable": True},
                {"name": "ACTIVE_FLAG",  "data_type": "CHAR(1)",       "nullable": False, "description": "Y/N"},
            ],
            "fr_references": ["NFR-Sources"],
        },
        {
            "table_name": "REF_ETL_BATCH_STATUS",
            "grain": "One row per subject area per load date",
            "description": "ETL batch gate — reports blocked until batch SUCCESS (NFR)",
            "columns": [
                {"name": "BATCH_KEY",          "data_type": "NUMBER(18)",    "nullable": False, "is_pk": True},
                {"name": "SUBJECT_AREA_CODE",  "data_type": "VARCHAR2(30)",  "nullable": False},
                {"name": "LOAD_DATE",          "data_type": "DATE",          "nullable": False},
                {"name": "LOAD_START_TIME",    "data_type": "TIMESTAMP",     "nullable": True},
                {"name": "LOAD_END_TIME",      "data_type": "TIMESTAMP",     "nullable": True},
                {"name": "BATCH_STATUS",       "data_type": "VARCHAR2(10)",  "nullable": False, "description": "PENDING/SUCCESS/FAILED"},
                {"name": "RECORDS_LOADED",     "data_type": "NUMBER(12)",    "nullable": True},
                {"name": "ERROR_COUNT",        "data_type": "NUMBER(10)",    "nullable": True},
                {"name": "SOURCE_SYSTEM_CODE", "data_type": "VARCHAR2(10)",  "nullable": True},
            ],
            "fr_references": ["NFR-DataCurrency"],
        },
    ]
