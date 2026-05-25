"""
Step 2 — Entity extraction
Uses the LLM to identify business entities from the BRD text,
including analytical/reporting entities from functional requirements sections.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from agent.ollama_client import chat, extract_json

SYSTEM_PROMPT = """You are a senior data architect. Your task is to extract ALL
business entities from a Business Requirements Document (BRD).

You must extract TWO categories of entities:

CATEGORY 1 — Operational entities
Distinct real-world concepts the business tracks or manages.
Examples: Customer, Order, Product, Invoice, Employee, Supplier.

CATEGORY 2 — Analytical / Reporting entities
Concepts found in reporting, analysis, and BI sections of the BRD. These include:
- Report or analysis objects (e.g. SalesReport, InventoryAnalysis)
- Dimensions mentioned in "Dimensions Required" sections (e.g. TimeDimension, GeographyDimension, ProductDimension)
- Metrics or KPIs mentioned in "Key Metrics" sections (e.g. RevenueMetric, CustomerSatisfactionScore)
- Filters or prompts mentioned in "Filters and Prompts" sections (e.g. DateRangeFilter, RegionFilter)
- Business decisions or purposes described in analysis sections (e.g. BusinessDecision, AnalysisReport)

IMPORTANT: Do NOT skip any section of the BRD. Specifically look for sections titled:
"Functional Requirements", "Analysis Reports", "Business Purpose",
"Key Business Decisions", "Dimensions Required", "Key Metrics",
"Filters and Prompts", "Reporting Requirements", "BI Requirements".
Every concept named in those sections must become an entity.

You must respond ONLY with a valid JSON object, no explanation, no markdown.
"""

USER_TEMPLATE = """
Analyse the following BRD text and extract ALL business entities — both
operational entities AND analytical/reporting entities.

Pay special attention to any sections about:
- Functional requirements and analysis reports
- Business purpose and key business decisions
- Dimensions required
- Key metrics and KPIs
- Filters and prompts
- Reporting or BI requirements

For each entity provide:
- "name": PascalCase entity name (e.g. "SalesReport", "TimeDimension", "RevenueMetric")
- "type": one of [core, supporting, reference, event, dimension, metric, report, filter]
  - core: central operational business entity
  - supporting: supports core entities
  - reference: lookup or classification
  - event: business event or transaction
  - dimension: analytical dimension (time, geography, product, customer etc.)
  - metric: KPI or measurable business metric
  - report: a report, analysis, or dashboard entity
  - filter: a filter, prompt, or query parameter used in reporting
- "description": one sentence describing what this entity represents
- "attributes": list of likely key attributes (max 6)
- "source": the exact section heading or phrase from the BRD that implies this entity

Return a JSON object with a single key "entities" containing a list.
Include EVERY entity — do not skip analytical or reporting concepts.

BRD TEXT:
---
{brd_text}
---

JSON response:
"""


def extract_entities(
    brd_text: str,
    ollama_url: str,
    model: str,
    temperature: float = 0.1,
) -> list[dict]:
    """
    Returns a list of entity dicts:
    {name, type, description, attributes, source}
    Covers both operational and analytical/reporting entities.
    """
    # Chunk if very long — keep to ~6000 chars for smaller models
    text_chunk = brd_text[:6000] if len(brd_text) > 6000 else brd_text

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(brd_text=text_chunk)},
    ]

    raw = chat(
        base_url=ollama_url,
        model=model,
        messages=messages,
        temperature=temperature,
        format="json",
    )

    data = extract_json(raw)

    if isinstance(data, list):
        entities = data
    elif isinstance(data, dict):
        entities = data.get("entities", [])
    else:
        entities = []

    # Valid entity types including new analytical types
    VALID_TYPES = {
        "core", "supporting", "reference", "event",
        "dimension", "metric", "report", "filter"
    }

    # Normalise
    cleaned = []
    for e in entities:
        if not isinstance(e, dict):
            continue
        name = e.get("name", "").strip()
        if not name:
            continue
        entity_type = e.get("type", "core")
        if entity_type not in VALID_TYPES:
            entity_type = "core"
        cleaned.append({
            "name": name,
            "type": entity_type,
            "description": e.get("description", ""),
            "attributes": e.get("attributes", []),
            "source": e.get("source", ""),
            "ontology_matches": [],  # filled in step 4
        })

    return cleaned
