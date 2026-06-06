"""
Step 2 — Entity extraction — Two-pass redesign.

Pass 1 — Full document scan (single LLM call, full BRD text)
  The LLM receives the entire BRD text at once and extracts all
  entities in one holistic pass — same way a human expert would
  read the document. No chunking, no context loss.

Pass 2 — GraphRAG enrichment (optional, runs if GraphRAG context available)
  If GraphRAG produced a knowledge graph, a second LLM call merges
  the graph-discovered nodes into the Pass 1 entity list, adds any
  entities the graph found that Pass 1 missed, and validates types
  against the SKILL.md rules.

This two-pass design closes the gap between direct document reading
and chunked pipeline extraction.
"""

import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from agent.ollama_client import chat, extract_json
from agent.skill_loader import load_skill
try:
    from agent.oracle_rdm_seeder import query_oracle_rdm, COLLECTION_LDM as _RDM_LDM
    _ORACLE_RDM_AVAILABLE = True
except Exception:
    _ORACLE_RDM_AVAILABLE = False

SKILL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "skills", "SKILL.md"
)

# Suffixes that almost always mark a report/visualization artifact rather than
# a data entity — always rejected.
HARD_FORBIDDEN_SUFFIXES = {
    "report","dashboard","scorecard","analysis","overview","summary",
    "monitor","tracker","snapshot","analytics","portal","feed","digest",
    "listing","ranking","top10",
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
VALID_TYPES = {"dimension","fact","reference","bridge"}

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
    sections:         list  = None,
    on_log                  = None,
    max_chunks:       int   = 4,   # kept for API compat, not used in new design
) -> list[dict]:
    """
    Two-pass entity extraction.

    Pass 1: Single LLM call with the full BRD text → complete entity list.
    Pass 2: If GraphRAG context available, merge graph-discovered entities.
    """
    def log(msg):
        if on_log: on_log(msg)

    skill_text = load_skill(SKILL_PATH)

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

    # ── Pass 2 — GraphRAG enrichment ──────────────────────────────────────────
    if graphrag_context and len(graphrag_context) > 200:
        log("Pass 2 — GraphRAG enrichment (merging graph-discovered entities)…")

        # Summarise Pass 1 for the prompt
        pass1_summary = "\n".join(
            f"- {e['name']} ({e['type']}): {e['description']}"
            for e in pass1_entities
        )

        # Pass the full GraphRAG context — it already covers the whole document
        # (chunk-by-chunk) and is the richest full-coverage signal we have.
        graph_ctx = graphrag_context

        try:
            raw2 = chat(
                base_url=ollama_url,
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PASS2.format(skill=skill_text)},
                    {"role": "user",   "content": USER_PASS2.format(
                        pass1_entities=pass1_summary,
                        graphrag_context=graph_ctx,
                    )},
                ],
                temperature=temperature,
                format="json",
            )
            data2 = extract_json(raw2)
            items2 = data2.get("entities", []) if isinstance(data2, dict) else (data2 or [])
            pass2_entities = _validate_and_clean(items2)

            # Merge: add Pass 2 entities not already in Pass 1
            existing_names = {e["name"].lower() for e in pass1_entities}
            added = 0
            for e in pass2_entities:
                if e["name"].lower() not in existing_names:
                    pass1_entities.append(e)
                    existing_names.add(e["name"].lower())
                    added += 1

            log(f"  Pass 2 added {added} new entities from GraphRAG context")
            log(f"  Total after merge: {len(pass1_entities)} entities")

        except Exception as e:
            log(f"  Pass 2 failed (using Pass 1 results only): {e}")
    else:
        log("  Pass 2 skipped — no GraphRAG context available")

    return pass1_entities


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

        # Forbidden filtering — whitelisted names bypass it entirely.
        if name_lower not in ALLOWED_EXACT_EXCEPTIONS:
            if name_lower in FORBIDDEN_EXACT:
                print(f"[step2] Rejected (forbidden exact): {name}")
                continue
            if any(name_lower.endswith(s) for s in HARD_FORBIDDEN_SUFFIXES):
                print(f"[step2] Rejected (report/view artifact): {name}")
                continue
            # Soft suffixes (rate/ratio/metric/view…) are measures/attributes
            # unless the entity is a reference (lookup) table — keep those.
            if entity_type != "reference" and any(
                name_lower.endswith(s) for s in SOFT_FORBIDDEN_SUFFIXES
            ):
                print(f"[step2] Rejected (metric/attribute, not an entity): {name}")
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
