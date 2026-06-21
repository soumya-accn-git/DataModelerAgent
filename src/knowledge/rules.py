"""
OWL/SHACL rules engine — aligned with SKILL.md.

Valid entity types: dimension, fact, reference, bridge only.
Reports/dashboards/filters are classified as derived outputs and used
to infer real dimensional/fact entities.
"""

import re, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

# ── Constants from SKILL.md ───────────────────────────────────────────────────

VALID_TYPES = {"dimension", "fact", "reference", "bridge"}

FORBIDDEN_SUFFIXES = {
    "report", "dashboard", "summary", "analysis", "view", "overview",
    "scorecard", "monitor", "tracker", "insight", "snapshot", "filter",
    "prompt", "top10", "kpi", "metric", "rate", "ratio", "percentage",
    "analytics", "portal", "feed", "digest", "listing", "ranking"
}

REPORT_SUFFIXES = {
    "report", "dashboard", "summary", "analysis", "view", "overview",
    "scorecard", "analytics", "portal", "insight", "snapshot"
}

# Filter/Prompt suffixes — these IMPLY dimensions (Rule R6), not forbidden
FILTER_SUFFIXES_IMPLY_DIM = {
    "filter", "prompt", "selector", "picker", "dropdown",
    "checkbox", "toggle"
}

DIMENSION_KEYWORDS = {
    "consumer": "ConsumerDimension",
    "customer": "CustomerDimension",
    "client":   "CustomerDimension",
    "product":  "ProductDimension",
    "item":     "ProductDimension",
    "time":     "TimeDimension",
    "date":     "TimeDimension",
    "period":   "TimeDimension",
    "month":    "TimeDimension",
    "quarter":  "TimeDimension",
    "year":     "TimeDimension",
    "region":   "GeographyDimension",
    "geography":"GeographyDimension",
    "location": "GeographyDimension",
    "country":  "GeographyDimension",
    "city":     "GeographyDimension",
    "channel":  "ChannelDimension",
    "store":    "StoreDimension",
    "employee": "EmployeeDimension",
    "agent":    "EmployeeDimension",
    "segment":  "SegmentDimension",
    "brand":    "BrandDimension",
    "category": "CategoryDimension",
    "market":   "MarketDimension",
    "campaign": "CampaignDimension",
    "supplier": "SupplierDimension",
    "vendor":   "SupplierDimension",
    "account":  "AccountDimension",
    "partner":  "PartnerDimension",
    "RegionFilter": "GeographyDimension",
    "DateRangePrompt":  "DateDimension",
    "DateRangeFilter":  "DateDimension"
}

FACT_KEYWORDS = {
    "spending":    "SpendingFact",
    "spend":       "SpendingFact",
    "sale":        "SaleFact",
    "sales":       "SaleFact",
    "revenue":     "RevenueFact",
    "transaction": "TransactionFact",
    "payment":     "PaymentFact",
    "order":       "OrderFact",
    "purchase":    "PurchaseFact",
    "claim":       "ClaimFact",
    "usage":       "UsageFact",
    "visit":       "VisitFact",
    "event":       "EventFact",
    "activity":    "ActivityFact",
    "performance": "PerformanceFact",
    "inventory":   "InventoryFact",
}

TRANSITIVE_LABELS = {"belongs to", "is part of", "contained in", "member of"}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _pascal_words(name: str) -> list[str]:
    return [w.lower() for w in re.findall(r'[A-Z][a-z0-9]*', name)]

def _is_forbidden(entity: dict) -> bool:
    name = entity.get("name", "").lower()
    t    = entity.get("type", "")
    if t not in VALID_TYPES:
        return True
    if any(name.endswith(s) for s in FORBIDDEN_SUFFIXES):
        return True
    return False

def _is_report(entity: dict) -> bool:
    name = entity.get("name", "").lower()
    return any(name.endswith(s) for s in REPORT_SUFFIXES)


def _infer_from_report(report_name: str, existing: set) -> list[dict]:
    """Infer Dimension and Fact entities from a report/dashboard name."""
    words   = _pascal_words(report_name)
    inferred = []

    for word in words:
        # Dimension inference
        if word in DIMENSION_KEYWORDS:
            dim_name = DIMENSION_KEYWORDS[word]
            if dim_name not in existing:
                inferred.append({
                    "name": dim_name,
                    "type": "dimension",
                    "description": f"Dimension inferred from report '{report_name}' — represents the {word} axis of analysis.",
                    "attributes": ["id", "name", "description", "code"],
                    "source": f"OWL Rule R1 — inferred from: {report_name}",
                    "ontology_matches": [f"schema:{word.capitalize()}"],
                    "inferred": True,
                })
                existing.add(dim_name)

        # Fact inference
        if word in FACT_KEYWORDS:
            fact_name = FACT_KEYWORDS[word]
            if fact_name not in existing:
                inferred.append({
                    "name": fact_name,
                    "type": "fact",
                    "description": f"Fact entity inferred from report '{report_name}' — stores measurable {word} events.",
                    "attributes": ["id", "amount", "quantity", "effectiveDate", "currencyCode"],
                    "source": f"OWL Rule R2 — inferred from: {report_name}",
                    "ontology_matches": ["schema:MonetaryAmount", "schema:QuantitativeValue"],
                    "inferred": True,
                })
                existing.add(fact_name)

    return inferred


def _ensure_time_dimension(entities: list[dict], existing: set) -> list[dict]:
    """OWL Rule R3 — every model must have a TimeDimension."""
    if "TimeDimension" not in existing:
        return [{
            "name": "TimeDimension",
            "type": "dimension",
            "description": "Standard time dimension — provides date/period context for all fact entities.",
            "attributes": ["dateKey", "fullDate", "year", "quarter", "month", "weekNumber"],
            "source": "OWL Rule R3 — TimeDimension always required",
            "ontology_matches": ["schema:DateTime"],
            "inferred": True,
        }]
    return []


def _infer_bridges(entities: list[dict], relationships: list[dict], existing: set) -> list[dict]:
    """OWL Rule R5 — infer Bridge entities for M:N dimension relationships."""
    bridges = []
    dims = {e["name"] for e in entities if e.get("type") == "dimension"}
    for r in relationships:
        if (r.get("cardinality") == "M:N"
                and r["from_entity"] in dims
                and r["to_entity"] in dims):
            bridge_name = r["from_entity"].replace("Dimension","") + r["to_entity"].replace("Dimension","") + "Bridge"
            if bridge_name not in existing:
                bridges.append({
                    "name": bridge_name,
                    "type": "bridge",
                    "description": f"Bridge entity resolving M:N between {r['from_entity']} and {r['to_entity']}.",
                    "attributes": ["id", r["from_entity"][0].lower()+"Id", r["to_entity"][0].lower()+"Id"],
                    "source": "OWL Rule R5 — M:N bridge inference",
                    "ontology_matches": [],
                    "inferred": True,
                })
                existing.add(bridge_name)
    return bridges


def apply_property_chains(relationships: list[dict]) -> list[dict]:
    """OWL transitive property chain rule."""
    new_rels = []
    seen = {(r["from_entity"], r["to_entity"], r["label"]) for r in relationships}
    for r1 in relationships:
        if r1["label"].lower() not in TRANSITIVE_LABELS:
            continue
        for r2 in relationships:
            if r2["label"].lower() not in TRANSITIVE_LABELS:
                continue
            if r1["to_entity"] == r2["from_entity"] and r1["from_entity"] != r2["to_entity"]:
                key = (r1["from_entity"], r2["to_entity"], r1["label"])
                if key not in seen:
                    seen.add(key)
                    new_rels.append({
                        "from_entity": r1["from_entity"],
                        "to_entity":   r2["to_entity"],
                        "label":       r1["label"],
                        "cardinality": "N:1",
                        "required":    False,
                        "description": f"OWL property chain: {r1['from_entity']} → {r1['to_entity']} → {r2['to_entity']}",
                        "ontology_type": "owl:TransitiveProperty",
                        "inferred": True,
                    })
    return new_rels


def validate_entities(entities: list[dict]) -> list[dict]:
    """SHACL shape validation aligned with SKILL.md."""
    violations = []
    names = [e["name"] for e in entities]

    # sh:minCount — at least one fact and one dimension
    types = [e.get("type") for e in entities]
    if "fact" not in types:
        violations.append({"entity":"(model)","field":"type",
            "message":"No Fact entity found — every CDM needs at least one Fact (sh:minCount)",
            "severity":"Error"})
    if "dimension" not in types:
        violations.append({"entity":"(model)","field":"type",
            "message":"No Dimension entity found — every CDM needs at least one Dimension (sh:minCount)",
            "severity":"Error"})

    for e in entities:
        name = e.get("name","")

        # sh:pattern — PascalCase
        if not re.match(r'^[A-Z][A-Za-z0-9]*$', name):
            violations.append({"entity":name,"field":"name",
                "message":f"'{name}' is not PascalCase (sh:pattern violation)",
                "severity":"Warning"})

        # sh:in — valid type
        if e.get("type") not in VALID_TYPES:
            violations.append({"entity":name,"field":"type",
                "message":f"Type '{e.get('type')}' is not one of: {VALID_TYPES} (sh:in violation)",
                "severity":"Error"})

        # sh:not — forbidden suffix
        name_lower = name.lower()
        for s in FORBIDDEN_SUFFIXES:
            if name_lower.endswith(s):
                violations.append({"entity":name,"field":"name",
                    "message":f"'{name}' ends with forbidden suffix '{s}' (sh:not violation)",
                    "severity":"Error"})
                break

        # sh:minLength — description required
        if not e.get("description","").strip():
            violations.append({"entity":name,"field":"description",
                "message":"Missing description (sh:minLength violation)",
                "severity":"Warning"})

        # sh:uniqueLang — no duplicates
        if names.count(name) > 1:
            violations.append({"entity":name,"field":"name",
                "message":f"Duplicate entity name '{name}' (sh:uniqueLang violation)",
                "severity":"Error"})

    return violations


def apply_ontology_rules(
    entities: list[dict],
    relationships: list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """
    Apply all OWL/SHACL rules.
    Returns: (entities, relationships, inferred_entities, violations)
    """
    existing = {e["name"] for e in entities}
    all_inferred = []
    kept_entities = []
    report_rels = []

    for e in entities:
        if _is_report(e):
            # Infer real entities from the report name
            inferred = _infer_from_report(e["name"], existing)
            all_inferred.extend(inferred)
            for inf in inferred:
                report_rels.append({
                    "from_entity": inf["name"],
                    "to_entity":   e["name"],
                    "label":       "feeds",
                    "cardinality": "1:N",
                    "required":    True,
                    "description": f"{inf['name']} provides data to {e['name']}",
                    "ontology_type": "owl:ObjectProperty",
                    "inferred": True,
                })
            # Keep report entities but clearly marked
            e["type"] = "report"
            e["ontology_matches"] = (e.get("ontology_matches") or []) + ["owl:DerivedClass"]
            kept_entities.append(e)
        elif _is_forbidden(e):
            # Drop entirely — forbidden type or suffix
            print(f"[rules] Dropped forbidden entity: {e['name']} (type={e.get('type')})")
        else:
            kept_entities.append(e)

    # OWL Rule R3 — ensure TimeDimension
    time_inferred = _ensure_time_dimension(kept_entities + all_inferred, existing)
    all_inferred.extend(time_inferred)

    # OWL Rule R5 — bridge inference
    bridge_inferred = _infer_bridges(kept_entities + all_inferred, relationships, existing)
    all_inferred.extend(bridge_inferred)

    final_entities = kept_entities + all_inferred

    # Property chains
    chain_rels = apply_property_chains(relationships)
    final_relationships = relationships + report_rels + chain_rels

    # SHACL validation — run on real entities only (exclude report type)
    real_entities = [e for e in final_entities if e.get("type") != "report"]
    violations = validate_entities(real_entities)

    return final_entities, final_relationships, all_inferred, violations


# ── Rule R6 integration ───────────────────────────────────────────────────────

def apply_all_rules(
    entities: list[dict],
    relationships: list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """
    Full rules pass including R6 filter inference.
    Replaces apply_ontology_rules as the main entry point.
    Returns: (entities, relationships, inferred_entities, violations)
    """
    from src.knowledge.filter_inference import apply_filter_inference

    existing = {e["name"] for e in entities}
    all_inferred = []

    # ── R6 — Filter/Prompt → Dimension inference (run first) ─────────────────
    filter_inferred, filters_to_discard = apply_filter_inference(entities, existing)
    all_inferred.extend(filter_inferred)
    discard_names = {e["name"] for e in filters_to_discard}

    # Remove discarded filter entities from the list
    entities = [e for e in entities if e["name"] not in discard_names]

    # ── R1/R2 — Report → Dimension/Fact inference ─────────────────────────────
    kept_entities = []
    report_rels   = []
    for e in entities:
        if _is_report(e):
            inferred = _infer_from_report(e["name"], existing)
            all_inferred.extend(inferred)
            for inf in inferred:
                report_rels.append({
                    "from_entity":   inf["name"],
                    "to_entity":     e["name"],
                    "label":         "feeds",
                    "cardinality":   "1:N",
                    "required":      True,
                    "description":   f"{inf['name']} provides data to {e['name']}",
                    "ontology_type": "owl:ObjectProperty",
                    "inferred":      True,
                })
            e["type"] = "report"
            e["ontology_matches"] = (e.get("ontology_matches") or []) + ["owl:DerivedClass"]
            kept_entities.append(e)
        elif _is_forbidden(e):
            print(f"[rules] Dropped: {e['name']} (type={e.get('type')})")
        else:
            kept_entities.append(e)

    # ── R3 — TimeDimension always required ───────────────────────────────────
    all_inferred.extend(_ensure_time_dimension(kept_entities + all_inferred, existing))

    # ── R5 — Bridge inference ────────────────────────────────────────────────
    all_inferred.extend(_infer_bridges(kept_entities + all_inferred, relationships, existing))

    final_entities = kept_entities + all_inferred

    # ── Property chains ───────────────────────────────────────────────────────
    chain_rels        = apply_property_chains(relationships)
    final_relationships = relationships + report_rels + chain_rels

    # ── SHACL validation ──────────────────────────────────────────────────────
    real_entities = [e for e in final_entities if e.get("type") != "report"]
    violations    = validate_entities(real_entities)

    return final_entities, final_relationships, all_inferred, violations
