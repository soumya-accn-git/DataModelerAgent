import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
import streamlit as st
import json
import pandas as pd
from src.pipeline.cdm_builder import result_to_mermaid, result_to_jsonld
from src.ui.graph_view import render_graph
from src.ui.ldm_output import render_ldm_output

TYPE_BADGES = {
    "core":       ("badge-core",       "🔵 Core"),
    "supporting": ("badge-supporting", "🟣 Supporting"),
    "reference":  ("badge-reference",  "⚪ Reference"),
    "event":      ("badge-event",      "🟡 Event"),
    "dimension":  ("badge-dimension",  "🟢 Dimension"),
    "fact":       ("badge-fact",       "🔴 Fact"),
    "metric":     ("badge-metric",     "🔴 Metric"),
    "report":     ("badge-report",     "🟠 Report"),
    "filter":     ("badge-filter",     "🔷 Filter"),
    "bridge":     ("badge-bridge",     "🟣 Bridge"),
}

def render_output(result: dict):
    # Summary counts
    entities      = result.get("entities", [])
    relationships = result.get("relationships", [])
    inferred      = result.get("inferred_entities", [])
    violations    = result.get("shacl_violations", [])
    stats         = result.get("stats", {})

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("Entities",      stats.get("entity_count", len(entities)))
    with c2: st.metric("Relationships", stats.get("relationship_count", len(relationships)))
    with c3: st.metric("Inferred",      len(inferred), help="Entities inferred by OWL rules from report names")
    with c4: st.metric("SHACL issues",  len(violations), help="SHACL shape validation results")
    with c5: st.metric("Sections",      stats.get("section_count","—"))

    # LDM result from session state
    ldm_result = st.session_state.get("ldm_result")

    # Tab order: Pipeline, Domain, Graph, Entities, Relationships, CDM, LDM, OWL/SHACL, JSON-LD
    tab_names = [
        "⚡  Pipeline",
        "🧬  Domain",
        "🕸️  Graph",
        "📦  Entities",
        "🔗  Relationships",
        "🗺️  CDM",
        "🦉  OWL / SHACL",
        "📋  JSON-LD",
    ]
    if ldm_result:
        tab_names.insert(6, "🏛️  LDM")

    tabs = st.tabs(tab_names)
    tab_iter = iter(tabs)

    with next(tab_iter): _render_pipeline_summary(result)
    with next(tab_iter): _render_domain(result)
    with next(tab_iter): render_graph(result)
    with next(tab_iter): _render_entities(result)
    with next(tab_iter): _render_relationships(result)
    with next(tab_iter): _render_diagram(result)
    if ldm_result:
        with next(tab_iter): render_ldm_output(ldm_result)
    with next(tab_iter): _render_owl(result)
    with next(tab_iter): _render_jsonld(result)


def _render_pipeline_summary(result: dict):
    timing = result.get("_pipeline_timing", {})
    steps  = timing.get("steps", [])
    total  = timing.get("total_duration", 0)

    if not steps:
        st.info("Pipeline timing not available. Re-run the pipeline to see step details.")
        return

    # ── Total duration banner ──────────────────────────────────────────────
    def _fmt(s):
        if s < 1:   return f"{s*1000:.0f}ms"
        if s < 60:  return f"{s:.1f}s"
        m, sec = divmod(int(s), 60)
        return f"{m}m {sec}s"

    st.markdown(
        f"<div style=\"padding:12px 16px;background:var(--color-background-secondary);"
        f"border-radius:8px;border:1px solid var(--color-border-tertiary);"
        f"margin-bottom:12px;\">"
        f"<span style=\"font-size:1.1rem;font-weight:600\">Total runtime: {_fmt(total)}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Step-by-step table ─────────────────────────────────────────────────
    longest = max((s["duration"] for s in steps), default=1) or 1

    for step in steps:
        idx  = step["idx"]
        icon = step["icon"]
        name = step["name"]
        dur  = step["duration"]
        pct  = dur / longest if longest > 0 else 0

        col_icon, col_name, col_bar, col_dur = st.columns([0.5, 2.5, 5, 1.5])

        with col_icon:
            st.markdown(f"<div style=\"font-size:1.2rem;padding-top:4px\">{icon}</div>",
                        unsafe_allow_html=True)
        with col_name:
            st.markdown(
                f"<div style=\"padding-top:6px;font-size:0.88rem;font-weight:500\">"
                f"Step {idx+1} · {name}</div>",
                unsafe_allow_html=True,
            )
        with col_bar:
            # Horizontal bar proportional to duration
            color = "#1F6FEB" if dur > 0 else "#484F58"
            bar_pct = max(int(pct * 100), 2)
            st.markdown(
                f"<div style=\"margin-top:8px;height:10px;border-radius:5px;"
                f"background:var(--color-border-tertiary);overflow:hidden;\">"
                f"<div style=\"width:{bar_pct}%;height:100%;background:{color};"
                f"border-radius:5px;transition:width 0.3s\"></div></div>",
                unsafe_allow_html=True,
            )
        with col_dur:
            dur_str = _fmt(dur) if dur > 0 else "—"
            st.markdown(
                f"<div style=\"padding-top:4px;font-size:0.85rem;"
                f"font-family:monospace;text-align:right\">{dur_str}</div>",
                unsafe_allow_html=True,
            )

    # ── GraphRAG stats if available ────────────────────────────────────────
    graphrag = result.get("graphrag", {})
    if graphrag and graphrag.get("neo4j_available"):
        st.divider()
        st.markdown("**GraphRAG extraction summary**")
        g1, g2, g3 = st.columns(3)
        with g1: st.metric("Graph nodes extracted", graphrag.get("nodes_extracted", 0))
        with g2: st.metric("Graph rels extracted",  graphrag.get("rels_extracted", 0))
        with g3: st.metric("Context chars",         f"{graphrag.get('context_chars',0):,}")



def _render_domain(result):
    domain = result.get("domain", {})
    if not domain:
        st.info("No domain information available.")
        return

    from_cache = domain.get("from_cache", False)
    cache_badge = " ⚡ *(cached — BRD unchanged)*" if from_cache else " 🆕 *(built from this BRD)*"
    st.subheader(f"🧬 Domain: {domain.get('name','—')}")
    st.caption(domain.get("description","") + cache_badge)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Generated files**")
        owl_file   = domain.get("owl_file","")
        shacl_file = domain.get("shacl_file","")
        if owl_file:
            st.markdown(f"📄 `ontology/generated/{owl_file}`")
        if shacl_file:
            st.markdown(f"📄 `ontology/generated/{shacl_file}`")

        # Download OWL file
        import os
        gen_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ontology", "generated")
        if owl_file:
            owl_path = os.path.join(gen_dir, owl_file)
            if os.path.exists(owl_path):
                with open(owl_path) as f:
                    st.download_button("⬇️ Download OWL (.ttl)",
                        data=f.read(), file_name=owl_file, mime="text/turtle")
        if shacl_file:
            shacl_path = os.path.join(gen_dir, shacl_file)
            if os.path.exists(shacl_path):
                with open(shacl_path) as f:
                    st.download_button("⬇️ Download SHACL (.ttl)",
                        data=f.read(), file_name=shacl_file, mime="text/turtle")

    with col2:
        st.markdown("**Key metrics (Fact attributes)**")
        for m in domain.get("key_metrics", []):
            st.markdown(f"- `{m}`")

    st.divider()

    col3, col4 = st.columns(2)
    with col3:
        forbidden = domain.get("forbidden_names", [])
        if forbidden:
            st.markdown("**Forbidden patterns (from BRD)**")
            st.caption("Report/dashboard names excluded from CDM entities")
            for name in forbidden:
                st.markdown(f"- 🚫 `{name}`")
    with col4:
        filter_to_dim = domain.get("filter_to_dim", [])
        if filter_to_dim:
            st.markdown("**Filter → Dimension mappings (Rule R6)**")
            rows = [{"Filter/Prompt": m.get("filter",""), "→ Dimension": m.get("dimension","")} for m in filter_to_dim]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # GraphRAG info card
    graphrag = result.get("graphrag", {})
    if graphrag:
        st.divider()
        st.markdown("**GraphRAG pipeline**")
        g1, g2, g3, g4, g5, g6 = st.columns(6)
        with g1:
            neo4j_ok = graphrag.get("neo4j_available", False)
            st.metric("Neo4j", "✅ Active" if neo4j_ok else "⚠️ Fallback")
        with g2:
            st.metric("Sections", graphrag.get("sections_loaded", 0))
        with g3:
            st.metric("Graph nodes", graphrag.get("nodes_extracted", 0),
                      help="Nodes extracted by LLMGraphTransformer")
        with g4:
            st.metric("Graph rels", graphrag.get("rels_extracted", 0),
                      help="Relationships extracted by LLMGraphTransformer")
        with g5:
            st.metric("Context chars", f"{graphrag.get('context_chars',0):,}")
        with g6:
            st.metric("Parser", graphrag.get("parser_used", "—"))



def _render_diagram(result):
    mermaid_str = result_to_mermaid(result)

    # Always show raw Mermaid text in expander for debugging
    with st.expander("🔍 View raw Mermaid source"):
        st.code(mermaid_str, language="text")

    try:
        from streamlit_mermaid import st_mermaid
        st_mermaid(mermaid_str, height=480)
    except ImportError:
        st.info("💡 Run `pip install streamlit-mermaid` for rendered diagrams.")
        st.code(mermaid_str, language="text")
    except Exception as exc:
        errors = _validate_mermaid_source(mermaid_str)
        if errors:
            st.warning("⚠️ Mermaid rendering failed and validation found issues.")
            for err in errors:
                st.write(f"- {err}")

        st.error("⚠️ Mermaid rendering failed. Showing raw source below.")
        st.write(f"**Error:** {exc}")
        st.code(_add_line_numbers(mermaid_str), language="text")

        fallback_mermaid = _build_fallback_graph(result)
        st.info("💡 Attempting a simpler fallback diagram using a generic graph layout.")
        try:
            st_mermaid(fallback_mermaid, height=480)
            st.success("Fallback diagram rendered successfully.")
        except Exception as exc2:
            st.error("⚠️ Fallback rendering also failed.")
            st.write(f"**Fallback error:** {exc2}")
            st.code(_add_line_numbers(fallback_mermaid), language="text")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Mermaid (.mmd)", data=mermaid_str,
            file_name="cdm.mmd", mime="text/plain", use_container_width=True)
    with c2:
        st.download_button("⬇️ JSON-LD (.jsonld)",
            data=json.dumps(result_to_jsonld(result), indent=2),
            file_name="cdm.jsonld", mime="application/json", use_container_width=True)


def _validate_mermaid_source(mermaid_str: str) -> list[str]:
    errors = []
    brace_stack = []

    for idx, line in enumerate(mermaid_str.splitlines(), start=1):
        stripped = line.strip()
        if stripped.endswith("{"):
            brace_stack.append(idx)
        elif stripped == "}":
            if brace_stack:
                brace_stack.pop()
            else:
                errors.append(f"Line {idx}: unexpected closing brace")

        if '"' in line and line.count('"') % 2 != 0:
            errors.append(f"Line {idx}: unbalanced quote character")

        if ": \"" in line and not line.rstrip().endswith('"'):
            errors.append(f"Line {idx}: relationship label is not properly quoted")

        if stripped and not line.startswith("  ") and not stripped.startswith("erDiagram") and not stripped.startswith("%%"):
            errors.append(f"Line {idx}: unexpected Mermaid indentation or syntax")

    for ln in brace_stack:
        errors.append(f"Line {ln}: opening brace has no matching closing brace")

    return errors


def _add_line_numbers(source: str) -> str:
    return "\n".join(f"{idx:>3}: {line}" for idx, line in enumerate(source.splitlines(), start=1))


def _build_fallback_graph(result) -> str:
    lines = ["graph TD"]
    entities = result.get("entities", [])
    relationships = result.get("relationships", [])

    for e in entities:
        name = _safe_name(e.get("name", ""))
        label = e.get("name", "")
        if not name:
            continue
        lines.append(f'    {name}["{label}"]')

    for r in relationships:
        from_e = _safe_name(r.get("from_entity", ""))
        to_e = _safe_name(r.get("to_entity", ""))
        label = r.get("label", "relates to").replace('"', '')
        if not from_e or not to_e:
            continue
        lines.append(f'    {from_e} --|{label}| {to_e}')

    return "\n".join(lines)


def _render_entities(result):
    entities = result.get("entities", [])
    if not entities:
        st.info("No entities found.")
        return

    all_types = sorted(set(e.get("type","core") for e in entities))
    selected  = st.multiselect(
        "Filter by type", options=all_types, default=all_types,
        format_func=lambda t: TYPE_BADGES.get(t,("",""))[1] or t,
    )

    filtered = [e for e in entities if e.get("type","core") in selected]

    rows = []
    for e in filtered:
        _, label = TYPE_BADGES.get(e.get("type","core"), ("","core"))
        inferred_flag = " *(inferred)*" if e.get("inferred") else ""
        rows.append({
            "Type":          label,
            "Entity":        e.get("name","") + inferred_flag,
            "Description":   e.get("description",""),
            "Ontology match":e.get("ontology_matches",[""])[0] if e.get("ontology_matches") else "",
            "Source":        e.get("source",""),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=380)
    st.download_button("⬇️ Download entities CSV",
        data=df.to_csv(index=False), file_name="entities.csv", mime="text/csv")


def _render_relationships(result):
    relationships = result.get("relationships", [])
    if not relationships:
        st.info("No relationships found.")
        return

    rows = []
    for r in relationships:
        inferred_flag = " *(inferred)*" if r.get("inferred") else ""
        rows.append({
            "From":          r.get("from_entity",""),
            "Relationship":  r.get("label","") + inferred_flag,
            "To":            r.get("to_entity",""),
            "Cardinality":   r.get("cardinality",""),
            "Ontology type": r.get("ontology_type",""),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=380)
    st.download_button("⬇️ Download relationships CSV",
        data=df.to_csv(index=False), file_name="relationships.csv", mime="text/csv")


def _render_owl(result):
    inferred      = result.get("inferred_entities", [])
    violations    = result.get("shacl_violations", [])
    entities      = result.get("entities", [])
    relationships = result.get("relationships", [])

    # Split inferred into filter-derived vs report-derived
    filter_inferred = [e for e in inferred if e.get("inferred_from_filter")]
    report_inferred = [e for e in inferred if not e.get("inferred_from_filter")]

    # ── R6 — Filter/Prompt derived dimensions ──────────────────────────────
    st.subheader("🔷 Rule R6 — Filter/Prompt → Dimension Inference")
    st.caption(
        "These dimension entities were not stated directly in the BRD. "
        "They were inferred from filter and prompt names by OWL Rule R6."
    )

    if filter_inferred:
        rows = []
        for e in filter_inferred:
            _, label = TYPE_BADGES.get(e.get("type","dimension"), ("",""))
            rows.append({
                "Inferred entity":   e.get("name",""),
                "Type":              label,
                "Inferred from":     e.get("inferred_from_filter",""),
                "Description":       e.get("description",""),
                "Ontology":          ", ".join(e.get("ontology_matches",[])),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No filter/prompt entities found in this BRD.")

    st.markdown("---")

    # ── R1/R2 — Report-derived entities ───────────────────────────────────
    st.subheader("🟠 Rules R1/R2 — Report/Dashboard → Dimension/Fact Inference")
    st.caption(
        "These entities were inferred from report and dashboard names. "
        "They represent the real data entities that feed those reports."
    )

    report_entities = [e for e in entities if e.get("type") == "report"]
    if report_entities:
        for report in report_entities:
            feeding = [
                r["from_entity"] for r in relationships
                if r.get("to_entity") == report["name"]
                and r.get("label") == "feeds"
                and r.get("inferred")
            ]
            if feeding:
                with st.expander(f"🟠 {report['name']} ← fed by {len(feeding)} inferred entities"):
                    for fe in feeding:
                        entity = next((e for e in report_inferred if e["name"] == fe), None)
                        if entity:
                            _, label = TYPE_BADGES.get(entity.get("type","dimension"),("",""))
                            st.markdown(
                                f"**{label} — {entity['name']}**  \n"
                                f"{entity.get('description','')}  \n"
                                f"*Ontology: {', '.join(entity.get('ontology_matches',[]))}*"
                            )
    else:
        st.info("No report/dashboard entities found in this BRD.")

    st.markdown("---")

    # ── SHACL Validation ───────────────────────────────────────────────────
    st.subheader("✅ SHACL Validation Report")
    st.caption(
        "Shape Constraint Language checks for naming conventions, "
        "missing descriptions, type correctness and duplicate names."
    )

    if not violations:
        st.success("✅ All SHACL shape constraints passed.")
    else:
        errors   = [v for v in violations if v.get("severity") == "Error"]
        warnings = [v for v in violations if v.get("severity") == "Warning"]
        if errors:
            st.error(f"❌ {len(errors)} errors")
            st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)
        if warnings:
            st.warning(f"⚠️ {len(warnings)} warnings")
            st.dataframe(pd.DataFrame(warnings), use_container_width=True, hide_index=True)



def _render_jsonld(result):
    st.code(json.dumps(result_to_jsonld(result), indent=2), language="json")