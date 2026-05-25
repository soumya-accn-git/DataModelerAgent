import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

st.set_page_config(
    page_title="BRD → Conceptual Data Model",
    page_icon="🗂️",
    layout="wide",
)

from ui.sidebar import render_sidebar
from ui.upload import render_upload
from ui.pipeline import render_pipeline
from ui.output import render_output

def main():
    st.title("🗂️ BRD → Conceptual Data Model Generator")
    st.caption(
        "Upload a Business Requirements Document and the agent will extract "
        "entities, detect relationships, enrich with ontology, and generate a "
        "Conceptual Data Model."
    )

    render_sidebar()

    if "pipeline_result" not in st.session_state:
        st.session_state.pipeline_result = None
    if "pipeline_running" not in st.session_state:
        st.session_state.pipeline_running = False

    # Upload widget — sets session state flags, does not return file
    render_upload()

    # Pipeline runs only when triggered via session state
    if st.session_state.get("pipeline_running") and st.session_state.get("trigger_file"):
        render_pipeline(st.session_state["trigger_file"])

    # Output renders only when pipeline is done
    if st.session_state.pipeline_result:
        render_output(st.session_state.pipeline_result)

if __name__ == "__main__":
    main()
