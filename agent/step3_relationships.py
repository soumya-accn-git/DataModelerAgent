"""
Step 3 — Relationship detection
Uses the LLM to infer relationships between extracted entities.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from agent.ollama_client import chat, extract_json
import json

SYSTEM_PROMPT = """You are a senior data architect. Your task is to identify
relationships between business entities extracted from a Business Requirements Document.

Focus on meaningful business relationships: ownership, composition, association,
and dependency. Identify cardinality accurately.

You must respond ONLY with a valid JSON object, no explanation, no markdown.
"""

USER_TEMPLATE = """
Given the following list of business entities and the original BRD text,
identify all meaningful relationships between the entities.

ENTITIES:
{entity_list}

BRD TEXT:
---
{brd_text}
---
Important: Make sure EVERY entity in the list appears in at least one relationship.
Do not skip any entity. Every entity must connect to at least one other entity.
---
For each relationship provide:
- "from_entity": name of the source entity
- "to_entity": name of the target entity
- "label": a short verb phrase describing the relationship (e.g. "places", "contains", "belongs to")
- "cardinality": one of ["1:1", "1:N", "N:1", "M:N"]
- "required": true if the relationship is mandatory, false if optional
- "description": one sentence explaining the business meaning
- "ontology_type": leave empty string "" (will be filled by ontology step)

Return a JSON object with a single key "relationships" containing a list.

JSON response:
"""


def detect_relationships(
    entities: list[dict],
    brd_text: str,
    ollama_url: str,
    model: str,
    temperature: float = 0.1,
) -> list[dict]:
    """
    Returns a list of relationship dicts.
    """
    entity_names = [e["name"] for e in entities]
    entity_summary = "\n".join(
        f"- {e['name']} ({e['type']}): {e['description']}" for e in entities
    )

    text_chunk = brd_text[:4000] if len(brd_text) > 4000 else brd_text

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(
                entity_list=entity_summary,
                brd_text=text_chunk,
            ),
        },
    ]

    raw = chat(
        base_url=ollama_url,
        model=model,
        messages=messages,
        temperature=temperature,
        format="json",
    )
    print("RAW RELATIONSHIP RESPONSE:", raw[:2000])
    
    data = extract_json(raw)

    if isinstance(data, list):
        relationships = data
    elif isinstance(data, dict):
        relationships = data.get("relationships", [])
    else:
        relationships = []

    # Normalise and validate — only keep relationships between known entities
    entity_set = set(entity_names)
    cleaned = []
    seen = set()

    for r in relationships:
        if not isinstance(r, dict):
            continue
        from_e = r.get("from_entity", "").strip()
        to_e = r.get("to_entity", "").strip()
        label = r.get("label", "relates to").strip()

        if not from_e or not to_e:
            continue

        # Fuzzy match against known entities
        from_e = _fuzzy_match(from_e, entity_set) or from_e
        to_e = _fuzzy_match(to_e, entity_set) or to_e

        key = (from_e, to_e, label)
        if key in seen:
            continue
        seen.add(key)

        cleaned.append({
            "from_entity": from_e,
            "to_entity": to_e,
            "label": label,
            "cardinality": r.get("cardinality", "1:N"),
            "required": r.get("required", False),
            "description": r.get("description", ""),
            "ontology_type": "",
        })

    return cleaned


def _fuzzy_match(name: str, entity_set: set) -> str | None:
    name_lower = name.lower().strip()
    # Exact match
    for e in entity_set:
        if e.lower() == name_lower:
            return e
    # Singular/plural match (strip trailing 's')
    for e in entity_set:
        if e.lower().rstrip('s') == name_lower.rstrip('s'):
            return e
    # Prefix match (at least 4 chars)
    for e in entity_set:
        min_len = min(len(name_lower), 4)
        if e.lower().startswith(name_lower[:min_len]):
            return e
    return None