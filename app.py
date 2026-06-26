import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from config import (
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE,
    AURA_INSTANCENAME, OLLAMA_URL, CHROMA_PATH,
)

st.set_page_config(
    page_title="DataModelerAgent",
    page_icon="🗂️",
    layout="wide",
)

st.markdown("""
<style>
/* Tighten global spacing */
.block-container {
    padding-top: 4.5rem !important;
    padding-bottom: 0.5rem !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
}
/* Compact headings */
h1 {
    font-size: 1.3rem !important;
    margin-bottom: 0 !important;
    white-space: normal !important;
    overflow: visible !important;
    width: 100% !important;
    max-width: 100% !important;
}
h2 { font-size: 1.1rem !important; margin-bottom: 0.2rem !important; }
h3 { font-size: 1rem !important; margin-bottom: 0.2rem !important; }
/* Compact widgets */
[data-testid="stVerticalBlock"] > div { gap: 0.4rem !important; }
[data-testid="stFileUploader"] { margin-bottom: 0.3rem !important; }
.stButton > button { padding: 0.3rem 0.8rem !important; font-size: 0.82rem !important; }
[data-testid="stMetric"] { padding: 0.4rem 0.6rem !important; }
[data-testid="stMetricValue"] { font-size: 1.4rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.72rem !important; }
/* Sidebar compact */
[data-testid="stSidebar"] { min-width: 220px !important; max-width: 240px !important; }
[data-testid="stSidebar"] .block-container {
    padding-top: 0.8rem !important;
    padding-left: 0.8rem !important;
    padding-right: 0.8rem !important;
}
[data-testid="stSidebar"] h2 { font-size: 0.85rem !important; }
[data-testid="stSidebar"] label { font-size: 0.78rem !important; }
[data-testid="stSidebar"] [data-testid="stSelectbox"] { margin-bottom: 0.2rem !important; }
/* Compact tabs */
[data-testid="stTabs"] [data-baseweb="tab"] {
    padding: 0.35rem 0.9rem !important;
    font-size: 0.82rem !important;
}
/* Compact dataframe */
[data-testid="stDataFrame"] { font-size: 0.8rem !important; }
/* Compact captions and text */
[data-testid="stCaptionContainer"] { font-size: 0.75rem !important; }
p { font-size: 0.85rem !important; margin-bottom: 0.2rem !important; }
/* Compact divider */
hr { margin: 0.4rem 0 !important; }
/* Compact alerts */
[data-testid="stAlert"] { padding: 0.4rem 0.8rem !important; font-size: 0.82rem !important; }
/* Compact progress */
[data-testid="stProgress"] { margin: 0.3rem 0 !important; }
/* Compact success/error */
.stSuccess, .stError, .stWarning { padding: 0.4rem 0.8rem !important; }
/* Tighten columns gap */
[data-testid="column"] { padding: 0 0.3rem !important; }
</style>
""", unsafe_allow_html=True)



from src.ui.sidebar import render_sidebar
from src.ui.upload import render_upload
from src.ui.pipeline_ui import render_pipeline
from src.ui.output import render_output
from src.ui.ldm_output import render_ldm_output
from src.ui.chat import render_chat

def main():
    defaults = {
        "pipeline_result":        None,
        "ldm_result":             None,
        "pdm_result":             None,
        "pipeline_running":       False,
        "pipeline_status":        None,
        "show_pipeline_status":   False,
        "use_cache":              False,
        "previous_brd_hash":      None,
        "cached_pipeline_result": None,
        "pipeline_mode":          "CDM only",
        "ollama_url":             OLLAMA_URL,
        "ollama_model":           "llama3.1:8b",
        "chroma_path":            CHROMA_PATH,
        "temperature":            0.1,
        "top_ontology_k":         3,
        "max_chunks":             4,
        "bq_project":             "your_gcp_project",
        "bq_dataset":             "MERCH_DW",
        # chat
        "chat_messages":           [],
        "chat_triggered_pipeline": False,
        "chat_pipeline_mode":      None,
        "current_uploaded_file":   None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    st.title("🗂️ DataModelerAgent — BRD → Conceptual Data Model")

    render_sidebar()
    render_upload()
    render_chat()

    if st.session_state.get("pipeline_running") and st.session_state.get("trigger_file"):
        render_pipeline(st.session_state["trigger_file"])

    cdm_result = st.session_state.get("pipeline_result")
    ldm_result = st.session_state.get("ldm_result")
    mode       = st.session_state.get("pipeline_mode", "CDM only")

    # In LDM-only mode prioritise LDM output; the CDM (restored from cache by
    # _restore_cached so the pipeline thread can use it) is just the input and
    # should not be rendered as the primary result.
    if mode == "LDM only" and ldm_result:
        render_ldm_output(ldm_result)
    elif cdm_result:
        render_output(cdm_result)
        if ldm_result:
            render_ldm_output(ldm_result)
    elif ldm_result:
        render_ldm_output(ldm_result)

if __name__ == "__main__":
    main()
