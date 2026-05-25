import streamlit as st
import time
from agent.pipeline import run_pipeline

STEPS = [
    ("📖", "Document parsing",       "Reading and cleaning the .docx file"),
    ("🔍", "Entity extraction",      "Identifying entities with the LLM"),
    ("🔗", "Relationship detection", "Inferring relationships and cardinality"),
    ("🧠", "Ontology enrichment",    "Matching entities to ontology concepts via ChromaDB"),
    ("🏗️", "CDM generation",         "Building the Conceptual Data Model graph"),
]

def render_pipeline(uploaded_file):
    if not st.session_state.get("pipeline_running"):
        return

    st.divider()
    st.subheader("⚡ Pipeline execution")

    step_placeholders = []
    for icon, name, desc in STEPS:
        col1, col2 = st.columns([1, 8])
        with col1:
            ph_icon = st.empty()
            ph_icon.markdown(f"<div style='font-size:1.6rem;text-align:center'>{icon}</div>", unsafe_allow_html=True)
        with col2:
            ph_status = st.empty()
            ph_status.markdown(
                f"**{name}** — <span style='color:gray'>{desc}</span>",
                unsafe_allow_html=True,
            )
        step_placeholders.append((ph_icon, ph_status, icon, name))

    log_placeholder = st.empty()
    progress_bar = st.progress(0)

    def on_step_start(step_idx):
        _, ph_status, icon, name = step_placeholders[step_idx]
        ph_status.markdown(
            f"**{name}** ⏳ *running…*",
            unsafe_allow_html=True,
        )
        progress_bar.progress((step_idx) / len(STEPS))

    def on_step_done(step_idx, detail=""):
        _, ph_status, icon, name = step_placeholders[step_idx]
        detail_str = f" — {detail}" if detail else ""
        ph_status.markdown(
            f"**{name}** ✅{detail_str}",
            unsafe_allow_html=True,
        )
        progress_bar.progress((step_idx + 1) / len(STEPS))

    def on_log(msg):
        log_placeholder.caption(f"🔧 {msg}")

    try:
        result = run_pipeline(
            file=uploaded_file,
            ollama_url=st.session_state.get("ollama_url", "http://localhost:11434"),
            model=st.session_state.get("ollama_model", "llama3.1:8b"),
            chroma_path=st.session_state.get("chroma_path", "./chroma_db"),
            temperature=st.session_state.get("temperature", 0.1),
            top_k=st.session_state.get("top_ontology_k", 3),
            on_step_start=on_step_start,
            on_step_done=on_step_done,
            on_log=on_log,
        )
        log_placeholder.empty()
        progress_bar.progress(1.0)
        st.success("🎉 Pipeline complete!")
        st.session_state["pipeline_result"] = result
    except Exception as e:
        st.error(f"❌ Pipeline failed: {e}")
        import traceback
        st.code(traceback.format_exc(), language="python")
    finally:
        st.session_state["pipeline_running"] = False
        if "trigger_file" in st.session_state:
            del st.session_state["trigger_file"]
