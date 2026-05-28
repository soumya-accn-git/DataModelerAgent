"""
Step 5 — CDM generation
Assembles the final Conceptual Data Model from entities and relationships.
Provides export helpers: Mermaid erDiagram and JSON-LD.
"""

import re


def build_cdm(parsed_doc: dict, entities: list[dict], relationships: list[dict]) -> dict:
    return {
        "document_title": _infer_title(parsed_doc),
        "entities": entities,
        "relationships": relationships,
        "stats": {
            "entity_count":      len(entities),
            "relationship_count": len(relationships),
            "section_count":     len(parsed_doc.get("sections", [])),
        },
    }


def _infer_title(parsed_doc: dict) -> str:
    sections = parsed_doc.get("sections", [])
    return sections[0].get("heading", "Business Requirements") if sections else "Business Requirements"


# ── Mermaid export ────────────────────────────────────────────────────────────

_CARDINALITY_MAP = {
    "1:1": ("||", "||"),
    "1:N": ("||", "o{"),
    "N:1": ("o{", "||"),
    "M:N": ("}o", "o{"),
}


def result_to_mermaid(result: dict) -> str:
    lines = ["erDiagram"]

    entities      = result.get("entities", [])
    relationships = result.get("relationships", [])

    # Collect valid entity names for relationship filtering
    valid_names = {_safe_name(e["name"]) for e in entities}

    # Entity blocks — name only, no attributes (CDM level)
    for e in entities:
        name = _safe_name(e["name"])
        if not name:
            continue
        lines.append(f"  {name} {{")
        lines.append(f"    string description")
        lines.append("  }")

    lines.append("")

    # Relationships
    seen = set()
    for r in relationships:
        from_e = _safe_name(r.get("from_entity", ""))
        to_e   = _safe_name(r.get("to_entity", ""))
        label  = _safe_label(r.get("label", "relates_to"))
        card   = r.get("cardinality", "1:N")

        if not from_e or not to_e:
            continue
        # Only draw relationships between known entities
        if from_e not in valid_names or to_e not in valid_names:
            continue

        key = (from_e, to_e, label)
        if key in seen:
            continue
        seen.add(key)

        left, right = _CARDINALITY_MAP.get(card, ("||", "o{"))
        connector   = "--" if r.get("required", False) else ".."

        lines.append(f'  {from_e} {left}{connector}{right} {to_e} : "{label}"')

    return "\n".join(lines)


def _safe_name(name: str) -> str:
    """
    Convert entity name to Mermaid-safe identifier.
    Strips everything except letters and digits — no underscores,
    no special chars, must start with a letter, max 40 chars.
    """
    if not name:
        return ""
    # Replace common separators with nothing
    clean = name.replace(" ", "").replace("_", "").replace("-", "").replace(".", "")
    # Keep only letters and digits
    clean = re.sub(r"[^A-Za-z0-9]", "", clean)
    # Must start with a letter
    if clean and not clean[0].isalpha():
        clean = "E" + clean
    return clean[:40] if clean else ""


def _safe_label(label: str) -> str:
    """
    Convert relationship label to Mermaid-safe quoted string.
    Keeps only letters, digits, spaces and hyphens. Max 30 chars.
    """
    if not label:
        return "relates to"
    # Keep only safe characters
    clean = re.sub(r"[^A-Za-z0-9 \-]", "", label.strip())
    # Collapse whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:30] if clean else "relates to"


# ── JSON-LD export ────────────────────────────────────────────────────────────

def result_to_jsonld(result: dict) -> dict:
    context = {
        "@context": {
            "@vocab":        "https://schema.org/",
            "cdm":           "https://example.org/cdm#",
            "entity":        "cdm:entity",
            "relationship":  "cdm:relationship",
            "cardinality":   "cdm:cardinality",
            "ontologyMatch": "cdm:ontologyMatch",
        }
    }

    entities_ld = []
    for e in result.get("entities", []):
        entities_ld.append({
            "@type":              "cdm:Entity",
            "@id":                f"cdm:{e['name']}",
            "name":               e["name"],
            "description":        e.get("description", ""),
            "cdm:entityType":     e.get("type", "core"),
            "cdm:attributes":     e.get("attributes", []),
            "cdm:ontologyMatch":  e.get("ontology_matches", []),
            "cdm:inferred":       e.get("inferred", False),
        })

    relationships_ld = []
    for r in result.get("relationships", []):
        relationships_ld.append({
            "@type":           "cdm:Relationship",
            "cdm:fromEntity":  {"@id": f"cdm:{r['from_entity']}"},
            "cdm:toEntity":    {"@id": f"cdm:{r['to_entity']}"},
            "cdm:label":       r.get("label", ""),
            "cdm:cardinality": r.get("cardinality", ""),
            "cdm:required":    r.get("required", False),
            "cdm:ontologyType":r.get("ontology_type", ""),
            "cdm:inferred":    r.get("inferred", False),
        })

    return {
        **context,
        "@type":               "cdm:ConceptualDataModel",
        "name":                result.get("document_title", "CDM"),
        "cdm:entities":        entities_ld,
        "cdm:relationships":   relationships_ld,
        "cdm:stats":           result.get("stats", {}),
    }