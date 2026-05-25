import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import streamlit as st

def render_upload():
    st.subheader("📄 Upload BRD")
    uploaded = st.file_uploader(
        "Drop your Business Requirements Document here",
        type=["docx"],
        help="Only .docx files are supported.",
    )

    if uploaded:
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.success(f"✅ **{uploaded.name}** ({uploaded.size / 1024:.1f} KB)")
        with col2:
            run = st.button(
                "▶ Run pipeline",
                type="primary",
                use_container_width=True,
                disabled=st.session_state.get("pipeline_running", False),
            )
            if run:
                st.session_state["pipeline_running"] = True
                st.session_state["trigger_file"] = uploaded
                st.session_state["pipeline_result"] = None
                st.rerun()
        with col3:
            if st.button("✖ Clear file", use_container_width=True):
                st.session_state["pipeline_running"] = False
                st.session_state["pipeline_result"] = None
                if "trigger_file" in st.session_state:
                    del st.session_state["trigger_file"]
                st.rerun()
