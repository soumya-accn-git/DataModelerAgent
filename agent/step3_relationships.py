"""
Step 3 — Relationship detection — Two-pass redesign.

Pass 1 — Full entity list + full BRD text (single LLM call)
  Detects all relationships between the extracted entities using
  the full BRD as context — no truncation, holistic view.

Pass 2 — GraphRAG enrichment
  If GraphRAG produced graph relationships, merges them in to catch
  any relationships the Pass 1 LLM missed.
"""

import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from agent.ollama_client import chat, extract_json

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
    on_log                  = None,
) -> list[dict]:
    """Two-pass relationship detection."""

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

    # ── Pass 2 — GraphRAG enrichment ──────────────────────────────────────────
    if graphrag_context and "## Extracted Knowledge Graph Relationships" in graphrag_context:
        log("Pass 2 — merging GraphRAG relationships…")

        # Extract just the relationships section from GraphRAG context
        graph_rels_text = ""
        parts = graphrag_context.split("## Extracted Knowledge Graph Relationships")
        if len(parts) > 1:
            graph_rels_text = parts[1].split("##")[0].strip()[:2000]

        if graph_rels_text:
            pass1_summary = "\n".join(
                f"- {r['from_entity']} --[{r['label']}]--> {r['to_entity']} [{r['cardinality']}]"
                for r in pass1_rels
            )
            try:
                raw2 = chat(
                    base_url=ollama_url,
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PASS2},
                        {"role": "user",   "content": USER_PASS2.format(
                            pass1_rels=pass1_summary,
                            graph_rels=graph_rels_text,
                            entity_names=", ".join(sorted(entity_names)),
                        )},
                    ],
                    temperature=temperature,
                    format="json",
                )
                data2 = extract_json(raw2)
                items2 = data2.get("relationships", []) if isinstance(data2, dict) else []
                merged = _validate_rels(items2, entity_names)

                # Union: NEVER drop a Pass 1 relationship. Start from all of
                # Pass 1 and add only genuinely new ones from the merge — the
                # model occasionally omits inputs when asked to "merge".
                existing_keys = {
                    (r["from_entity"], r["to_entity"], r["label"])
                    for r in pass1_rels
                }
                union = list(pass1_rels)
                added = 0
                for r in merged:
                    key = (r["from_entity"], r["to_entity"], r["label"])
                    if key not in existing_keys:
                        union.append(r)
                        existing_keys.add(key)
                        added += 1
                log(f"  Pass 2 added {added} relationships from GraphRAG")
                return union
            except Exception as e:
                log(f"  Pass 2 failed (using Pass 1 only): {e}")
    else:
        log("  Pass 2 skipped — no GraphRAG relationship context")

    return pass1_rels


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
