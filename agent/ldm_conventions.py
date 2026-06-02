"""
LDM Naming Conventions Loader

Single source of truth for all LDM naming rules.
Reads from skills/LDM_NAMING_CONVENTIONS.md and exposes:
  - TABLE_PREFIXES      dict  — entity_type → prefix
  - DIM_ALIASES         dict  — raw name → canonical DIM_ name
  - FACT_ALIASES        dict  — raw name → canonical FACT_ name
  - SCD_ASSIGNMENTS     dict  — table_name → scd_type
  - GRAIN_DECLARATIONS  dict  — table_name → grain string
  - FORBIDDEN_SUFFIXES  set   — name endings that must not be entities
  - SCHEMA              str   — schema name
  - enforce_naming()    func  — corrects any table name to convention
  - get_prompt_rules()  func  — returns conventions as LLM prompt text
  - enforce_mandatory_fks() func — ensures all facts have mandatory dimension FKs
"""

import os, re

CONVENTIONS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "skills", "LDM_NAMING_CONVENTIONS.md"
)

# ── Static definitions (source of truth) ─────────────────────────────────────

SCHEMA = "MERCH_DW"

TABLE_PREFIXES = {
    "dimension": "DIM_",
    "fact":      "FACT_",
    "bridge":    "BRIDGE_",
    "reference": "REF_",
    "aggregate": "AGG_",
    "view":      "V_",
    "staging":   "STG_",
    "etl":       "ETL_",
}

FORBIDDEN_PREFIXES = {"T_", "TB_", "TBL_", "FCT_", "FT_", "D_", "F_"}

DIM_ALIASES = {
    "PRODUCT":               "DIM_PRODUCT",
    "PRODUCTS":              "DIM_PRODUCT",
    "PRODUCT_DIMENSION":     "DIM_PRODUCT",
    "PRODUCTHIERARCHY":      "DIM_PRODUCT",
    "SALEFACT":              "DIM_PRODUCT",
    "ORGANISATION":          "DIM_ORGANISATION",
    "ORGANIZATION":          "DIM_ORGANISATION",
    "STORE":                 "DIM_ORGANISATION",
    "LOCATION":              "DIM_ORGANISATION",
    "STOREDIMENSION":        "DIM_ORGANISATION",
    "ORGANISATIONDIMENSION": "DIM_ORGANISATION",
    "CALENDAR":              "DIM_BUSINESS_CALENDAR",
    "TIME":                  "DIM_BUSINESS_CALENDAR",
    "DATE":                  "DIM_BUSINESS_CALENDAR",
    "BUSINESS_CALENDAR":     "DIM_BUSINESS_CALENDAR",
    "FISCAL_CALENDAR":       "DIM_BUSINESS_CALENDAR",
    "BUSINESSCALENDAR":      "DIM_BUSINESS_CALENDAR",
    "TIMEDIMENSION":         "DIM_BUSINESS_CALENDAR",
    "SEASON":                "DIM_PRODUCT_SEASON",
    "PRODUCT_SEASON":        "DIM_PRODUCT_SEASON",
    "PRODUCTSEASON":         "DIM_PRODUCT_SEASON",
    "RETAIL_TYPE":           "DIM_RETAIL_PRICE_TYPE",
    "PRICE_TYPE":            "DIM_RETAIL_PRICE_TYPE",
    "RETAILPRICETYPE":       "DIM_RETAIL_PRICE_TYPE",
    "PRICETYPE":             "DIM_RETAIL_PRICE_TYPE",
    "RETAILTYPE":            "DIM_RETAIL_PRICE_TYPE",
}

FACT_ALIASES = {
    "SALES":                  "FACT_SALES",
    "SALE":                   "FACT_SALES",
    "SALES_FACT":             "FACT_SALES",
    "SALEFACT":               "FACT_SALES",
    "MARKDOWN":               "FACT_MARKDOWN",
    "MARKDOWNS":              "FACT_MARKDOWN",
    "MARKDOWN_FACT":          "FACT_MARKDOWN",
    "MARKDOWNFACT":           "FACT_MARKDOWN",
    "FORECAST":               "FACT_SALES_FORECAST",
    "SALES_FORECAST":         "FACT_SALES_FORECAST",
    "SALESFORECAST":          "FACT_SALES_FORECAST",
    "SALES_FORECAST_FACT":    "FACT_SALES_FORECAST",
    "SUPPLIER_COST":          "FACT_SUPPLIER_COST",
    "SUPPLIERCOST":           "FACT_SUPPLIER_COST",
    "SUPPLIER":               "FACT_SUPPLIER_COST",
    "COST":                   "FACT_SUPPLIER_COST",
    "CURRENCY_CONVERSION":    "FACT_CURRENCY_CONVERSION",
    "CURRENCYCONVERSION":     "FACT_CURRENCY_CONVERSION",
    "CURRENCY":               "FACT_CURRENCY_CONVERSION",
}

SCD_ASSIGNMENTS = {
    "DIM_PRODUCT":            2,
    "DIM_ORGANISATION":       2,
    "DIM_BUSINESS_CALENDAR":  1,
    "DIM_PRODUCT_SEASON":     1,
    "DIM_RETAIL_PRICE_TYPE":  1,
}

GRAIN_DECLARATIONS = {
    "FACT_SALES":               "Item × Location × Day × Retail Price Type",
    "FACT_MARKDOWN":            "Item × Location × Week × Retail Price Type",
    "FACT_SALES_FORECAST":      "Item × Location × Week",
    "FACT_SUPPLIER_COST":       "Item × Supplier × Period",
    "FACT_CURRENCY_CONVERSION": "From-Currency × Currency Type × Date",
    "AGG_SALES_WEEKLY":         "Subclass × Location × Week × Retail Price Type",
}

FORBIDDEN_SUFFIXES = {
    "report", "dashboard", "summary", "analysis", "view", "overview",
    "scorecard", "analytics", "portal", "insight", "snapshot",
    "kpi", "metric", "rate", "ratio", "percentage", "top10", "topn",
}

# ── Mandatory conformed dimensions ───────────────────────────────────────────
# Every fact table MUST be connected to these dimensions.
# FACT_CURRENCY_CONVERSION is exempt from PRODUCT_KEY (it has no product grain).

MANDATORY_FACT_FKS = {
    # FK column name → (dimension table, data type, description)
    "DATE_KEY":     ("DIM_BUSINESS_CALENDAR", "NUMBER(8)",  "FK to DIM_BUSINESS_CALENDAR — mandatory on all facts"),
    "ORG_KEY":      ("DIM_ORGANISATION",       "NUMBER(18)", "FK to DIM_ORGANISATION — mandatory on all facts"),
    "PRODUCT_KEY":  ("DIM_PRODUCT",            "NUMBER(18)", "FK to DIM_PRODUCT — mandatory on all facts"),
}

# Facts exempt from PRODUCT_KEY (no product grain)
FACTS_WITHOUT_PRODUCT = {"FACT_CURRENCY_CONVERSION"}

# Mandatory relationships every fact must declare
MANDATORY_FACT_RELATIONSHIPS = [
    {"from": "DIM_BUSINESS_CALENDAR", "to": "FACT_*", "label": "dates",      "cardinality": "1:N"},
    {"from": "DIM_ORGANISATION",      "to": "FACT_*", "label": "locates",    "cardinality": "1:N"},
    {"from": "DIM_PRODUCT",           "to": "FACT_*", "label": "classifies", "cardinality": "1:N"},
]

STANDARD_PK_NAMES = {
    "DIM_PRODUCT":           "PRODUCT_KEY",
    "DIM_ORGANISATION":      "ORG_KEY",
    "DIM_BUSINESS_CALENDAR": "DATE_KEY",
    "DIM_PRODUCT_SEASON":    "SEASON_KEY",
    "DIM_RETAIL_PRICE_TYPE": "PRICE_TYPE_KEY",
}

STANDARD_FK_NAMES = {
    "DIM_PRODUCT":           "PRODUCT_KEY",
    "DIM_ORGANISATION":      "ORG_KEY",
    "DIM_BUSINESS_CALENDAR": "DATE_KEY",
    "DIM_RETAIL_PRICE_TYPE": "PRICE_TYPE_KEY",
}


# ── Enforcement ───────────────────────────────────────────────────────────────

def enforce_mandatory_fks(ldm_result: dict, on_log=None) -> dict:
    """
    Ensure every fact table has the mandatory conformed dimension FK columns.
    Adds missing DATE_KEY, ORG_KEY, PRODUCT_KEY columns if absent.
    Also ensures mandatory relationships exist in the LDM.
    """
    def log(msg):
        if on_log: on_log(msg)

    for fact in ldm_result.get("fact_tables", []):
        table_name = fact.get("table_name", "")
        existing_cols = {c.get("name","").upper() for c in fact.get("columns", [])}

        for fk_col, (dim_table, dtype, desc) in MANDATORY_FACT_FKS.items():
            # PRODUCT_KEY exempt for currency conversion
            if fk_col == "PRODUCT_KEY" and table_name in FACTS_WITHOUT_PRODUCT:
                continue

            if fk_col not in existing_cols:
                # Insert FK at the front after any existing FKs
                fk_col_def = {
                    "name":        fk_col,
                    "data_type":   dtype,
                    "nullable":    False,
                    "is_fk":       True,
                    "is_pk":       False,
                    "metric_type": "fk",
                    "description": desc,
                }
                # Find position — insert after last existing FK
                insert_pos = 0
                for i, c in enumerate(fact.get("columns", [])):
                    if c.get("is_fk") or c.get("metric_type") == "fk":
                        insert_pos = i + 1
                fact.setdefault("columns", []).insert(insert_pos, fk_col_def)
                log(f"  Added missing {fk_col} to {table_name}")

        # Ensure grain_columns includes the mandatory FKs
        grain_cols = set(fact.get("grain_columns", []))
        for fk_col in MANDATORY_FACT_FKS:
            if fk_col == "PRODUCT_KEY" and table_name in FACTS_WITHOUT_PRODUCT:
                continue
            if fk_col not in grain_cols:
                fact.setdefault("grain_columns", []).append(fk_col)

    return ldm_result


def enforce_naming(table_name: str, entity_type: str) -> str:
    """
    Enforce naming convention on a table name.
    Reads from the alias maps and prefix rules in this module.
    """
    name = table_name.strip().upper()

    if entity_type in ("dimension",):
        if name.startswith("DIM_"):
            return name
        # Strip forbidden prefixes
        for fp in FORBIDDEN_PREFIXES | {"FACT_", "REF_", "BRIDGE_", "AGG_"}:
            if name.startswith(fp):
                name = name[len(fp):]
                break
        if name in DIM_ALIASES:
            return DIM_ALIASES[name]
        return f"DIM_{name}"

    elif entity_type == "fact":
        if name.startswith("FACT_"):
            return name
        for fp in FORBIDDEN_PREFIXES | {"DIM_", "REF_", "BRIDGE_", "AGG_"}:
            if name.startswith(fp):
                name = name[len(fp):]
                break
        if name in FACT_ALIASES:
            return FACT_ALIASES[name]
        return f"FACT_{name}"

    elif entity_type == "bridge":
        if name.startswith("BRIDGE_"):
            return name
        return f"BRIDGE_{name}"

    elif entity_type == "reference":
        if name.startswith("REF_"):
            return name
        return f"REF_{name}"

    elif entity_type == "aggregate":
        if name.startswith("AGG_"):
            return name
        return f"AGG_{name}"

    return name


def enforce_ldm_naming(ldm_result: dict) -> dict:
    """Apply naming conventions to all tables in an LDM result dict."""
    for t in ldm_result.get("dimension_tables", []):
        t["table_name"] = enforce_naming(t.get("table_name", ""), "dimension")

    for t in ldm_result.get("fact_tables", []):
        t["table_name"] = enforce_naming(t.get("table_name", ""), "fact")

    for t in ldm_result.get("bridge_tables", []):
        t["table_name"] = enforce_naming(t.get("table_name", ""), "bridge")

    for t in ldm_result.get("reference_tables", []):
        t["table_name"] = enforce_naming(t.get("table_name", ""), "reference")

    return ldm_result


# ── Prompt text ───────────────────────────────────────────────────────────────

def get_prompt_rules() -> str:
    """
    Return naming convention rules as a compact LLM prompt string.
    Injected into all LDM step prompts.
    """
    dim_aliases_text = "\n".join(
        f"  {k} → {v}"
        for k, v in list(DIM_ALIASES.items())[:8]
    )
    fact_aliases_text = "\n".join(
        f"  {k} → {v}"
        for k, v in list(FACT_ALIASES.items())[:8]
    )
    return f"""
=== MANDATORY NAMING CONVENTIONS (from LDM_NAMING_CONVENTIONS.md) ===

TABLE PREFIXES — strictly enforce these:
  Dimension tables:  DIM_    e.g. DIM_PRODUCT, DIM_ORGANISATION, DIM_BUSINESS_CALENDAR
  Fact tables:       FACT_   e.g. FACT_SALES, FACT_MARKDOWN, FACT_SALES_FORECAST
  Bridge tables:     BRIDGE_ e.g. BRIDGE_ITEM_SEASON
  Reference tables:  REF_    e.g. REF_CURRENCY, REF_SOURCE_SYSTEM
  Aggregate tables:  AGG_    e.g. AGG_SALES_WEEKLY

FORBIDDEN prefixes: T_, TB_, TBL_, FCT_, FT_, D_, F_
NEVER omit the prefix — PRODUCT alone is INVALID, DIM_PRODUCT is VALID.

CANONICAL DIMENSION NAMES:
{dim_aliases_text}

CANONICAL FACT NAMES:
{fact_aliases_text}

STANDARD SURROGATE KEY NAMES:
  DIM_PRODUCT           → PRODUCT_KEY
  DIM_ORGANISATION      → ORG_KEY
  DIM_BUSINESS_CALENDAR → DATE_KEY
  DIM_RETAIL_PRICE_TYPE → PRICE_TYPE_KEY
  DIM_PRODUCT_SEASON    → SEASON_KEY

SCHEMA: {SCHEMA}
All tables: {SCHEMA}.<TABLE_NAME>

SCD TYPE ASSIGNMENTS:
  DIM_PRODUCT:            SCD2 (product reclassification tracked)
  DIM_ORGANISATION:       SCD2 (store reclassification tracked)
  DIM_BUSINESS_CALENDAR:  SCD1 (calendar never changes)
  DIM_PRODUCT_SEASON:     SCD1 (season dates are fixed)
  DIM_RETAIL_PRICE_TYPE:  SCD1 (static — only 3 values)

MANDATORY FK COLUMNS — every FACT_ table MUST include ALL of these:
  DATE_KEY        NUMBER(8)     NOT NULL  -- FK to DIM_BUSINESS_CALENDAR
  ORG_KEY         NUMBER(18)   NOT NULL  -- FK to DIM_ORGANISATION
  PRODUCT_KEY     NUMBER(18)   NOT NULL  -- FK to DIM_PRODUCT

MANDATORY RELATIONSHIPS — every FACT_ table MUST declare:
  DIM_BUSINESS_CALENDAR ||--}}o FACT_* : "dates"
  DIM_ORGANISATION      ||--}}o FACT_* : "locates"
  DIM_PRODUCT           ||--}}o FACT_* : "classifies"

NOTE: Department (DEPT_ID) is an attribute of DIM_PRODUCT — not a separate dimension.
      Time dimension = DIM_BUSINESS_CALENDAR.
      Location dimension = DIM_ORGANISATION.

=== END NAMING CONVENTIONS ===
"""


def load_conventions_text() -> str:
    """Return full conventions file as raw text for reference."""
    if os.path.exists(CONVENTIONS_PATH):
        with open(CONVENTIONS_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return get_prompt_rules()
