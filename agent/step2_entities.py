"""
Step 2 — Entity extraction
Two focused LLM calls:
  Call A — operational entities (fast, short prompt)
  Call B — analytical/reporting entities (fast, short prompt)
Results are merged and deduplicated.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from agent.ollama_client import chat, extract_json

# ── Call A — Operational entities ────────────────────────────────────────────

SYSTEM_A = """You are a data architect. Extract operational business entities from a BRD.
Operational entities are things the business tracks: Customer, Order, Product, Invoice, Employee, etc.
Respond ONLY with valid JSON, no explanation."""

USER_A = """Extract all operational business entities from this BRD text.

For each entity return:
- "name": PascalCase (e.g. "CustomerOrder")
- "type": one of [core, supporting, reference, event]
- "description": one sentence
- "attributes": up to 5 key fields
- "source": phrase from BRD that implies this entity

Return: {{"entities": [...]}}

BRD TEXT:
---
{brd_text}
---
JSON:"""

# ── Call B — Analytical entities ─────────────────────────────────────────────

SYSTEM_B = """You are a data architect. Extract analytical and reporting entities from a BRD.
Look specifically for: Reports, Dimensions, Metrics/KPIs, Filters, Business Decisions, Analysis sections.
Respond ONLY with valid JSON, no explanation."""

USER_B = """Extract all analytical and reporting entities from this BRD text.

Look for sections titled: Functional Requirements, Analysis Reports, Business Purpose,
Key Business Decisions, Dimensions Required, Key Metrics, Filters and Prompts.

For each entity return:
- "name": PascalCase (e.g. "SalesReport", "TimeDimension", "RevenueMetric")
- "type": one of [dimension, metric, report, filter]
- "description": one sentence
- "attributes": up to 5 key fields
- "source": section heading or phrase from BRD

Return: {{"entities": [...]}}

BRD TEXT:
---
{brd_text}
---
JSON:"""


def extract_entities(
    brd_text: str,
    ollama_url: str,
    model: str,
    temperature: float = 0.1,
) -> list[dict]:
    """
    Returns merged list of operational + analytical entity dicts.
    """
    chunk = brd_text[:4000] if len(brd_text) > 4000 else brd_text

    VALID_TYPES = {
        "core", "supporting", "reference", "event",
        "dimension", "metric", "report", "filter"
    }

    all_entities = []

    # ── Call A — operational ─────────────────────────────────────────────────
    try:
        raw_a = chat(
            base_url=ollama_url,
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_A},
                {"role": "user",   "content": USER_A.format(brd_text=chunk)},
            ],
            temperature=temperature,
            format="json",
        )
        data_a = extract_json(raw_a)
        if isinstance(data_a, dict):
            all_entities += data_a.get("entities", [])
        elif isinstance(data_a, list):
            all_entities += data_a
    except Exception as e:
        print(f"[step2] Call A failed: {e}")

    # ── Call B — analytical ──────────────────────────────────────────────────
    try:
        raw_b = chat(
            base_url=ollama_url,
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_B},
                {"role": "user",   "content": USER_B.format(brd_text=chunk)},
            ],
            temperature=temperature,
            format="json",
        )
        data_b = extract_json(raw_b)
        if isinstance(data_b, dict):
            all_entities += data_b.get("entities", [])
        elif isinstance(data_b, list):
            all_entities += data_b
    except Exception as e:
        print(f"[step2] Call B failed: {e}")

    # ── Normalise and deduplicate ─────────────────────────────────────────────
    seen = set()
    cleaned = []
    for e in all_entities:
        if not isinstance(e, dict):
            continue
        name = e.get("name", "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        entity_type = e.get("type", "core")
        if entity_type not in VALID_TYPES:
            entity_type = "core"
        cleaned.append({
            "name": name,
            "type": entity_type,
            "description": e.get("description", ""),
            "attributes": e.get("attributes", []),
            "source": e.get("source", ""),
            "ontology_matches": [],
        })

    return cleaned
