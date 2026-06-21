"""
PDM Step — BigQuery Physical Data Model DDL Generator

Converts an LDM result into BigQuery CREATE TABLE DDL with:
  - BigQuery-native column types (STRING, INT64, NUMERIC, FLOAT64, BOOL, DATE, TIMESTAMP)
  - Mandatory audit columns on every table (row lifecycle + ETL lineage)
  - PRIMARY KEY / FOREIGN KEY NOT ENFORCED constraints (BigQuery 2023+)
  - PARTITION BY DATE(_ETL_LOAD_TS) for facts and large dims
  - CLUSTER BY top-4 FK/PK columns for query acceleration

No LLM calls — fully rule-based from the LDM result structure.
"""

import re

# ── BigQuery project / dataset defaults ──────────────────────────────────────
BQ_PROJECT_DEFAULT = "your_gcp_project"
BQ_DATASET_DEFAULT = "MERCH_DW"

# ── LDM → BigQuery type map ───────────────────────────────────────────────────
_BQ_TYPE_MAP: dict[str, str] = {
    "VARCHAR":        "STRING",
    "VARCHAR2":       "STRING",
    "NVARCHAR":       "STRING",
    "NVARCHAR2":      "STRING",
    "CHAR":           "STRING",
    "NCHAR":          "STRING",
    "TEXT":           "STRING",
    "CLOB":           "STRING",
    "NUMBER":         "NUMERIC",
    "NUMERIC":        "NUMERIC",
    "DECIMAL":        "NUMERIC",
    "FLOAT":          "FLOAT64",
    "FLOAT64":        "FLOAT64",
    "DOUBLE":         "FLOAT64",
    "REAL":           "FLOAT64",
    "INTEGER":        "INT64",
    "INT":            "INT64",
    "INT64":          "INT64",
    "BIGINT":         "INT64",
    "SMALLINT":       "INT64",
    "TINYINT":        "INT64",
    "DATE":           "DATE",
    "TIMESTAMP":      "TIMESTAMP",
    "TIMESTAMP_NTZ":  "TIMESTAMP",
    "DATETIME":       "DATETIME",
    "TIME":           "TIME",
    "BOOLEAN":        "BOOL",
    "BOOL":           "BOOL",
    "BYTES":          "BYTES",
    "BLOB":           "BYTES",
    "RAW":            "BYTES",
    "JSON":           "JSON",
}


def _to_bq_type(ldm_type: str) -> str:
    """Map an LDM/ANSI type string to the equivalent BigQuery type."""
    stripped = ldm_type.strip()

    # NUMBER(p,s) / NUMERIC(p,s) / DECIMAL(p,s)
    m = re.match(r'(?:NUMBER|NUMERIC|DECIMAL)\((\d+),\s*(\d+)\)', stripped, re.I)
    if m:
        p, s = int(m.group(1)), int(m.group(2))
        if p <= 29 and s <= 9:
            return f"NUMERIC({p},{s})"
        return "BIGNUMERIC"

    # NUMBER(p) — treat as INT64 if scale 0
    m = re.match(r'(?:NUMBER|INTEGER|INT)\((\d+)\)', stripped, re.I)
    if m:
        return "INT64"

    # Strip any parenthetical size for simple string/char types
    base = re.sub(r'\(.*\)', '', stripped).strip().upper()
    return _BQ_TYPE_MAP.get(base, "STRING")


# ── Mandatory audit columns ───────────────────────────────────────────────────
# Tuple: (column_name, bq_type, not_null_flag, description)
_AUDIT_COLUMNS: list[tuple[str, str, bool, str]] = [
    # Row lifecycle
    ("CREATED_AT",      "TIMESTAMP", True,  "Row creation timestamp (UTC)"),
    ("UPDATED_AT",      "TIMESTAMP", True,  "Last update timestamp (UTC)"),
    ("CREATED_BY",      "STRING",    True,  "User or process that inserted the row"),
    ("UPDATED_BY",      "STRING",    True,  "User or process that last updated the row"),
    ("ROW_VERSION",     "INT64",     True,  "Optimistic-lock version counter; incremented on every update"),
    ("IS_DELETED",      "BOOL",      True,  "Soft-delete flag; TRUE means logically deleted"),
    # ETL lineage
    ("_ETL_BATCH_ID",   "STRING",    False, "ETL job/batch identifier for traceability"),
    ("_ETL_LOAD_TS",    "TIMESTAMP", False, "Timestamp when this row was loaded by ETL — used as partition column"),
    ("_SOURCE_SYSTEM",  "STRING",    False, "Originating source system (e.g. POS, ERP, MANUAL)"),
    ("_RECORD_HASH",    "STRING",    False, "SHA-256 hash of business-key columns for change detection"),
]

_AUDIT_NAMES = {a[0].upper() for a in _AUDIT_COLUMNS}


# ── Partition strategy ────────────────────────────────────────────────────────

def _partition_clause(table: dict) -> str:
    """Return a BigQuery PARTITION BY clause, or '' for tables that don't need one."""
    name = table.get("table_name", "").upper()
    col_names_upper = {c.get("name", "").upper() for c in table.get("columns", [])}

    # FACT tables — always partition on ETL load timestamp
    if name.startswith("FACT_"):
        return "PARTITION BY DATE(_ETL_LOAD_TS)"

    # BRIDGE tables — partition on ETL load
    if name.startswith("BRIDGE_"):
        return "PARTITION BY DATE(_ETL_LOAD_TS)"

    # DIM tables — only worth partitioning if many columns (likely large SCD table)
    if name.startswith("DIM_"):
        if len(table.get("columns", [])) >= 8:
            return "PARTITION BY DATE(_ETL_LOAD_TS)"
        return ""

    # REF tables are typically small — skip partitioning
    return ""


# ── Clustering strategy ───────────────────────────────────────────────────────

def _cluster_cols(table: dict) -> list[str]:
    """Return up to 4 column names for CLUSTER BY (empty list = no clustering)."""
    name = table.get("table_name", "").upper()
    cols = table.get("columns", [])
    cluster: list[str] = []

    if name.startswith("FACT_"):
        # Cluster on FK surrogate keys — best cardinality for filter/join pruning
        for col in cols:
            cname = col.get("name", "").upper()
            if col.get("is_fk") and cname.endswith("_KEY"):
                cluster.append(col.get("name", ""))
            if len(cluster) >= 4:
                break
        # Fall back to PKs if no FKs found
        if not cluster:
            for col in cols:
                if col.get("is_pk"):
                    cluster.append(col.get("name", ""))
                if len(cluster) >= 4:
                    break

    elif name.startswith("DIM_"):
        # Natural key first (high selectivity), then surrogate PK
        for col in cols:
            if col.get("is_nk"):
                cluster.append(col.get("name", ""))
        for col in cols:
            if col.get("is_pk") and col.get("name", "") not in cluster:
                cluster.append(col.get("name", ""))
            if len(cluster) >= 4:
                break

    elif name.startswith(("BRIDGE_", "REF_")):
        for col in cols:
            if col.get("is_pk"):
                cluster.append(col.get("name", ""))
            if len(cluster) >= 2:
                break

    return cluster[:4]


# ── DDL for one table ─────────────────────────────────────────────────────────

def _bq_ddl_for_table(table: dict, project: str, dataset: str) -> str:
    """Generate BigQuery CREATE OR REPLACE TABLE DDL for one LDM table."""
    table_name = table.get("table_name", "UNKNOWN")
    columns    = table.get("columns", [])
    grain      = table.get("grain", "")
    scd_type   = table.get("scd_type")
    source     = table.get("source_system", "")
    fr_refs    = ", ".join(table.get("fr_references", []))

    full_ref = f"`{project}.{dataset}.{table_name}`"

    # ── Comment header ────────────────────────────────────────────────────────
    lines = [
        f"-- {'─' * 73}",
        f"-- {table_name}",
        f"-- Grain : {grain}",
    ]
    if scd_type:
        lines.append(f"-- SCD   : {scd_type}")
    if source:
        lines.append(f"-- Source: {source}")
    if fr_refs:
        lines.append(f"-- FR    : {fr_refs}")
    lines.append(f"-- {'─' * 73}")
    lines.append(f"CREATE OR REPLACE TABLE {full_ref}")
    lines.append("(")

    existing_upper = {c.get("name", "").upper() for c in columns}
    col_defs:   list[str] = []
    pk_cols:    list[str] = []
    fk_entries: list[tuple[str, str, str]] = []  # (col, ref_table, ref_col)

    # ── Business columns ──────────────────────────────────────────────────────
    for col in columns:
        cname    = col.get("name", "COL")
        ctype    = _to_bq_type(col.get("data_type", "STRING"))
        nullable = col.get("nullable", True)
        desc     = col.get("description", "").replace('"', "'")
        is_pk    = col.get("is_pk", False)
        is_fk    = col.get("is_fk", False)

        null_str = "" if nullable else " NOT NULL"
        desc_opt = f' OPTIONS(description="{desc}")' if desc else ""
        col_defs.append(f"    {cname:<42} {ctype}{null_str}{desc_opt}")

        if is_pk:
            pk_cols.append(cname)
        if is_fk and col.get("fk_table"):
            fk_entries.append((cname, col["fk_table"], cname))

    # ── Audit columns (skip any already defined in the LDM) ──────────────────
    for aname, atype, not_null, adesc in _AUDIT_COLUMNS:
        if aname.upper() not in existing_upper:
            null_str = " NOT NULL" if not_null else ""
            col_defs.append(f"    {aname:<42} {atype}{null_str} OPTIONS(description=\"{adesc}\")")

    lines.append(",\n".join(col_defs))

    # ── Constraints (NOT ENFORCED — BigQuery declares but does not enforce) ───
    constraints: list[str] = []
    if pk_cols:
        pk_list = ", ".join(pk_cols)
        constraints.append(
            f"    CONSTRAINT PK_{table_name}\n"
            f"        PRIMARY KEY ({pk_list}) NOT ENFORCED"
        )
    for fk_col, fk_table, ref_col in fk_entries:
        ref = f"`{project}.{dataset}.{fk_table}`"
        constraints.append(
            f"    CONSTRAINT FK_{table_name}_{fk_col}\n"
            f"        FOREIGN KEY ({fk_col})\n"
            f"        REFERENCES {ref} ({ref_col}) NOT ENFORCED"
        )

    if constraints:
        lines[-1] = lines[-1] + ","
        lines.append(",\n".join(constraints))

    lines.append(")")

    # ── Table OPTIONS ────────────────────────────────────────────────────────
    if grain:
        safe_grain = grain.replace('"', "'")
        lines.append(f'OPTIONS(description="{safe_grain}")')

    # ── PARTITION BY ─────────────────────────────────────────────────────────
    partition = _partition_clause(table)
    if partition:
        lines.append(partition)

    # ── CLUSTER BY ───────────────────────────────────────────────────────────
    cluster = _cluster_cols(table)
    if cluster:
        lines.append(f"CLUSTER BY {', '.join(cluster)}")

    lines.append(";")
    lines.append("")

    return "\n".join(lines)


# ── Full DDL ──────────────────────────────────────────────────────────────────

def generate_bq_ddl(
    ldm_result: dict,
    project:    str = BQ_PROJECT_DEFAULT,
    dataset:    str = BQ_DATASET_DEFAULT,
) -> str:
    """Generate complete BigQuery DDL for all tables in the LDM result."""
    all_tables = (
        ldm_result.get("dimension_tables", []) +
        ldm_result.get("fact_tables",      []) +
        ldm_result.get("bridge_tables",    []) +
        ldm_result.get("reference_tables", [])
    )

    audit_names = ", ".join(a[0] for a in _AUDIT_COLUMNS)

    header = f"""-- {'=' * 77}
-- PHYSICAL DATA MODEL — BigQuery
-- Project : {project}
-- Dataset : {dataset}
-- Tables  : {len(all_tables)}
-- Generated by DataModelerAgent PDM Step
--
-- Audit columns added to every table:
--   {audit_names}
--
-- Partitioning  : FACT / BRIDGE / large DIM → PARTITION BY DATE(_ETL_LOAD_TS)
-- Clustering    : FACT → top-4 FK _KEY columns
--                 DIM  → Natural-key then Surrogate-key
-- Constraints   : PRIMARY KEY / FOREIGN KEY NOT ENFORCED (documentation only)
-- {'=' * 77}

CREATE SCHEMA IF NOT EXISTS `{project}.{dataset}`;

"""

    sections: dict[str, list] = {
        "DIMENSION TABLES": ldm_result.get("dimension_tables", []),
        "FACT TABLES":      ldm_result.get("fact_tables",      []),
        "BRIDGE TABLES":    ldm_result.get("bridge_tables",    []),
        "REFERENCE TABLES": ldm_result.get("reference_tables", []),
    }

    parts = [header]
    for section_label, tables in sections.items():
        if not tables:
            continue
        parts.append(f"-- {'─' * 77}")
        parts.append(f"-- {section_label}")
        parts.append(f"-- {'─' * 77}\n")
        for t in tables:
            parts.append(_bq_ddl_for_table(t, project, dataset))

    return "\n".join(parts)


# ── PDM summary ───────────────────────────────────────────────────────────────

def generate_pdm_summary(ldm_result: dict) -> list[dict]:
    """Table-level summary for the PDM output UI."""
    rows = []
    sections = [
        ("Dimension", ldm_result.get("dimension_tables", [])),
        ("Fact",      ldm_result.get("fact_tables",      [])),
        ("Bridge",    ldm_result.get("bridge_tables",    [])),
        ("Reference", ldm_result.get("reference_tables", [])),
    ]
    for ttype, tables in sections:
        for t in tables:
            name = t.get("table_name", "")
            partition = _partition_clause(t) or "—"
            cluster   = ", ".join(_cluster_cols(t)) or "—"
            biz_cols  = len(t.get("columns", []))
            total_cols = biz_cols + len(_AUDIT_COLUMNS)
            rows.append({
                "Table":        name,
                "Type":         ttype,
                "BQ Columns":   total_cols,
                "Biz Columns":  biz_cols,
                "Audit Columns": len(_AUDIT_COLUMNS),
                "Partition":    partition.replace("PARTITION BY ", ""),
                "Cluster By":   cluster,
            })
    return rows


# ── Main entry point ──────────────────────────────────────────────────────────

def build_pdm_output(
    ldm_result: dict,
    project:    str = BQ_PROJECT_DEFAULT,
    dataset:    str = BQ_DATASET_DEFAULT,
    on_log      = None,
) -> dict:
    """
    Build the complete PDM output from a validated LDM result.

    Returns:
        {
            ddl_bq:       str        — BigQuery DDL script
            summary:      list[dict] — per-table summary
            table_count:  int
            audit_cols:   list[str]  — names of audit columns added
            project:      str
            dataset:      str
        }
    """
    def log(msg: str):
        if on_log:
            on_log(msg)

    log(f"Generating BigQuery DDL for project={project}, dataset={dataset}…")
    ddl_bq = generate_bq_ddl(ldm_result, project=project, dataset=dataset)

    log("Building PDM summary table…")
    summary = generate_pdm_summary(ldm_result)

    table_count = ddl_bq.count("CREATE OR REPLACE TABLE")
    log(f"PDM complete — {table_count} tables, {len(_AUDIT_COLUMNS)} audit columns per table")

    return {
        "ddl_bq":      ddl_bq,
        "summary":     summary,
        "table_count": table_count,
        "audit_cols":  [a[0] for a in _AUDIT_COLUMNS],
        "project":     project,
        "dataset":     dataset,
    }
