"""
Step 2 — Entity extraction
Loads the domain SKILL.md to enforce extraction rules as guardrails.
Two focused LLM calls: dimensions/references/bridges + facts.
"""

import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from agent.ollama_client import chat, extract_json
from agent.skill_loader import load_skill

SKILL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills", "SKILL.md")

# ── Forbidden name suffixes (from SKILL.md rule 3) ───────────────────────────
FORBIDDEN_SUFFIXES = {
    "report", "dashboard", "summary", "analysis", "view", "overview",
    "scorecard", "monitor", "tracker", "insight", "snapshot", "filter",
    "prompt", "top10", "kpi", "metric", "rate", "ratio", "percentage",
    "analytics", "portal", "feed", "digest", "listing", "ranking"
}

FORBIDDEN_EXACT = {
    "top10", "filter", "prompt", "kpi", "metric", "report",
    "dashboard", "summary", "analysis", "view", "data", "information"
}

VALID_TYPES = {"dimension", "fact", "reference", "bridge"}

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_DIMENSIONS = """{skill}

You are a senior data architect. Extract DIMENSION, REFERENCE and BRIDGE entities only.

DIMENSION = descriptive axis (Customer, Product, Time, Geography, Channel, Employee)
REFERENCE = small lookup table (Currency, Status, Category, Country)
BRIDGE    = resolves M:N between dimensions (CustomerProduct, EmployeeRole)

FORBIDDEN — do NOT return:
- Report names (SalesReport, CMODashboard)
- Dashboard names (ExecutiveDashboard)
- Filter or prompt names (Top10Filter, DateRangePrompt)
- Metric or KPI names (RevenueGrowth, NPS, ARPU)
- Names ending in: Report, Dashboard, Filter, Prompt, Analysis, Summary, View, KPI, Metric, Rate, Ratio

Respond ONLY with valid JSON, no explanation, no markdown."""

SYSTEM_FACTS = """{skill}

You are a senior data architect. Extract FACT entities only.

FACT = a measurable event or transaction with numeric metrics.
Examples: Sale, Transaction, Payment, Order, SpendingFact, ClaimFact, UsageFact.

FORBIDDEN — do NOT return:
- Report names, dashboard names, filter names, metric names
- Dimension entities (Customer, Product, Time etc.)

Respond ONLY with valid JSON, no explanation, no markdown."""

USER_TEMPLATE = """Extract {entity_category} entities from this BRD text.

For each entity return:
- "name": PascalCase noun, singular (e.g. "CustomerDimension", "SaleFact")
- "type": one of [{valid_types}]
- "description": one sentence — what business concept this represents
- "attributes": up to 5 key fields (no report names, no metric names)
- "source": section heading or phrase from BRD that implies this entity

RULES:
- Name MUST be PascalCase
- Name MUST be singular
- Name MUST NOT end in: Report, Dashboard, Filter, Prompt, Top10, KPI, Metric, Rate, Analysis, Summary, View
- Only return genuine data entities, not reports, dashboards, filters or metrics

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

    skill_text = load_skill(SKILL_PATH)
    chunk = brd_text[:4000] if len(brd_text) > 4000 else brd_text

    all_entities = []

    # ── Call A — Dimensions, References, Bridges ──────────────────────────────
    try:
        raw_a = chat(
            base_url=ollama_url, model=model,
            messages=[
                {"role": "system", "content": SYSTEM_DIMENSIONS.format(skill=skill_text)},
                {"role": "user",   "content": USER_TEMPLATE.format(
                    entity_category="DIMENSION, REFERENCE, and BRIDGE",
                    valid_types="dimension, reference, bridge",
                    brd_text=chunk,
                )},
            ],
            temperature=temperature, format="json",
        )
        data_a = extract_json(raw_a)
        all_entities += (data_a.get("entities", []) if isinstance(data_a, dict) else data_a)
    except Exception as e:
        print(f"[step2] Call A failed: {e}")

    # ── Call B — Facts ────────────────────────────────────────────────────────
    try:
        raw_b = chat(
            base_url=ollama_url, model=model,
            messages=[
                {"role": "system", "content": SYSTEM_FACTS.format(skill=skill_text)},
                {"role": "user",   "content": USER_TEMPLATE.format(
                    entity_category="FACT",
                    valid_types="fact",
                    brd_text=chunk,
                )},
            ],
            temperature=temperature, format="json",
        )
        data_b = extract_json(raw_b)
        all_entities += (data_b.get("entities", []) if isinstance(data_b, dict) else data_b)
    except Exception as e:
        print(f"[step2] Call B failed: {e}")

    return _validate_and_clean(all_entities)


def _validate_and_clean(raw: list) -> list[dict]:
    """
    Apply SKILL.md guardrails to filter and normalise extracted entities.
    Rejects forbidden names, enforces PascalCase, deduplicates.
    """
    seen   = set()
    result = []

    for e in raw:
        if not isinstance(e, dict):
            continue

        name = e.get("name", "").strip()
        if not name:
            continue

        # Enforce PascalCase — skip if fails
        if not re.match(r'^[A-Z][A-Za-z0-9]*$', name):
            print(f"[step2] Rejected (not PascalCase): {name}")
            continue

        # Reject forbidden exact matches
        if name.lower() in FORBIDDEN_EXACT:
            print(f"[step2] Rejected (forbidden exact): {name}")
            continue

        # Reject forbidden suffixes
        name_lower = name.lower()
        if any(name_lower.endswith(s) for s in FORBIDDEN_SUFFIXES):
            print(f"[step2] Rejected (forbidden suffix): {name}")
            continue

        # Normalise type
        entity_type = e.get("type", "dimension").lower()
        if entity_type not in VALID_TYPES:
            # Best-guess reclassification
            if any(kw in name_lower for kw in ["fact","sale","transaction","payment","order","claim","usage","spend"]):
                entity_type = "fact"
            elif any(kw in name_lower for kw in ["status","category","type","code","currency","country"]):
                entity_type = "reference"
            else:
                entity_type = "dimension"

        # Deduplicate
        if name.lower() in seen:
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
