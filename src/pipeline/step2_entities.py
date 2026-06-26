"""
Step 2 — Entity extraction — Two-pass + deterministic GraphRAG merge.

Pass 1a — Full document scan (single LLM call, full BRD text)
Pass 1b — Completeness sweep (second LLM call if yield looks low)
Pass 2  — Deterministic GraphRAG merge (code, not LLM)
  Iterates the structured graph_nodes list and adds any CDM-type node
  (Dimension/Fact/Reference/Bridge) that Pass 1 missed.  Because this
  is a set-union in Python — not an LLM prompt — every GraphRAG node
  is guaranteed to appear in the final entity list.
"""

import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from src.tools.ollama_client import chat, extract_json
from src.tools.skill_loader import load_skill
try:
    from src.knowledge.oracle_rdm_seeder import query_oracle_rdm, COLLECTION_LDM as _RDM_LDM
    _ORACLE_RDM_AVAILABLE = True
except Exception:
    _ORACLE_RDM_AVAILABLE = False

SKILL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "skills", "SKILL.md"
)

# Suffixes that almost always mark a report/visualization artifact rather than
# a data entity — always rejected.
HARD_FORBIDDEN_SUFFIXES = {
    "report","dashboard","scorecard","analysis","overview","summary",
    "monitor","tracker","snapshot","analytics","portal","feed","digest",
    "listing","ranking","top10","subjectarea",
}
# Suffixes that usually denote a measure/attribute of a fact (not an entity) —
# rejected UNLESS the entity is a reference (lookup) table, e.g. ExchangeRate.
# Previously these were hard-rejected, silently dropping legitimate entities.
SOFT_FORBIDDEN_SUFFIXES = {
    "kpi","metric","rate","ratio","percentage","view","insight",
}
# Names that end in a forbidden suffix but are legitimate reference entities.
ALLOWED_EXACT_EXCEPTIONS = {
    "exchangerate","conversionrate","currencyrate","taxrate",
    "interestrate","growthrate","fxrate",
}
FORBIDDEN_EXACT = {
    "top10","kpi","metric","report","dashboard",
    "summary","analysis","view","data","information"
}
# Names containing "Top<N>" anywhere (not just as suffix) are ranking queries.
_FORBIDDEN_INFIX_RE = re.compile(r'top\d+', re.IGNORECASE)
VALID_TYPES = {"dimension","fact","reference","bridge"}

# ── Deterministic type reclassification ───────────────────────────────────────
# The LLM frequently mislabels measurable business processes (Sales, Profit,
# Markdown, Forecast) as "dimension". These name tokens force such entities back
# to "fact" so a sales/profit BRD never yields zero facts. Matched against the
# entity NAME only (lower-cased) to avoid description false positives.
FACT_NAME_TOKENS = (
    "sales", "sale", "profit", "revenue", "margin", "markdown", "markup",
    "forecast", "transaction", "payment", "order", "shipment", "receipt",
    "contribution", "spend", "turnover", "gmroi", "sellthrough", "selling",
    "billing", "invoice", "claim", "usage", "movement",
)
# Explicit suffixes are authoritative — they reflect deliberate modeling intent
# and are never overridden by the keyword heuristic.
_SUFFIX_TYPE = (
    ("dimension", "dimension"),
    ("fact",      "fact"),
    ("reference", "reference"),
    ("bridge",    "bridge"),
    ("junction",  "bridge"),
)


def _reclassify_type(name: str, llm_type: str) -> str:
    """Deterministically correct an entity's type from its name.

    1. An explicit suffix (…Dimension/…Fact/…Reference/…Bridge) wins outright.
    2. Otherwise, a fact-process token in the name overrides a 'dimension' or
       'reference' label (the common LLM mistake). Facts already typed 'fact',
       and 'bridge' entities, are left alone.
    Returns the corrected type. Pure function — same input, same output."""
    n = name.lower()
    for suffix, t in _SUFFIX_TYPE:
        if n.endswith(suffix):
            return t
    if llm_type in ("dimension", "reference") and any(tok in n for tok in FACT_NAME_TOKENS):
        return "fact"
    return llm_type

# GraphRAG node types that map to CDM entity types.
# Any other GraphRAG type (Report, Filter, Actor, BusinessRule …) is skipped.
_GRAPH_TYPE_MAP = {
    "Dimension": "dimension",
    "Fact":      "fact",
    "Reference": "reference",
    "Bridge":    "bridge",
}

# ── Pass 1 prompts — full document scan ──────────────────────────────────────

SYSTEM_PASS1 = """You are an experienced subject matter expert in Data Modeling, specifically in Dimensional Modeling and able to precisely design data models Ontology and Graph RAG. Use your knowledge and experience in modeling the DWH schema for CDM and LDM.

{skill}

Perform a full document analysis of the BRD.
Read the ENTIRE BRD text carefully and extract ALL business entities
needed for a Conceptual Data Model.

Look specifically at:
- Any section titled "Dimensions", "Key Dimensions", "Subject Areas"
- Any section titled "Facts", "Metrics", "Key Metrics", "Measures"
- Any section titled "Functional Requirements" — extract entities implied
- Tables listing hierarchies, attributes, or data elements
- Report descriptions — extract the underlying entities they report on

Entity types:
  dimension — descriptive axis (Customer, Product, Time, Geography)
  fact      — measurable event or transaction (Sale, Transaction, Payment)
  reference — lookup table (Currency, Status, Category)
  bridge    — resolves M:N between dimensions

FORBIDDEN — never return:
- Report/dashboard names ending in: Report, Dashboard, Scorecard, Analysis
- Metric/KPI names (these are ATTRIBUTES of fact entities, not entities)

IMPORTANT — Filter and Prompt names imply Dimension entities:
  Instead of returning "RegionFilter" as an entity, infer and return "GeographyDimension"
  Instead of returning "DateRangePrompt", return "TimeDimension"
  Instead of returning "ProductCategoryFilter", return "ProductDimension"
  Strip the Filter/Prompt suffix, identify the subject noun, and return the corresponding Dimension.
- Generic terms: Data, Information, System

Respond ONLY with valid JSON, no explanation, no markdown."""

USER_PASS1 = """Read the full BRD below and extract EVERY entity needed for the CDM.

Be exhaustive — do not stop after finding a few. Read every section,
every table, every requirement. A complete BRD typically yields
5–15 dimension entities, 2–6 fact entities, 2–5 reference entities.

IMPORTANT: Extract ALL fact entities. A typical retail BRD has:
- FACT_SALES or SalesFact (daily sales transactions)
- FACT_MARKDOWN or MarkdownFact (markdowns and markups)
- FACT_SALES_FORECAST or ForecastFact (sales forecasts)
- FACT_SUPPLIER_COST or SupplierCostFact (cost tiers)
Do NOT stop after finding one fact. Extract all of them.

For each entity return:
- "name": PascalCase singular noun (e.g. "ProductDimension", "SalesFact")
- "type": one of [dimension, fact, reference, bridge]
- "description": one sentence — business meaning
- "attributes": up to 6 key fields or hierarchy levels
- "source": exact section heading or table name from the BRD

Return: {{"entities": [...]}}

FULL BRD TEXT:
---
{brd_text}
---
JSON:"""

USER_COMPLETENESS = """A first pass already extracted some entities from this BRD (listed under KNOWN).
Re-read the ENTIRE BRD and return ANY entities that are MISSING — of EVERY type:
dimensions, facts, reference (lookup) tables, and bridges. Do not repeat KNOWN ones.

Be exhaustive. Check every section, every table, every functional requirement.
Pay special attention to:
- Separate business processes that each imply their OWN fact (e.g. sales vs. markdowns
  vs. forecasts are distinct facts — do not merge them)
- Dimensions and reference tables introduced in later sections
- Subject nouns behind any filter/prompt names (return the implied Dimension)

For each NEW entity return:
- "name": PascalCase singular noun
- "type": one of [dimension, fact, reference, bridge]
- "description": one sentence — business meaning
- "attributes": up to 6 key fields
- "source": exact section heading or table name from the BRD

KNOWN (already found — do NOT repeat these):
{known}

Return: {{"entities": [...]}}

FULL BRD TEXT:
---
{brd_text}
---
JSON:"""

# ── Pass 2 prompts — GraphRAG enrichment ─────────────────────────────────────

SYSTEM_PASS2 = """You are an experienced subject matter expert in Data Modeling, specifically in Dimensional Modeling and able to precisely design data models Ontology and Graph RAG. Use your knowledge and experience in modeling the DWH schema for CDM and LDM.

{skill}

Validate and enrich the entity list using additional context from a knowledge graph.

Your task:
1. Review the existing entity list (Pass 1 results)
2. Review the GraphRAG context (nodes and relationships extracted from
   the BRD knowledge graph)
3. Add any entities found in the graph that are MISSING from Pass 1
4. Correct any misclassified types in Pass 1
5. Do NOT remove correct entities from Pass 1
6. Apply the same FORBIDDEN rules — no reports, no metrics as entities
   NOTE: Filters and Prompts are NOT forbidden — they imply Dimensions.
   Convert any filter/prompt names to their underlying dimension entity.

Respond ONLY with valid JSON, no explanation, no markdown."""

USER_PASS2 = """Below are:
A) Entities already extracted from the full BRD (Pass 1)
B) Additional context from the GraphRAG knowledge graph

Enrich the entity list by:
- Adding entities found in the GraphRAG context that are missing from Pass 1
- Correcting any type misclassifications
- Keeping all correct Pass 1 entities

PASS 1 ENTITIES:
{pass1_entities}

GRAPHRAG CONTEXT:
---
{graphrag_context}
---

Return the COMPLETE merged entity list:
{{"entities": [...]}}

JSON:"""


# ── Main entry point ──────────────────────────────────────────────────────────

def extract_entities(
    brd_text:         str,
    ollama_url:       str,
    model:            str,
    temperature:      float = 0.1,
    graphrag_context: str   = "",
    graph_nodes:      list  = None,   # structured nodes from step2_graphrag
    sections:         list  = None,
    on_log                  = None,
    max_chunks:       int   = 4,      # kept for API compat
    oltp_context:     str   = "",     # compact source-system summary (optional)
) -> list[dict]:
    """
    Two-pass entity extraction with deterministic GraphRAG merge.

    Pass 1:  LLM full-document scan (+ completeness sweep if yield low).
    Pass 2:  Code-based merge of structured graph_nodes — guaranteed inclusion
             of every CDM-type node the LLM missed, with no LLM call.
    """
    def log(msg):
        if on_log: on_log(msg)

    skill_text = load_skill(SKILL_PATH)

    # Append OLTP source context to the skill text when provided — gives the
    # LLM a source-system signal so it can infer fact/dimension entities from
    # the actual tables that will feed the data warehouse.
    if oltp_context:
        skill_text = skill_text + "\n\n" + oltp_context

    # ── Pass 1a — Full document scan ─────────────────────────────────────────
    log("Pass 1a — full document scan…")

    # Send the ENTIRE BRD. With num_ctx raised (see ollama_client), there is no
    # need to slice — slicing was the main cause of missed later-section entities.
    full_text = brd_text
    log(f"  Document: {len(brd_text):,} chars → sending full text")

    pass1_entities = []
    try:
        raw1 = chat(
            base_url=ollama_url,
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PASS1.format(skill=skill_text)},
                {"role": "user",   "content": USER_PASS1.format(brd_text=full_text)},
            ],
            temperature=temperature,
            format="json",
        )
        data1 = extract_json(raw1)
        items = data1.get("entities", []) if isinstance(data1, dict) else (data1 or [])
        pass1_entities = _validate_and_clean(items)
        log(f"  Pass 1a found {len(pass1_entities)} valid entities")
    except Exception as e:
        log(f"  Pass 1a failed: {e}")

    # ── Pass 1b — Completeness sweep (adds entities of ANY type) ───────────────
    # The holistic Pass 1 can still stop early on long BRDs. If the yield looks
    # low, run one more FULL-document pass and merge every new entity type — not
    # just facts — so later-section dimensions and reference tables aren't lost.
    fact_count = sum(1 for e in pass1_entities if e.get("type") == "fact")
    log(f"  Pass 1a totals: {len(pass1_entities)} entities ({fact_count} facts)")

    if len(pass1_entities) < 8 or fact_count < 2:
        log("Pass 1b — completeness sweep (full document, all entity types)…")
        known = ", ".join(e["name"] for e in pass1_entities) or "(none yet)"
        try:
            raw1b = chat(
                base_url=ollama_url,
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PASS1.format(skill=skill_text)},
                    {"role": "user",   "content": USER_COMPLETENESS.format(
                        brd_text=full_text, known=known)},
                ],
                temperature=temperature,
                format="json",
            )
            data1b = extract_json(raw1b)
            items1b = data1b.get("entities", []) if isinstance(data1b, dict) else (data1b or [])
            new_ents = _validate_and_clean(items1b)

            # Merge — add any new entity of ANY type not already present
            existing_names = {e["name"].lower() for e in pass1_entities}
            added = 0
            for e in new_ents:
                if e["name"].lower() not in existing_names:
                    pass1_entities.append(e)
                    existing_names.add(e["name"].lower())
                    added += 1
            log(f"  Pass 1b added {added} entities (all types)")
        except Exception as e:
            log(f"  Pass 1b failed: {e}")

    if not pass1_entities:
        log("  ⚠️  Pass 1 returned no entities — check model and BRD content")

    # ── Pass 2 — Deterministic GraphRAG merge ────────────────────────────────
    if graph_nodes:
        pass1_entities = _merge_graph_nodes(pass1_entities, graph_nodes, log)
        log(f"  Total after GraphRAG merge: {len(pass1_entities)} entities")
    else:
        log("  Pass 2 skipped — no structured graph_nodes available")

    return pass1_entities


# ── Deterministic GraphRAG merge ─────────────────────────────────────────────

def _merge_graph_nodes(
    pass1: list[dict],
    graph_nodes: list[dict],
    log=None,
) -> list[dict]:
    """
    Code-based set-union of GraphRAG nodes into the Pass 1 entity list.

    Rules:
    - Only Dimension/Fact/Reference/Bridge nodes are added (Report, Filter,
      Actor, BusinessRule, DataField, SystemModule are skipped).
    - The same forbidden-suffix filters as _validate_and_clean are applied
      so garbage names from the graph never reach the CDM.
    - Deduplication is case-insensitive.
    - Every surviving node is guaranteed to appear in the output — no LLM
      can silently drop it.
    """
    def _log(msg):
        if log: log(msg)

    known  = {e["name"].lower() for e in pass1}
    result = list(pass1)
    added  = 0

    for node in graph_nodes:
        cdm_type = _GRAPH_TYPE_MAP.get(node.get("type"))
        if cdm_type is None:
            continue  # not a CDM entity type

        name = node.get("id", "").strip()
        if not name:
            continue

        name_lower = name.lower()
        if name_lower in known:
            continue

        # Same deterministic correction applied to LLM entities — GraphRAG also
        # labels Sales/Profit nodes as "Dimension".
        cdm_type = _reclassify_type(name, cdm_type)

        # Apply same forbidden filters as _validate_and_clean
        if name_lower in FORBIDDEN_EXACT:
            continue
        if any(name_lower.endswith(s) for s in HARD_FORBIDDEN_SUFFIXES):
            continue
        if _FORBIDDEN_INFIX_RE.search(name_lower):
            continue
        if cdm_type != "reference" and any(
            name_lower.endswith(s) for s in SOFT_FORBIDDEN_SUFFIXES
        ):
            continue

        props = node.get("properties", {})
        description = props.get("description", props.get("name", ""))

        result.append({
            "name":             name,
            "type":             cdm_type,
            "description":      description,
            "attributes":       [],
            "source":           "GraphRAG",
            "ontology_matches": [],
        })
        known.add(name_lower)
        added += 1

    _log(f"  GraphRAG node merge: {added} new entities added (deterministic)")
    return result


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_and_clean(raw: list) -> list[dict]:
    seen   = set()
    result = []

    for e in raw:
        if not isinstance(e, dict):
            continue
        name = e.get("name", "").strip()
        if not name:
            continue

        # PascalCase
        if not re.match(r'^[A-Z][A-Za-z0-9]*$', name):
            print(f"[step2] Rejected (not PascalCase): {name}")
            continue

        name_lower = name.lower()

        # Normalise type FIRST — the forbidden filter below is type-aware.
        entity_type = e.get("type", "").lower().strip()
        if entity_type not in VALID_TYPES:
            if any(kw in name_lower for kw in [
                "fact","sale","transaction","payment","order","claim","usage","spend"
            ]):
                entity_type = "fact"
            elif any(kw in name_lower for kw in [
                "status","category","type","code","currency","country","reference"
            ]):
                entity_type = "reference"
            elif any(kw in name_lower for kw in ["bridge","junction","assoc"]):
                entity_type = "bridge"
            else:
                entity_type = "dimension"

        # Deterministic correction — override LLM mislabels (e.g. a Sales/Profit
        # process typed "dimension" becomes "fact"). Runs on every entity, not
        # just those with invalid types.
        entity_type = _reclassify_type(name, entity_type)

        # Forbidden filtering — whitelisted names bypass it entirely.
        if name_lower not in ALLOWED_EXACT_EXCEPTIONS:
            if name_lower in FORBIDDEN_EXACT:
                print(f"[step2] Rejected (forbidden exact): {name}")
                continue
            if any(name_lower.endswith(s) for s in HARD_FORBIDDEN_SUFFIXES):
                print(f"[step2] Rejected (report/view artifact): {name}")
                continue
            # Infix check — e.g. CurrentTop10SaleItems (ranking report, not a table)
            if _FORBIDDEN_INFIX_RE.search(name_lower):
                print(f"[step2] Rejected (ranking/top-N infix): {name}")
                continue
            # Soft suffixes (rate/ratio/metric/view…) are measures/attributes
            # unless the entity is a reference (lookup) table — keep those.
            if entity_type != "reference" and any(
                name_lower.endswith(s) for s in SOFT_FORBIDDEN_SUFFIXES
            ):
                print(f"[step2] Rejected (metric/attribute, not an entity): {name}")
                continue
            # Description-based filter: the LLM sometimes extracts a report/dashboard
            # artifact that has no forbidden suffix but whose own description calls it
            # a "report" or "dashboard" (e.g. "Current Sales Profit Contribution report").
            desc_lower = e.get("description", "").lower()
            if (desc_lower
                    and entity_type != "reference"
                    and re.search(r'\breport\b|\bdashboard\b', desc_lower)):
                print(f"[step2] Rejected (described as report/dashboard): {name}")
                continue

        # Deduplicate — keep richer entry
        if name.lower() in seen:
            for existing in result:
                if existing["name"].lower() == name.lower():
                    if not existing["description"] and e.get("description"):
                        existing["description"] = e["description"]
                    if len(e.get("attributes",[])) > len(existing.get("attributes",[])):
                        existing["attributes"] = e["attributes"]
            continue

        seen.add(name.lower())
        result.append({
            "name":             name,
            "type":             entity_type,
            "description":      e.get("description", ""),
            "attributes":       e.get("attributes", []),
            "source":           e.get("source", ""),
            "ontology_matches": [],
        })

    return result
