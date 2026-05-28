import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
from agent.pipeline_agent import run_pipeline

STEPS = [
    ("📖", "Document parsing"),
    ("🧬", "Ontology building"),
    ("🔍", "Entity extraction"),
    ("🔗", "Relationship detection"),
    ("🧠", "Ontology enrichment"),
    ("🦉", "OWL/SHACL rules"),
    ("🏗️", "CDM generation"),
]

def render_pipeline(uploaded_file):
    # Check if using cached result
    if st.session_state.get("use_cache"):
        return

    if not st.session_state.get("pipeline_running"):
        return

    st.divider()
    st.subheader("⚡ Pipeline")

    cols = st.columns(len(STEPS))
    placeholders = []
    for i, (icon, name) in enumerate(STEPS):
        with cols[i]:
            ph = st.empty()
            ph.markdown(f"**{icon} {name}**  \n⬜ waiting")
            placeholders.append(ph)

    progress_bar = st.progress(0)
    log_ph = st.empty()

    def on_start(i):
        icon, name = STEPS[i]
        placeholders[i].markdown(f"**{icon} {name}**  \n⏳ running…")
        progress_bar.progress(i / len(STEPS))

    def on_done(i, detail=""):
        icon, name = STEPS[i]
        placeholders[i].markdown(f"**{icon} {name}**  \n✅ {detail}")
        progress_bar.progress((i + 1) / len(STEPS))

    def on_log(msg):
        log_ph.caption(f"🔧 {msg}")

    try:
        result = run_pipeline(
            file=uploaded_file,
            ollama_url=st.session_state.get("ollama_url", "http://localhost:11434"),
            model=st.session_state.get("ollama_model", "llama3.1:8b"),
            chroma_path=st.session_state.get("chroma_path", "./chroma_db"),
            temperature=st.session_state.get("temperature", 0.1),
            top_k=st.session_state.get("top_ontology_k", 3),
            on_step_start=on_start,
            on_step_done=on_done,
            on_log=on_log,
        )
        log_ph.empty()
        progress_bar.progress(1.0)
        st.success("🎉 Pipeline complete!")
        st.session_state["pipeline_result"] = result
        # Cache the result for future use
        st.session_state["cached_pipeline_result"] = result
    except Exception as e:
        st.error(f"❌ Pipeline failed: {e}")
        import traceback
        st.code(traceback.format_exc(), language="python")
    finally:
        st.session_state["pipeline_running"] = False
        if "trigger_file" in st.session_state:
            del st.session_state["trigger_file"]
