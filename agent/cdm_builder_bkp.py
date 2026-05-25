"""
Step 5 — CDM generation
Assembles the final Conceptual Data Model from entities and relationships.
Also provides export helpers: Mermaid erDiagram and JSON-LD.
"""


def build_cdm(
    parsed_doc: dict,
    entities: list[dict],
    relationships: list[dict],
) -> dict:
    """
    Assembles the CDM result object.
    """
    return {
        "document_title": _infer_title(parsed_doc),
        "entities": entities,
        "relationships": relationships,
        "stats": {
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            "section_count": len(parsed_doc.get("sections", [])),
        },
    }


def _infer_title(parsed_doc: dict) -> str:
    sections = parsed_doc.get("sections", [])
    if sections:
        return sections[0].get("heading", "Business Requirements")
    return "Business Requirements"


# ─── Mermaid export ──────────────────────────────────────────────────────────

_CARDINALITY_MAP = {
    "1:1":  ("||", "||"),
    "1:N":  ("||", "o{"),
    "N:1":  ("o{", "||"),
    "M:N":  ("}o", "o{"),
}

def result_to_mermaid(result: dict) -> str:
    lines = ["erDiagram"]

    entities = result.get("entities", [])
    relationships = result.get("relationships", [])

    # Entity blocks with attributes
    for e in entities:
        name = _safe_name(e["name"])
        lines.append(f"  {name} {{")
        lines.append(f"    string id PK")
        for attr in e.get("attributes", [])[:6]:
            attr_name = _safe_attr(attr)
            lines.append(f"    string {attr_name}")
        lines.append("  }")

    lines.append("")

    # Relationships
    seen_rel = set()
    for r in relationships:
        from_e = _safe_name(r.get("from_entity", ""))
        to_e = _safe_name(r.get("to_entity", ""))
        label = _safe_label(r.get("label", "relates_to"))
        card = r.get("cardinality", "1:N")

        if not from_e or not to_e:
            continue

        key = (from_e, to_e)
        if key in seen_rel:
            continue
        seen_rel.add(key)

        left, right = _CARDINALITY_MAP.get(card, ("||", "o{"))
        required = r.get("required", False)
        connector = "--" if required else ".."

        lines.append(f"  {from_e} {left}{connector}{right} {to_e} : \"{label}\"")

    return "\n".join(lines)


def _safe_name(name: str) -> str:
    """Make entity name safe for Mermaid — remove spaces, keep PascalCase."""
    import re
    name = re.sub(r"[^A-Za-z0-9_]", "", name.replace(" ", "_"))
    return name or "Entity"


def _safe_attr(attr: str) -> str:
    import re
    attr = attr.strip().lower()
    attr = re.sub(r"[^a-z0-9_]", "_", attr.replace(" ", "_"))
    attr = re.sub(r"_+", "_", attr).strip("_")
    return attr or "field"


def _safe_label(label: str) -> str:
    import re
    label = label.strip()
    label = re.sub(r'["\n]', "", label)
    return label[:40] if label else "relates to"


# ─── JSON-LD export ───────────────────────────────────────────────────────────

def result_to_jsonld(result: dict) -> dict:
    context = {
        "@context": {
            "@vocab": "https://schema.org/",
            "cdm": "https://example.org/cdm#",
            "entity": "cdm:entity",
            "relationship": "cdm:relationship",
            "cardinality": "cdm:cardinality",
            "ontologyMatch": "cdm:ontologyMatch",
        }
    }

    entities_ld = []
    for e in result.get("entities", []):
        entities_ld.append({
            "@type": "cdm:Entity",
            "@id": f"cdm:{e['name']}",
            "name": e["name"],
            "description": e.get("description", ""),
            "cdm:entityType": e.get("type", "core"),
            "cdm:attributes": e.get("attributes", []),
            "cdm:ontologyMatch": e.get("ontology_matches", []),
        })

    relationships_ld = []
    for r in result.get("relationships", []):
        relationships_ld.append({
            "@type": "cdm:Relationship",
            "cdm:fromEntity": {"@id": f"cdm:{r['from_entity']}"},
            "cdm:toEntity": {"@id": f"cdm:{r['to_entity']}"},
            "cdm:label": r.get("label", ""),
            "cdm:cardinality": r.get("cardinality", ""),
            "cdm:required": r.get("required", False),
            "cdm:ontologyType": r.get("ontology_type", ""),
        })

    return {
        **context,
        "@type": "cdm:ConceptualDataModel",
        "name": result.get("document_title", "CDM"),
        "cdm:entities": entities_ld,
        "cdm:relationships": relationships_ld,
        "cdm:stats": result.get("stats", {}),
    }
