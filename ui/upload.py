"""
Upload panel — BRD file upload with three pipeline run options.

Three run modes shown as distinct buttons:
  ▶ CDM only      — full 8-step CDM pipeline
  ▶ CDM + LDM     — CDM pipeline then LDM Steps A+B
  ▶ LDM only      — skip CDM, use stored CDM result, run Steps A+B only

Same-BRD detection: if the uploaded file matches the previous hash,
shows cached result options alongside the re-run buttons.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import hashlib


def _file_hash(uploaded_file) -> str:
    return hashlib.sha256(uploaded_file.getvalue()).hexdigest()[:16]


def _trigger(uploaded, mode: str, use_cache: bool = False):
    """Set session state and rerun to trigger the pipeline."""
    st.session_state["pipeline_mode"]    = mode
    st.session_state["pipeline_running"] = True
    st.session_state["trigger_file"]     = uploaded
    st.session_state["use_cache"]        = use_cache
    st.session_state["pipeline_result"]  = None
    if not use_cache:
        st.session_state["previous_brd_hash"] = _file_hash(uploaded)
    st.rerun()


def render_upload():
    st.subheader("📄 Upload BRD")

    uploaded = st.file_uploader(
        "Drop your Business Requirements Document (.docx)",
        type=["docx"],
        label_visibility="visible",
    )

    if not uploaded:
        return

    # ── File info row ──────────────────────────────────────────────────────
    file_hash    = _file_hash(uploaded)
    prev_hash    = st.session_state.get("previous_brd_hash")
    same_brd     = file_hash == prev_hash
    has_cdm      = st.session_state.get("pipeline_result") is not None or _has_stored_cdm(file_hash)
    has_ldm      = st.session_state.get("ldm_result") is not None or _has_stored_ldm(file_hash)
    is_running   = st.session_state.get("pipeline_running", False)

    # File badge row
    c_file, c_clear = st.columns([5, 1])
    with c_file:
        cdm_badge = "CDM ✅" if has_cdm else "CDM —"
        ldm_badge = "LDM ✅" if has_ldm else "LDM —"
        st.success(
            f"**{uploaded.name}** · {uploaded.size/1024:.1f} KB · "
            f"`{file_hash}` · {cdm_badge} · {ldm_badge}"
        )
    with c_clear:
        if st.button("✖ Clear", use_container_width=True):
            for k in ["pipeline_running","pipeline_result","ldm_result",
                      "use_cache","trigger_file","cached_pipeline_result"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── Restore cached results if same BRD ────────────────────────────────
    if same_brd and has_cdm and not st.session_state.get("pipeline_result"):
        _restore_cached(file_hash)

    # ── Run buttons ────────────────────────────────────────────────────────
    st.markdown("**Run pipeline**")

    b1, b2, b3 = st.columns(3)

    with b1:
        st.markdown(
            '<div style="border:1px solid var(--color-border-tertiary);'
            'border-radius:8px;padding:.6rem .8rem;margin-bottom:.3rem">'
            '<div style="font-size:12px;font-weight:500;margin-bottom:3px">📊 CDM only</div>'
            '<div style="font-size:11px;color:var(--color-text-secondary)">Full 8-step pipeline · Conceptual Data Model</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button(
            "▶ Run CDM",
            key="btn_cdm_only",
            type="primary",
            use_container_width=True,
            disabled=is_running,
        ):
            _trigger(uploaded, "CDM only")

    with b2:
        st.markdown(
            '<div style="border:1px solid var(--color-border-tertiary);'
            'border-radius:8px;padding:.6rem .8rem;margin-bottom:.3rem">'
            '<div style="font-size:12px;font-weight:500;margin-bottom:3px">🏛️ CDM + LDM</div>'
            '<div style="font-size:11px;color:var(--color-text-secondary)">CDM pipeline then LDM Steps A+B</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button(
            "▶ Run CDM + LDM",
            key="btn_cdm_ldm",
            type="primary",
            use_container_width=True,
            disabled=is_running,
        ):
            _trigger(uploaded, "CDM + LDM")

    with b3:
        ldm_tip = "Requires a stored CDM result" if not has_cdm else "Uses stored CDM — runs Steps A+B only"
        st.markdown(
            f'<div style="border:1px solid var(--color-border-tertiary);'
            f'border-radius:8px;padding:.6rem .8rem;margin-bottom:.3rem">'
            f'<div style="font-size:12px;font-weight:500;margin-bottom:3px">⚡ LDM only</div>'
            f'<div style="font-size:11px;color:var(--color-text-secondary)">{ldm_tip}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button(
            "▶ Run LDM only",
            key="btn_ldm_only",
            type="secondary",
            use_container_width=True,
            disabled=is_running or not has_cdm,
            help=ldm_tip,
        ):
            _trigger(uploaded, "LDM only")

    # Disabled hint for LDM only
    if not has_cdm:
        st.caption("⚠️ LDM only is disabled — run CDM first to generate a stored result.")

    # Running indicator
    if is_running:
        mode = st.session_state.get("pipeline_mode","CDM only")
        st.info(f"⏳ Pipeline running: **{mode}**…")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _has_stored_cdm(brd_hash: str) -> bool:
    try:
        from agent.result_store import load_cdm
        return load_cdm(brd_hash) is not None
    except Exception:
        return False


def _has_stored_ldm(brd_hash: str) -> bool:
    try:
        from agent.result_store import load_ldm
        return load_ldm(brd_hash) is not None
    except Exception:
        return False


def _restore_cached(brd_hash: str):
    """Silently restore CDM and LDM from disk into session state."""
    try:
        from agent.result_store import load_cdm, load_ldm

        if not st.session_state.get("pipeline_result"):
            cdm = load_cdm(brd_hash)
            if cdm:
                st.session_state["pipeline_result"]        = cdm
                st.session_state["cached_pipeline_result"] = cdm

        if not st.session_state.get("ldm_result"):
            ldm = load_ldm(brd_hash)
            if ldm:
                st.session_state["ldm_result"] = ldm
    except Exception:
        pass
