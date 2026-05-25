import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import json
import pandas as pd
from agent.cdm_builder import result_to_mermaid, result_to_jsonld

# Badge colours for each entity type
TYPE_BADGES = {
    "core":       ("🔵", "Core"),
    "supporting": ("🟣", "Supporting"),
    "reference":  ("⚪", "Reference"),
    "event":      ("🟡", "Event"),
    "dimension":  ("🟢", "Dimension"),
    "metric":     ("🔴", "Metric"),
    "report":     ("🟠", "Report"),
    "filter":     ("🔷", "Filter"),
}

def render_output(result: dict):
    st.divider()
    st.subheader("📊 Conceptual Data Model")

    # Summary counts by type
    entities = result.get("entities", [])
    type_counts = {}
    for e in entities:
        t = e.get("type", "core")
        type_counts[t] = type_counts.get(t, 0) + 1

    cols = st.columns(len(type_counts) if type_counts else 1)
    for i, (t, count) in enumerate(sorted(type_counts.items())):
        icon, label = TYPE_BADGES.get(t, ("⚫", t.capitalize()))
        with cols[i]:
            st.metric(f"{icon} {label}", count)

    st.divider()

    tab_diagram, tab_entities, tab_relations, tab_json = st.tabs([
        "🗺️ Diagram", "📦 Entities", "🔗 Relationships", "📋 JSON-LD"
    ])

    with tab_diagram:
        _render_diagram(result)

    with tab_entities:
        _render_entities(result)

    with tab_relations:
        _render_relationships(result)

    with tab_json:
        _render_jsonld(result)

## Render the data model diagram

def _render_diagram(result):
    from streamlit_mermaid import st_mermaid

    mermaid_str = result_to_mermaid(result)

    st.markdown("**Entity-Relationship Diagram**")
    st_mermaid(mermaid_str, height=600)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Download Mermaid (.mmd)",
            data=mermaid_str,
            file_name="cdm.mmd",
            mime="text/plain",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            "⬇️ Download JSON-LD (.jsonld)",
            data=json.dumps(result_to_jsonld(result), indent=2),
            file_name="cdm.jsonld",
            mime="application/json",
            use_container_width=True,
        )

def _render_entities(result):
    entities = result.get("entities", [])
    if not entities:
        st.info("No entities found.")
        return

    st.markdown(f"**{len(entities)} entities extracted**")

    # Filter by type
    all_types = sorted(set(e.get("type", "core") for e in entities))
    selected_types = st.multiselect(
        "Filter by type",
        options=all_types,
        default=all_types,
        format_func=lambda t: f"{TYPE_BADGES.get(t, ('⚫',''))[0]} {TYPE_BADGES.get(t, ('','Unknown'))[1]}",
    )

    filtered = [e for e in entities if e.get("type", "core") in selected_types]

    rows = []
    for e in filtered:
        icon, label = TYPE_BADGES.get(e.get("type", "core"), ("⚫", "Unknown"))
        rows.append({
            "Type": f"{icon} {label}",
            "Entity": e.get("name", ""),
            "Description": e.get("description", ""),
            "Attributes": ", ".join(e.get("attributes", [])),
            "Ontology match": ", ".join(e.get("ontology_matches", [])),
            "Source": e.get("source", ""),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Download entities CSV",
        data=df.to_csv(index=False),
        file_name="entities.csv",
        mime="text/csv",
    )


def _render_relationships(result):
    relationships = result.get("relationships", [])
    if not relationships:
        st.info("No relationships found.")
        return

    st.markdown(f"**{len(relationships)} relationships detected**")

    rows = []
    for r in relationships:
        rows.append({
            "From": r.get("from_entity", ""),
            "Relationship": r.get("label", ""),
            "To": r.get("to_entity", ""),
            "Cardinality": r.get("cardinality", ""),
            "Ontology type": r.get("ontology_type", ""),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Download relationships CSV",
        data=df.to_csv(index=False),
        file_name="relationships.csv",
        mime="text/csv",
    )


def _render_jsonld(result):
    jsonld = result_to_jsonld(result)
    st.code(json.dumps(jsonld, indent=2), language="json")
