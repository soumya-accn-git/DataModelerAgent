"""
Step 3 — Relationship detection — Pass 1 LLM + deterministic GraphRAG merge.

Pass 1 — Full entity list + full BRD text (single LLM call)
  Detects all relationships between the extracted entities using
  the full BRD as context — no truncation, holistic view.

Pass 2 — Deterministic GraphRAG merge (code, not LLM)
  Iterates the structured graph_rels list and adds any relationship
  where both endpoints are valid CDM entities and the pair is not
  already covered by Pass 1.  Every such relationship is guaranteed
  to appear in the output regardless of LLM behaviour.
"""

import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from src.tools.ollama_client import chat, extract_json

# Maps GraphRAG relationship types to human-readable CDM labels
_GRAPH_REL_LABEL = {
    "HAS_DIMENSION":  "has dimension",
    "HAS_FACT":       "has fact",
    "RELATES_TO":     "relates to",
    "FEEDS":          "feeds",
    "DEPENDS_ON":     "depends on",
    "VALIDATES":      "validates",
    "TRIGGERS":       "triggers",
    "ACCESSES":       "accesses",
    "FILTERS_BY":     "filters by",
    "BELONGS_TO":     "belongs to",
    "FULFILLS":       "fulfills",
    "CLASSIFIED_BY":  "classified by",
}

SYSTEM_PASS1 = """You are an experienced subject matter expert in Data Modeling, specifically in Dimensional Modeling and able to precisely design data models Ontology and Graph RAG. Use your knowledge and experience in modeling the DWH schema for CDM and LDM.

Detect all relationships between CDM entities extracted from a Business Requirements Document.

Rules:
- Only create relationships between entities in the provided list
- Dimension → Fact: cardinality 1:N
- Fact → Dimension: cardinality N:1
- Reference → Dimension or Fact: cardinality 1:N
- Bridge → Dimension: cardinality N:1 (both sides)
- Use verb labels: "classifies", "locates", "dates", "feeds", "belongs to"
- Identify cardinality accurately: 1:1, 1:N, N:1, M:N

Respond ONLY with valid JSON, no explanation, no markdown."""

USER_PASS1 = """Detect all relationships between these entities based on the BRD.

ENTITIES:
{entity_list}

BRD TEXT:
---
{brd_text}
---

For each relationship return:
- "from_entity": source entity name (must be in entity list)
- "to_entity": target entity name (must be in entity list)
- "label": short verb phrase (e.g. "classifies", "dates", "belongs to")
- "cardinality": one of [1:1, 1:N, N:1, M:N]
- "required": true if mandatory
- "description": one sentence — business meaning

Return: {{"relationships": [...]}}
JSON:"""

SYSTEM_PASS2 = """You are an experienced subject matter expert in Data Modeling, specifically in Dimensional Modeling and able to precisely design data models Ontology and Graph RAG. Use your knowledge and experience in modeling the DWH schema for CDM and LDM.

Merge relationship lists.
Add graph-discovered relationships that are missing from the existing list.
Only include relationships where BOTH entities exist in the entity list.
Respond ONLY with valid JSON."""

USER_PASS2 = """Merge these two relationship sources into one complete list.

EXISTING RELATIONSHIPS (Pass 1):
{pass1_rels}

GRAPHRAG RELATIONSHIPS (from knowledge graph):
{graph_rels}

VALID ENTITY NAMES:
{entity_names}

Return the COMPLETE merged list — keep all Pass 1 relationships,
add GraphRAG relationships where both entities are valid:
{{"relationships": [...]}}
JSON:"""


def detect_relationships(
    entities:         list[dict],
    brd_text:         str,
    ollama_url:       str,
    model:            str,
    temperature:      float = 0.1,
    graphrag_context: str   = "",
    graph_rels:       list  = None,   # structured rels from step2_graphrag
    on_log                  = None,
) -> list[dict]:
    """Pass 1 LLM detection + deterministic GraphRAG merge."""

    def log(msg):
        if on_log: on_log(msg)

    entity_names = {e["name"] for e in entities}
    entity_list  = "\n".join(
        f"- {e['name']} ({e['type']}): {e['description']}"
        for e in entities
    )

    # ── Pass 1 — Full document ────────────────────────────────────────────────
    log("Pass 1 — full document relationship detection…")
    # Send the ENTIRE BRD — num_ctx is now large enough (see ollama_client), so
    # relationships described in later sections are no longer cut off.
    source_text = brd_text

    pass1_rels = []
    try:
        raw1 = chat(
            base_url=ollama_url,
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PASS1},
                {"role": "user",   "content": USER_PASS1.format(
                    entity_list=entity_list,
                    brd_text=source_text,
                )},
            ],
            temperature=temperature,
            format="json",
        )
        data1 = extract_json(raw1)
        items = data1.get("relationships", []) if isinstance(data1, dict) else []
        pass1_rels = _validate_rels(items, entity_names)
        log(f"  Pass 1 found {len(pass1_rels)} relationships")
    except Exception as e:
        log(f"  Pass 1 failed: {e}")

    # ── Pass 2 — Deterministic GraphRAG merge ────────────────────────────────
    if graph_rels:
        return _merge_graph_rels(pass1_rels, graph_rels, entity_names, log)
    else:
        log("  Pass 2 skipped — no structured graph_rels available")
        return pass1_rels


def _merge_graph_rels(
    pass1: list[dict],
    graph_rels: list[dict],
    entity_names: set,
    log=None,
) -> list[dict]:
    """
    Code-based set-union of GraphRAG relationships into Pass 1 results.

    Rules:
    - Both source and target must be valid CDM entity names (fuzzy-matched).
    - Pairs already covered by Pass 1 are skipped (keyed on from+to,
      direction-sensitive).
    - Every surviving relationship is guaranteed in the output.
    """
    def _log(msg):
        if log: log(msg)

    seen   = {(r["from_entity"], r["to_entity"]) for r in pass1}
    result = list(pass1)
    added  = 0

    for rel in graph_rels:
        src = _fuzzy_match(rel.get("source", ""), entity_names) or rel.get("source", "")
        tgt = _fuzzy_match(rel.get("target", ""), entity_names) or rel.get("target", "")

        if src not in entity_names or tgt not in entity_names:
            continue  # at least one endpoint not in the CDM entity list

        if (src, tgt) in seen:
            continue  # already covered

        rel_type = rel.get("type", "RELATES_TO")
        label    = _GRAPH_REL_LABEL.get(rel_type, rel_type.lower().replace("_", " "))

        result.append({
            "from_entity":   src,
            "to_entity":     tgt,
            "label":         label,
            "cardinality":   "1:N",
            "required":      False,
            "description":   f"GraphRAG-discovered: {src} {label} {tgt}",
            "ontology_type": "",
            "source":        "GraphRAG",
        })
        seen.add((src, tgt))
        added += 1

    _log(f"  GraphRAG rel merge: {added} new relationships added (deterministic)")
    return result


def _validate_rels(raw: list, entity_names: set) -> list[dict]:
    seen   = set()
    result = []

    for r in raw:
        if not isinstance(r, dict):
            continue
        from_e = r.get("from_entity", "").strip()
        to_e   = r.get("to_entity", "").strip()
        label  = r.get("label", "relates to").strip()

        if not from_e or not to_e:
            continue

        # Fuzzy match against known entities
        from_e = _fuzzy_match(from_e, entity_names) or from_e
        to_e   = _fuzzy_match(to_e, entity_names) or to_e

        # Both must be valid entities
        if from_e not in entity_names or to_e not in entity_names:
            continue

        key = (from_e, to_e, label)
        if key in seen:
            continue
        seen.add(key)

        result.append({
            "from_entity": from_e,
            "to_entity":   to_e,
            "label":       label,
            "cardinality": r.get("cardinality", "1:N"),
            "required":    r.get("required", False),
            "description": r.get("description", ""),
            "ontology_type": "",
        })

    return result


def _fuzzy_match(name: str, entity_names: set) -> str | None:
    name_lower = name.lower().strip()
    for e in entity_names:
        if e.lower() == name_lower:
            return e
    for e in entity_names:
        if e.lower().rstrip("s") == name_lower.rstrip("s"):
            return e
    for e in entity_names:
        if len(name_lower) >= 4 and e.lower().startswith(name_lower[:4]):
            return e
    return None
