"""
LDM output tab — displays the Logical Data Model results in Streamlit.

Shows:
  - Summary tab:    table count, column count, FR coverage overview
  - Tables tab:     per-table card with columns, grain, SCD type
  - Diagram tab:    Mermaid erDiagram
  - DDL tab:        SQL DDL with download buttons (ANSI + Snowflake)
  - FR Coverage tab: which table satisfies which requirement
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
import streamlit as st
import pandas as pd
from src.pipeline.step_ldm_ddl import build_ldm_output

# Type colours
TYPE_COLORS = {
    "DIM_":    ("#E1F5EE", "#085041"),
    "FACT_":   ("#FCEBEB", "#501313"),
    "BRIDGE_": ("#FAEEDA", "#412402"),
    "REF_":    ("#EEEDFE", "#26215C"),
}


def _type_badge(table_name: str) -> str:
    for prefix, (bg, fg) in TYPE_COLORS.items():
        if table_name.startswith(prefix):
            label = prefix.rstrip("_")
            return (f'<span style="background:{bg};color:{fg};'
                    f'font-size:10px;font-weight:500;border-radius:20px;'
                    f'padding:2px 8px">{label}</span>')
    return ""


def _metric_badge(mtype: str) -> str:
    colors = {
        "additive":     ("#E1F5EE", "#085041", "ADD"),
        "semi_additive":("#FAEEDA", "#412402", "SEMI"),
        "non_additive": ("#FCEBEB", "#501313", "NON-ADD"),
        "fk":           ("#EEEDFE", "#26215C", "FK"),
        "degenerate":   ("#F3F4F6", "#374151", "DEG"),
    }
    if mtype not in colors:
        return ""
    bg, fg, label = colors[mtype]
    return (f'<span style="background:{bg};color:{fg};'
            f'font-size:9px;font-weight:500;border-radius:20px;'
            f'padding:1px 6px">{label}</span>')


def render_ldm_output(ldm_result: dict):
    """Main entry point — renders the full LDM output section."""
    if not ldm_result:
        st.info("No LDM result available. Run the pipeline with mode **CDM + LDM** or **LDM only**.")
        return

    # Build all outputs (fast — no LLM)
    with st.spinner("Building DDL and diagrams…"):
        output = build_ldm_output(ldm_result, on_log=None)

    # ── Header metrics ─────────────────────────────────────────────────────
    all_tables = (
        ldm_result.get("dimension_tables", []) +
        ldm_result.get("fact_tables", []) +
        ldm_result.get("bridge_tables", []) +
        ldm_result.get("reference_tables", [])
    )
    total_cols = sum(len(t.get("columns",[])) for t in all_tables)
    fr_count   = len(output["fr_matrix"])

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("Dimensions",  len(ldm_result.get("dimension_tables",[])))
    with c2: st.metric("Facts",       len(ldm_result.get("fact_tables",[])))
    with c3: st.metric("Bridges",     len(ldm_result.get("bridge_tables",[])))
    with c4: st.metric("Total cols",  total_cols)
    with c5: st.metric("FRs covered", fr_count)

    st.divider()

    # ── Tabs ──────────────────────────────────────────────────────────────
    validation = ldm_result.get("_validation")
    pdm_result = st.session_state.get("pdm_result")

    tab_names = ["📋  Tables", "🗺️  Diagram", "💾  DDL", "✅  FR Coverage"]
    if validation:
        tab_names.append("🔍  Validation")
    if pdm_result:
        tab_names.append("🔷  BigQuery PDM")

    tabs = st.tabs(tab_names)
    tab_iter = iter(tabs)

    with next(tab_iter): _render_tables(ldm_result, output["summary"])
    with next(tab_iter): _render_diagram(output["mermaid"])
    with next(tab_iter): _render_ddl(output["ddl_ansi"], output["ddl_sf"])
    with next(tab_iter): _render_fr_coverage(output["fr_matrix"])
    if validation:
        with next(tab_iter): _render_validation(validation)
    if pdm_result:
        with next(tab_iter): _render_pdm(pdm_result)


# ── Tables tab ────────────────────────────────────────────────────────────────

def _render_tables(ldm_result: dict, summary: list[dict]):
    # Summary table
    st.markdown("**All tables**")
    df = pd.DataFrame(summary)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**Column detail**")

    sections = [
        ("🟢 Dimension tables", ldm_result.get("dimension_tables",[])),
        ("🔴 Fact tables",      ldm_result.get("fact_tables",[])),
        ("🟣 Bridge tables",    ldm_result.get("bridge_tables",[])),
        ("⚪ Reference tables", ldm_result.get("reference_tables",[])),
    ]

    for section_label, tables in sections:
        if not tables:
            continue
        with st.expander(f"{section_label} ({len(tables)})", expanded=True):
            for table in tables:
                tname  = table.get("table_name","")
                grain  = table.get("grain","")
                scd    = table.get("scd_type")
                source = table.get("source_system","—")
                cols   = table.get("columns",[])

                badge = _type_badge(tname)
                scd_str = f" · SCD{scd}" if scd else ""
                st.markdown(
                    f"{badge} **{tname}** · {len(cols)} columns · "
                    f"Source: `{source}`{scd_str}",
                    unsafe_allow_html=True,
                )
                st.caption(f"Grain: {grain}")

                # Column table
                col_rows = []
                for c in cols:
                    mtype = c.get("metric_type","")
                    mbadge = _metric_badge(mtype) if mtype else ""
                    pk_str = " 🔑" if c.get("is_pk") else ""
                    nk_str = " 🏷️" if c.get("is_nk") else ""
                    fk_str = " 🔗" if c.get("is_fk") else ""
                    null_str = "" if c.get("nullable",True) else "NOT NULL"
                    col_rows.append({
                        "Column":      c.get("name","") + pk_str + nk_str + fk_str,
                        "Data type":   c.get("data_type",""),
                        "Nullable":    null_str,
                        "Description": c.get("description",""),
                    })
                if col_rows:
                    st.dataframe(
                        pd.DataFrame(col_rows),
                        use_container_width=True,
                        hide_index=True,
                    )
                st.markdown("")


# ── Diagram tab ───────────────────────────────────────────────────────────────

def _render_diagram(mermaid: str):
    with st.expander("🔍 View raw Mermaid source"):
        st.code(mermaid, language="text")

    try:
        from streamlit_mermaid import st_mermaid
        st_mermaid(mermaid, height=600)
    except ImportError:
        st.info("Install `streamlit-mermaid` for rendered diagram.")
        st.code(mermaid, language="text")


# ── DDL tab ───────────────────────────────────────────────────────────────────

def _render_ddl(ddl_ansi: str, ddl_sf: str):
    dialect = st.radio(
        "Dialect",
        ["ANSI SQL", "Snowflake"],
        horizontal=True,
        label_visibility="collapsed",
    )
    ddl = ddl_ansi if dialect == "ANSI SQL" else ddl_sf

    col1, col2 = st.columns([3,1])
    with col1:
        st.caption(f"{ddl.count('CREATE TABLE')} tables · "
                   f"{ddl.count('CREATE OR REPLACE VIEW')} views · "
                   f"{len(ddl):,} chars")
    with col2:
        st.download_button(
            f"⬇️ Download {dialect} DDL",
            data=ddl,
            file_name=f"LDM_DDL_{'snowflake' if dialect=='Snowflake' else 'ansi'}.sql",
            mime="text/plain",
            use_container_width=True,
        )

    st.code(ddl[:6000] + ("\n\n-- ... (truncated — download for full DDL)" if len(ddl)>6000 else ""),
            language="sql")


# ── FR Coverage tab ───────────────────────────────────────────────────────────


def _render_validation(validation: dict):
    """Render validation agent results."""
    passed   = validation.get("passed", False)
    accepted = validation.get("accepted_with_issues", False)
    total    = validation.get("total_issues", 0)

    # Banner
    if passed:
        st.success("✅ LDM validation passed — all checks clear")
    elif accepted:
        st.warning(f"⚠️ LDM accepted with {total} issue(s) — max retries reached")
    else:
        st.error(f"❌ LDM has {total} issue(s)")

    # Summary metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("FR gaps",           validation.get("fr_gaps", 0))
    with c2: st.metric("Structural errors", validation.get("structural_errors", 0))
    with c3: st.metric("Struct warnings",   validation.get("structural_warnings", 0))
    with c4: st.metric("Grain issues",      validation.get("grain_issues", 0))

    st.divider()

    # Check 1 — FR coverage
    fr_checks = validation.get("fr_checks", [])
    if fr_checks:
        with st.expander(f"📋 FR Coverage ({sum(1 for c in fr_checks if c.get('status')=='COVERED')}/{len(fr_checks)} covered)", expanded=True):
            rows = []
            for c in fr_checks:
                rows.append({
                    "FR":          c.get("fr_id",""),
                    "Status":      c.get("status",""),
                    "Covered by":  c.get("covered_by","—"),
                    "Gap":         c.get("gap_description","—"),
                    "Fix":         c.get("repair_hint","—"),
                })
            if rows:
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)

    # Check 2 — Structural
    struct = validation.get("structural_checks", [])
    if struct:
        errors   = [s for s in struct if s.get("severity")=="ERROR"]
        warnings = [s for s in struct if s.get("severity")=="WARNING"]
        with st.expander(f"🏗️ Structural rules ({len(errors)} errors, {len(warnings)} warnings)", expanded=bool(errors)):
            for s in struct:
                icon = "❌" if s["severity"]=="ERROR" else "⚠️"
                st.markdown(f"{icon} **[{s['rule']}]** `{s['table']}` — {s['issue']}")
                st.caption(f"Fix: {s['fix']}")

    # Check 3 — Grain
    grain = validation.get("grain_checks", [])
    if grain:
        issues = [g for g in grain if g.get("grain_status")=="ISSUE"]
        with st.expander(f"⚖️ Grain validation ({len(issues)} issues)", expanded=bool(issues)):
            for g in grain:
                icon = "✅" if g.get("grain_status")=="CORRECT" else "❌"
                st.markdown(f"{icon} **{g.get('table_name','')}** — {g.get('declared_grain','')}")
                if g.get("grain_issue"):
                    st.caption(f"Issue: {g['grain_issue']}")
                if g.get("repair_hint"):
                    st.caption(f"Fix: {g['repair_hint']}")

    # Repair prompt
    repair = validation.get("repair_prompt")
    if repair:
        with st.expander("🔧 Repair prompt (used for Step B re-run)"):
            st.code(repair, language="text")


def _render_fr_coverage(fr_matrix: list[dict]):
    if not fr_matrix:
        st.info("No FR coverage data available.")
        return

    st.markdown(f"**{len(fr_matrix)} functional requirements covered by the LDM**")
    df = pd.DataFrame(fr_matrix)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.caption(
        "🔑 = Primary Key · 🏷️ = Natural Key · 🔗 = Foreign Key  |  "
        "ADD = Additive metric · SEMI = Semi-additive · NON-ADD = Non-additive ratio"
    )


# ── BigQuery PDM tab ──────────────────────────────────────────────────────────

def _render_pdm(pdm_result: dict):
    """Render BigQuery Physical Data Model output."""
    project     = pdm_result.get("project", "—")
    dataset     = pdm_result.get("dataset", "—")
    table_count = pdm_result.get("table_count", 0)
    audit_cols  = pdm_result.get("audit_cols", [])
    ddl_bq      = pdm_result.get("ddl_bq", "")
    summary     = pdm_result.get("summary", [])

    # ── Header metrics ────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("BQ Tables",      table_count)
    with c2: st.metric("Audit cols",      len(audit_cols), help="Added to every table")
    with c3: st.metric("Project",         project)
    with c4: st.metric("Dataset",         dataset)

    # ── Audit columns legend ──────────────────────────────────────────────
    with st.expander("ℹ️ Audit columns added to every table", expanded=False):
        AUDIT_DETAILS = [
            ("CREATED_AT",     "TIMESTAMP", "NOT NULL", "Row creation timestamp (UTC)"),
            ("UPDATED_AT",     "TIMESTAMP", "NOT NULL", "Last update timestamp (UTC)"),
            ("CREATED_BY",     "STRING",    "NOT NULL", "User or process that inserted the row"),
            ("UPDATED_BY",     "STRING",    "NOT NULL", "User or process that last updated the row"),
            ("ROW_VERSION",    "INT64",     "NOT NULL", "Optimistic-lock version counter"),
            ("IS_DELETED",     "BOOL",      "NOT NULL", "Soft-delete flag (logical delete)"),
            ("_ETL_BATCH_ID",  "STRING",    "",         "ETL job/batch identifier"),
            ("_ETL_LOAD_TS",   "TIMESTAMP", "",         "ETL ingestion timestamp — partition column"),
            ("_SOURCE_SYSTEM", "STRING",    "",         "Originating source system"),
            ("_RECORD_HASH",   "STRING",    "",         "SHA-256 hash of business keys for CDC"),
        ]
        df_audit = pd.DataFrame(AUDIT_DETAILS, columns=["Column", "BQ Type", "Constraint", "Purpose"])
        st.dataframe(df_audit, use_container_width=True, hide_index=True)

    st.divider()

    # ── Summary table ─────────────────────────────────────────────────────
    if summary:
        st.markdown("**Physical table summary**")
        df_sum = pd.DataFrame(summary)
        st.dataframe(df_sum, use_container_width=True, hide_index=True)
        st.divider()

    # ── DDL ───────────────────────────────────────────────────────────────
    st.markdown("**BigQuery DDL**")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(
            f"{ddl_bq.count('CREATE OR REPLACE TABLE')} tables · "
            f"{len(ddl_bq):,} chars"
        )
    with col2:
        st.download_button(
            "⬇️ Download BigQuery DDL",
            data=ddl_bq,
            file_name=f"PDM_BigQuery_{dataset}.sql",
            mime="text/plain",
            use_container_width=True,
        )

    st.code(
        ddl_bq[:8000] + ("\n\n-- ... (truncated — download for full DDL)" if len(ddl_bq) > 8000 else ""),
        language="sql",
    )

    # ── Conventions legend ────────────────────────────────────────────────
    st.divider()
    st.caption(
        "**Partitioning:** FACT / BRIDGE → `PARTITION BY DATE(_ETL_LOAD_TS)` · "
        "Large DIM (≥8 cols) → `PARTITION BY DATE(_ETL_LOAD_TS)` · "
        "Small DIM / REF → no partitioning  |  "
        "**Clustering:** FACT → top-4 FK `_KEY` cols · DIM → NK then PK · BRIDGE/REF → PK  |  "
        "**Constraints:** PRIMARY KEY / FOREIGN KEY `NOT ENFORCED` (BigQuery documentation constraints)"
    )
