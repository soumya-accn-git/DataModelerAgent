"""
OWL Rule R6 — Filter/Prompt → Dimension inference.
Strips filter/prompt suffixes, matches subject words to known dimension
patterns, and returns inferred Dimension or Reference entities.
"""

import re

# Suffixes that mark something as a filter/prompt (not an entity)
FILTER_SUFFIXES = {
    "filter", "prompt", "selector", "picker", "dropdown",
    "checkbox", "toggle", "input", "parameter", "param",
    "criteria", "criterion", "option", "control"
}

# Range/boundary infixes — extract subject from these
RANGE_INFIXES = {"range", "min", "max", "from", "to", "between", "start", "end"}

# Top-N patterns — discard entirely (Rule R6c)
TOPN_PATTERN = re.compile(r'^top\d*$|^rank|^limit|^first\d*$|^last\d*$', re.IGNORECASE)

# Subject word → Dimension/Reference mapping (Rule R6a table)
SUBJECT_TO_ENTITY = {
    # Geography
    "region":      ("GeographyDimension",  "dimension"),
    "geography":   ("GeographyDimension",  "dimension"),
    "territory":   ("GeographyDimension",  "dimension"),
    "area":        ("GeographyDimension",  "dimension"),
    "location":    ("GeographyDimension",  "dimension"),
    "country":     ("GeographyDimension",  "dimension"),
    "city":        ("GeographyDimension",  "dimension"),
    "state":       ("GeographyDimension",  "dimension"),
    "zone":        ("GeographyDimension",  "dimension"),
    "postal":      ("GeographyDimension",  "dimension"),

    # Time
    "date":        ("TimeDimension",       "dimension"),
    "daterange":   ("TimeDimension",       "dimension"),
    "time":        ("TimeDimension",       "dimension"),
    "period":      ("TimeDimension",       "dimension"),
    "month":       ("TimeDimension",       "dimension"),
    "quarter":     ("TimeDimension",       "dimension"),
    "year":        ("TimeDimension",       "dimension"),
    "week":        ("TimeDimension",       "dimension"),
    "day":         ("TimeDimension",       "dimension"),
    "fiscal":      ("TimeDimension",       "dimension"),

    # Product
    "product":     ("ProductDimension",    "dimension"),
    "item":        ("ProductDimension",    "dimension"),
    "sku":         ("ProductDimension",    "dimension"),
    "catalogue":   ("ProductDimension",    "dimension"),
    "catalog":     ("ProductDimension",    "dimension"),

    # Customer
    "customer":    ("CustomerDimension",   "dimension"),
    "client":      ("CustomerDimension",   "dimension"),
    "consumer":    ("CustomerDimension",   "dimension"),
    "account":     ("CustomerDimension",   "dimension"),
    "member":      ("CustomerDimension",   "dimension"),

    # Channel / Store
    "channel":     ("ChannelDimension",    "dimension"),
    "store":       ("StoreDimension",      "dimension"),
    "outlet":      ("StoreDimension",      "dimension"),
    "branch":      ("StoreDimension",      "dimension"),
    "outlet":      ("StoreDimension",      "dimension"),

    # Employee
    "employee":    ("EmployeeDimension",   "dimension"),
    "agent":       ("EmployeeDimension",   "dimension"),
    "rep":         ("EmployeeDimension",   "dimension"),
    "staff":       ("EmployeeDimension",   "dimension"),
    "salesperson": ("EmployeeDimension",   "dimension"),

    # Category / Segment
    "category":    ("CategoryDimension",   "dimension"),
    "segment":     ("SegmentDimension",    "dimension"),
    "group":       ("SegmentDimension",    "dimension"),
    "class":       ("CategoryDimension",   "dimension"),
    "type":        ("CategoryDimension",   "dimension"),

    # Brand
    "brand":       ("BrandDimension",      "dimension"),
    "make":        ("BrandDimension",      "dimension"),
    "manufacturer":("BrandDimension",      "dimension"),

    # Campaign
    "campaign":    ("CampaignDimension",   "dimension"),
    "promotion":   ("CampaignDimension",   "dimension"),
    "offer":       ("CampaignDimension",   "dimension"),
    "promo":       ("CampaignDimension",   "dimension"),

    # Supplier
    "supplier":    ("SupplierDimension",   "dimension"),
    "vendor":      ("SupplierDimension",   "dimension"),
    "partner":     ("PartnerDimension",    "dimension"),

    # References
    "currency":    ("CurrencyReference",   "reference"),
    "fx":          ("CurrencyReference",   "reference"),
    "exchange":    ("CurrencyReference",   "reference"),
    "status":      ("StatusReference",     "reference"),
    "flag":        ("StatusReference",     "reference"),
    "code":        ("CodeReference",       "reference"),
}


def _pascal_words(name: str) -> list[str]:
    """Split PascalCase into lowercase word list."""
    return [w.lower() for w in re.findall(r'[A-Z][a-z0-9]*', name)]


def _is_topn(words: list[str]) -> bool:
    """Rule R6c — detect Top-N patterns."""
    for w in words:
        if TOPN_PATTERN.match(w):
            return True
    return False


def _strip_filter_suffix(words: list[str]) -> list[str]:
    """Remove trailing filter/prompt suffix words."""
    return [w for w in words if w not in FILTER_SUFFIXES]


def _strip_range_infixes(words: list[str]) -> list[str]:
    """Remove range/boundary infix words, keeping subject."""
    return [w for w in words if w not in RANGE_INFIXES]


def infer_dimension_from_filter(
    entity: dict,
    existing_names: set,
) -> dict | None:
    """
    Given a filter/prompt entity, attempt to infer a Dimension or Reference.
    Returns a new entity dict, or None if no inference possible (e.g. Top-N).
    """
    name  = entity.get("name", "")
    words = _pascal_words(name)

    if not words:
        return None

    # Rule R6c — discard Top-N filters
    if _is_topn(words):
        return None

    # Strip filter suffixes
    subject_words = _strip_filter_suffix(words)
    # Strip range infixes
    subject_words = _strip_range_infixes(subject_words)

    if not subject_words:
        return None

    # Try matching subject words against the mapping table
    for word in subject_words:
        if word in SUBJECT_TO_ENTITY:
            entity_name, entity_type = SUBJECT_TO_ENTITY[word]
            if entity_name in existing_names:
                return None  # already exists
            existing_names.add(entity_name)
            return {
                "name":        entity_name,
                "type":        entity_type,
                "description": (
                    f"{entity_type.capitalize()} entity inferred from filter '{name}' "
                    f"(OWL Rule R6 — filter/prompt implies dimension)."
                ),
                "attributes":  ["id", "name", "description", "code"],
                "source":      f"OWL Rule R6 — inferred from filter: {name}",
                "ontology_matches": [f"schema:{word.capitalize()}"],
                "inferred":    True,
                "inferred_from_filter": name,
            }

    # Compound word match — try joining adjacent words
    compound = "".join(subject_words)
    if compound in SUBJECT_TO_ENTITY:
        entity_name, entity_type = SUBJECT_TO_ENTITY[compound]
        if entity_name not in existing_names:
            existing_names.add(entity_name)
            return {
                "name":        entity_name,
                "type":        entity_type,
                "description": f"{entity_type.capitalize()} inferred from filter '{name}'.",
                "attributes":  ["id", "name", "description", "code"],
                "source":      f"OWL Rule R6 — inferred from filter: {name}",
                "ontology_matches": [],
                "inferred":    True,
                "inferred_from_filter": name,
            }

    return None


def apply_filter_inference(
    entities: list[dict],
    existing_names: set,
) -> tuple[list[dict], list[dict]]:
    """
    Scan all entities. For any that look like filters/prompts:
      - Infer the underlying Dimension/Reference (if possible)
      - Return (inferred_entities, filters_to_discard)

    Does NOT modify the input list — caller decides what to keep/drop.
    """
    inferred = []
    to_discard = []

    filter_indicators = FILTER_SUFFIXES | {"top10", "topn", "rank", "ranking"}

    for e in entities:
        name_lower = e.get("name", "").lower()
        etype      = e.get("type", "")

        # Detect if this entity is a filter/prompt — either by type
        # or by its name ending in a filter/prompt suffix
        is_filter = (
            etype in ("filter", "prompt")
            or any(name_lower.endswith(s) for s in filter_indicators)
        )

        if not is_filter:
            continue

        to_discard.append(e)
        result = infer_dimension_from_filter(e, existing_names)
        if result:
            inferred.append(result)
        # If result is None (Top-N etc.) — filter is simply discarded

    return inferred, to_discard
