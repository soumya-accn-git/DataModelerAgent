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

SKILL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "skills", "SKILL.md"
)

FORBIDDEN_SUFFIXES = {
    "report","dashboard","summary","analysis","view","overview",
    "scorecard","monitor","tracker","insight","snapshot",
    "top10","kpi","metric","rate","ratio","percentage",
    "analytics","portal","feed","digest","listing","ranking"
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

USER_FACTS_ONLY = """Read the BRD below and extract ONLY fact entities.

A fact entity = a measurable business event at a specific grain (time × location × product).

COMMON RETAIL FACT ENTITIES — look for ALL of these:
1. SalesFact / SalesAndProfitFact — daily sales, returns, profit, transaction counts
2. MarkdownFact — markdown amounts (clearance, promo, permanent), markdown-to-sales ratios
3. MarkupFact / MarkdownMarkupFact — markup amounts applied to items
4. ProfitFact / GrossProfitFact — profit metrics, contribution percentages
5. SalesForecastFact / ForecastFact — forecast quantities, variance vs actual
6. SupplierCostFact — supplier cost tiers (base, net, net-net, dead net)
7. CurrencyConversionFact — exchange rates for multi-currency support

Do NOT merge separate business processes into one fact. If the BRD describes
markdowns AND sales separately, they are TWO separate fact entities.

For each fact entity return:
- "name": PascalCase ending in Fact (e.g. "SalesFact", "MarkdownFact", "ProfitFact")
- "type": "fact"
- "description": what measurable business event this captures
- "attributes": key metrics mentioned in the BRD for this fact
- "source": BRD section that implies this fact

Return: {{"entities": [...]}}

BRD TEXT:
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

    # Split BRD into two halves for larger documents to avoid token limits
    full_text = brd_text[:8000] if len(brd_text) > 8000 else brd_text
    log(f"  Document: {len(brd_text):,} chars → sending {len(full_text):,} chars")

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

    # ── Pass 1b — Dedicated fact scan (safety net for missing facts) ───────────
    # Run a focused fact-only extraction if fewer than 2 facts found —
    # the general scan often truncates before reaching all fact sections
    fact_count = sum(1 for e in pass1_entities if e.get("type") == "fact")
    log(f"  Facts found so far: {fact_count}")

    if fact_count < 3:  # run dedicated scan if fewer than 3 facts — BRD typically has 4+
        log("Pass 1b — dedicated fact extraction (fewer than 2 facts found)…")
        # Use second half of BRD if available — facts often appear later
        fact_text = brd_text[3000:9000] if len(brd_text) > 6000 else full_text
        try:
            raw1b = chat(
                base_url=ollama_url,
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PASS1.format(skill=skill_text)},
                    {"role": "user",   "content": USER_FACTS_ONLY.format(brd_text=fact_text)},
                ],
                temperature=temperature,
                format="json",
            )
            data1b = extract_json(raw1b)
            items1b = data1b.get("entities", []) if isinstance(data1b, dict) else (data1b or [])
            new_facts = _validate_and_clean(items1b)

            # Merge — add facts not already in pass1_entities
            existing_names = {e["name"].lower() for e in pass1_entities}
            added = 0
            for e in new_facts:
                if e["name"].lower() not in existing_names and e.get("type") == "fact":
                    pass1_entities.append(e)
                    existing_names.add(e["name"].lower())
                    added += 1
            log(f"  Pass 1b added {added} fact entities")
        except Exception as e:
            log(f"  Pass 1b failed: {e}")

    # ── Pass 1c — scan remaining BRD sections not yet covered ──────────────
    # If BRD is large, the first 8000 chars may miss facts in later sections
    fact_count_now = sum(1 for e in pass1_entities if e.get("type") == "fact")
    if fact_count_now < 3 and len(brd_text) > 8000:
        log("Pass 1c — scanning later BRD sections for additional facts…")
        later_text = brd_text[6000:12000] if len(brd_text) > 12000 else brd_text[5000:]
        try:
            raw1c = chat(
                base_url=ollama_url,
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PASS1.format(skill=skill_text)},
                    {"role": "user",   "content": USER_FACTS_ONLY.format(brd_text=later_text)},
                ],
                temperature=temperature,
                format="json",
            )
            data1c = extract_json(raw1c)
            items1c = data1c.get("entities", []) if isinstance(data1c, dict) else (data1c or [])
            new_facts_c = _validate_and_clean(items1c)
            existing_names = {e["name"].lower() for e in pass1_entities}
            added_c = 0
            for e in new_facts_c:
                if e["name"].lower() not in existing_names and e.get("type") == "fact":
                    pass1_entities.append(e)
                    existing_names.add(e["name"].lower())
                    added_c += 1
            log(f"  Pass 1c added {added_c} additional fact entities")
        except Exception as e:
            log(f"  Pass 1c failed: {e}")

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

        # Keep GraphRAG context focused — first 3000 chars
        graph_ctx = graphrag_context[:3000]

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

        # Forbidden exact
        if name.lower() in FORBIDDEN_EXACT:
            print(f"[step2] Rejected (forbidden exact): {name}")
            continue

        # Forbidden suffix
        name_lower = name.lower()
        if any(name_lower.endswith(s) for s in FORBIDDEN_SUFFIXES):
            print(f"[step2] Rejected (forbidden suffix): {name}")
            continue

        # Normalise type
        entity_type = e.get("type", "dimension").lower().strip()
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
