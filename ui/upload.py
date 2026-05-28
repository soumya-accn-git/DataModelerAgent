import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import hashlib

def _compute_file_hash(uploaded_file) -> str:
    """Compute SHA256 hash of uploaded file content."""
    return hashlib.sha256(uploaded_file.getvalue()).hexdigest()

def render_upload():
    st.subheader("📄 Upload BRD")
    uploaded = st.file_uploader(
        "Drop your Business Requirements Document (.docx)",
        type=["docx"],
        label_visibility="visible",
    )
    if uploaded:
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.success(f"✅ **{uploaded.name}** ({uploaded.size/1024:.1f} KB)")
        
        # Compute file hash and check against previous upload
        file_hash = _compute_file_hash(uploaded)
        prev_hash = st.session_state.get("previous_brd_hash")
        has_cached_result = st.session_state.get("cached_pipeline_result") is not None
        
        if file_hash == prev_hash and has_cached_result:
            # Same file as before, ask if rescan is needed
            st.info("📌 This BRD is the same as the previously uploaded one.")
            col_rescan_yes, col_rescan_no = st.columns(2)
            with col_rescan_yes:
                if st.button("🔄 Re-scan for entities & relationships", use_container_width=True):
                    st.session_state["pipeline_running"] = True
                    st.session_state["trigger_file"] = uploaded
                    st.session_state["use_cache"] = False
                    st.session_state["pipeline_result"] = None
                    st.rerun()
            with col_rescan_no:
                if st.button("✅ Use previous scan result", use_container_width=True):
                    st.session_state["pipeline_running"] = False
                    st.session_state["use_cache"] = True
                    st.session_state["pipeline_result"] = st.session_state.get("cached_pipeline_result")
                    st.rerun()
        else:
            # New file, proceed with pipeline
            with col2:
                if st.button("▶ Run pipeline", type="primary", use_container_width=True,
                             disabled=st.session_state.get("pipeline_running", False)):
                    st.session_state["pipeline_running"] = True
                    st.session_state["trigger_file"] = uploaded
                    st.session_state["pipeline_result"] = None
                    st.session_state["previous_brd_hash"] = file_hash
                    st.session_state["use_cache"] = False
                    st.rerun()
        
        with col3:
            if st.button("✖ Clear", use_container_width=True):
                st.session_state["pipeline_running"] = False
                st.session_state["pipeline_result"] = None
                st.session_state["use_cache"] = False
                if "trigger_file" in st.session_state:
                    del st.session_state["trigger_file"]
                st.rerun()