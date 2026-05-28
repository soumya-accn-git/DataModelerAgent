import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import json
import pandas as pd
from agent.cdm_builder import result_to_mermaid, result_to_jsonld

TYPE_BADGES = {
    "core":       ("badge-core",       "🔵 Core"),
    "supporting": ("badge-supporting", "🟣 Supporting"),
    "reference":  ("badge-reference",  "⚪ Reference"),
    "event":      ("badge-event",      "🟡 Event"),
    "dimension":  ("badge-dimension",  "🟢 Dimension"),
    "metric":     ("badge-metric",     "🔴 Metric"),
    "report":     ("badge-report",     "🟠 Report"),
    "filter":     ("badge-filter",     "🔷 Filter"),
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

    tab_domain, tab_diagram, tab_entities, tab_relations, tab_owl, tab_json = st.tabs([
        "🧬  Domain",
        "🗺️  Diagram",
        "📦  Entities",
        "🔗  Relationships",
        "🦉  OWL / SHACL",
        "📋  JSON-LD",
    ])

    with tab_domain:    _render_domain(result)
    with tab_diagram:   _render_diagram(result)
    with tab_entities:  _render_entities(result)
    with tab_relations: _render_relationships(result)
    with tab_owl:       _render_owl(result)
    with tab_json:      _render_jsonld(result)


def _render_domain(result):
    domain = result.get("domain", {})
    if not domain:
        st.info("No domain information available.")
        return

    st.subheader(f"🧬 Domain: {domain.get('name','—')}")
    st.caption(domain.get("description",""))

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
        gen_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ontology", "generated")
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
        st.markdown("**Expected dimensions**")
        for d in domain.get("dimensions", []):
            st.markdown(f"- 🟢 `{d}`")
    with col4:
        st.markdown("**Expected facts**")
        for f in domain.get("facts", []):
            st.markdown(f"- 🔴 `{f}`")

    filters = domain.get("filters", [])
    if filters:
        st.divider()
        st.markdown("**Filter → Dimension mappings (Rule R6)**")
        rows = [{"Filter/Prompt": f.get("filter_name",""), "→ Dimension": f.get("implied_dimension","")} for f in filters]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)



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