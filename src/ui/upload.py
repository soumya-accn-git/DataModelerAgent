"""
Upload panel — BRD file upload with four pipeline run options.

Four run modes:
  ▶ CDM only        — full 8-step CDM pipeline (always enabled)
  ▶ LDM only        — Steps A+B+V from stored CDM (requires CDM)
  ▶ PDM only        — BigQuery DDL from stored LDM (requires LDM)
  ▶ CDM + LDM + PDM — full end-to-end pipeline (always enabled)

After completion: Status button toggles a timing + file-path panel.
No "Pipeline running…" banner — the pipeline_ui handles live progress.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
import streamlit as st
import hashlib
import time as _time


def _file_hash(uploaded_file) -> str:
    return hashlib.sha256(uploaded_file.getvalue()).hexdigest()[:16]


def _trigger(uploaded, mode: str):
    st.session_state["pipeline_mode"]    = mode
    st.session_state["pipeline_running"] = True
    st.session_state["trigger_file"]     = uploaded
    st.session_state["use_cache"]        = False
    # For LDM-only / PDM-only the upstream result (CDM / LDM) is the *input*
    # to the pipeline — preserve it so the thread can use it without needing
    # to go through the _restore_cached round-trip.  For CDM runs clear the
    # stale CDM so the new result is always fresh.
    if mode not in ("LDM only", "PDM only"):
        st.session_state["pipeline_result"] = None
    if mode not in ("PDM only",):
        st.session_state["ldm_result"] = None
    st.session_state["previous_brd_hash"] = _file_hash(uploaded)
    st.rerun()


# ── Status detail panel ────────────────────────────────────────────────────────

def _render_status_detail(status: dict):
    """Render the step timing table + DMG file paths inside an expander."""
    steps  = status.get("steps", [])
    files  = status.get("files", {})
    total  = status.get("total_duration", 0)
    state  = status.get("status", "Completed")
    error  = status.get("error", "")

    # Overall status banner
    if state == "Failed":
        st.error(f"**Status:** ❌ Failed" + (f" — {error}" if error else ""))
    elif state == "Completed with warnings":
        st.warning(f"**Status:** ⚠️ Completed with warnings" + (f" — {error}" if error else ""))
    else:
        st.success("**Status:** ✅ Completed")

    if steps:
        rows = []
        for s in steps:
            d = s.get("duration", 0)
            rows.append({
                "": s.get("icon", ""),
                "Step": s.get("name", ""),
                "Duration": _fmt(d),
                "Detail": s.get("detail", ""),
            })
        import pandas as pd
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            use_container_width=True,
            column_config={
                "":        st.column_config.TextColumn(width="small"),
                "Step":    st.column_config.TextColumn(width="medium"),
                "Duration":st.column_config.TextColumn(width="small"),
                "Detail":  st.column_config.TextColumn(width="large"),
            },
        )
        st.caption(f"**Total:** {_fmt(total)}")

    if files:
        st.markdown("**Generated files**")
        dmg_base = os.path.normpath(
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                         "Data Models Generated")
        )
        for label, path in files.items():
            rel = os.path.relpath(path, dmg_base) if os.path.isabs(path) else path
            st.code(f"Data Models Generated/{rel}", language="")


def _render_status_section():
    """Show the Status toggle button + expandable panel below the run buttons."""
    status = st.session_state.get("pipeline_status")
    if not status:
        return

    mode  = status.get("mode", "")
    total = status.get("total_duration", 0)
    state = status.get("status", "Completed")
    show  = st.session_state.get("show_pipeline_status", False)

    icon  = {"Failed": "❌", "Completed with warnings": "⚠️"}.get(state, "✅")
    label = f"{'📊 Hide Status' if show else '📊 Status'}  ·  {icon} {mode} — {_fmt(total)}"
    if st.button(label, key="btn_pipeline_status", use_container_width=True):
        st.session_state["show_pipeline_status"] = not show
        st.rerun()

    if st.session_state.get("show_pipeline_status"):
        with st.container():
            _render_status_detail(status)


def _fmt(s: float) -> str:
    if s < 1:
        return f"{s*1000:.0f}ms"
    if s < 60:
        return f"{s:.1f}s"
    m, sec = divmod(int(s), 60)
    return f"{m}m {sec}s"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _has_stored_cdm(brd_hash: str) -> bool:
    try:
        from src.tools.result_store import load_cdm
        return load_cdm(brd_hash) is not None
    except Exception:
        return False


def _has_stored_ldm(brd_hash: str) -> bool:
    try:
        from src.tools.result_store import load_ldm
        return load_ldm(brd_hash) is not None
    except Exception:
        return False


def _has_stored_pdm(brd_hash: str) -> bool:
    try:
        from src.tools.result_store import load_pdm
        return load_pdm(brd_hash) is not None
    except Exception:
        return False


def _restore_cached(brd_hash: str):
    try:
        from src.tools.result_store import load_cdm, load_ldm, load_pdm
        if not st.session_state.get("pipeline_result"):
            cdm = load_cdm(brd_hash)
            if cdm:
                st.session_state["pipeline_result"]        = cdm
                st.session_state["cached_pipeline_result"] = cdm
        if not st.session_state.get("ldm_result"):
            ldm = load_ldm(brd_hash)
            if ldm:
                st.session_state["ldm_result"] = ldm
        if not st.session_state.get("pdm_result"):
            pdm = load_pdm(brd_hash)
            if pdm:
                st.session_state["pdm_result"] = pdm
    except Exception:
        pass


# ── Run history panel ─────────────────────────────────────────────────────────

def _render_run_history():
    try:
        from src.tools.result_store import load_run_log
        runs = load_run_log()
    except Exception:
        return
    if not runs:
        return

    st.divider()
    st.markdown("**📋 Run History** *(last 2 runs)*")
    for i, run in enumerate(reversed(runs)):
        ts    = _time.strftime("%d %b %H:%M", _time.localtime(run.get("timestamp", 0)))
        mode  = run.get("mode", "?")
        state = run.get("status", "Completed")
        total = run.get("total_duration", 0)
        icon  = {"Failed": "❌", "Completed with warnings": "⚠️"}.get(state, "✅")
        label = f"Run {i + 1}:  {icon} {mode}  ·  {ts}  ·  {_fmt(total)}"
        with st.expander(label, expanded=(i == 0)):
            _render_status_detail(run)


# ── Main upload panel ──────────────────────────────────────────────────────────

def render_upload():
    st.subheader("📄 Upload BRD")

    uploaded = st.file_uploader(
        "Drop your Business Requirements Document (.docx)",
        type=["docx"],
        label_visibility="visible",
    )

    if not uploaded:
        st.session_state.pop("current_uploaded_file", None)
        return

    st.session_state["current_uploaded_file"] = uploaded
    file_hash  = _file_hash(uploaded)
    prev_hash  = st.session_state.get("previous_brd_hash")
    same_brd   = file_hash == prev_hash
    has_cdm    = st.session_state.get("pipeline_result") is not None or _has_stored_cdm(file_hash)
    has_ldm    = st.session_state.get("ldm_result") is not None or _has_stored_ldm(file_hash)
    has_pdm    = st.session_state.get("pdm_result") is not None or _has_stored_pdm(file_hash)
    is_running = st.session_state.get("pipeline_running", False)

    # File info row
    c_file, c_clear = st.columns([5, 1])
    with c_file:
        cdm_badge = "CDM ✅" if has_cdm else "CDM —"
        ldm_badge = "LDM ✅" if has_ldm else "LDM —"
        pdm_badge = "PDM ✅" if has_pdm else "PDM —"
        st.success(
            f"**{uploaded.name}** · {uploaded.size/1024:.1f} KB · "
            f"`{file_hash}` · {cdm_badge} · {ldm_badge} · {pdm_badge}"
        )
    with c_clear:
        if st.button("✖ Clear", use_container_width=True):
            for k in ["pipeline_running", "pipeline_result", "ldm_result", "pdm_result",
                      "pipeline_status", "show_pipeline_status",
                      "use_cache", "trigger_file", "cached_pipeline_result"]:
                st.session_state.pop(k, None)
            st.rerun()

    # Restore cached results for same BRD
    if same_brd and has_cdm and not st.session_state.get("pipeline_result"):
        _restore_cached(file_hash)

    # Run buttons (4 modes)
    st.markdown("**Run pipeline**")
    b1, b2, b3, b4 = st.columns(4)

    with b1:
        st.markdown(_card_html(
            "📊 CDM only",
            "Full 8-step pipeline · Conceptual Data Model",
        ), unsafe_allow_html=True)
        if st.button(
            "▶ Run CDM",
            key="btn_cdm_only",
            type="primary",
            use_container_width=True,
            disabled=is_running,
        ):
            _trigger(uploaded, "CDM only")

    with b2:
        ldm_tip = "Requires a stored CDM result" if not has_cdm else "Uses stored CDM — Steps A+B+V"
        st.markdown(_card_html(
            "⚡ LDM only",
            ldm_tip,
            disabled=not has_cdm,
        ), unsafe_allow_html=True)
        if st.button(
            "▶ Run LDM only",
            key="btn_ldm_only",
            type="secondary",
            use_container_width=True,
            disabled=is_running or not has_cdm,
            help=ldm_tip,
        ):
            _trigger(uploaded, "LDM only")

    with b3:
        pdm_tip = "Requires a stored LDM result" if not has_ldm else "BigQuery DDL from stored LDM"
        st.markdown(_card_html(
            "🔷 PDM only",
            pdm_tip,
            disabled=not has_ldm,
        ), unsafe_allow_html=True)
        if st.button(
            "▶ Run PDM only",
            key="btn_pdm_only",
            type="secondary",
            use_container_width=True,
            disabled=is_running or not has_ldm,
            help=pdm_tip,
        ):
            _trigger(uploaded, "PDM only")

    with b4:
        st.markdown(_card_html(
            "🏗️ CDM + LDM + PDM",
            "Full pipeline · BigQuery DDL with audit &amp; partitioning",
        ), unsafe_allow_html=True)
        if st.button(
            "▶ Run Full Pipeline",
            key="btn_cdm_ldm_pdm",
            type="primary",
            use_container_width=True,
            disabled=is_running,
        ):
            _trigger(uploaded, "CDM + LDM + PDM")

    # Disabled hints
    if not has_cdm:
        st.caption("⚠️ LDM only is disabled — run CDM first.")
    if not has_ldm:
        st.caption("⚠️ PDM only is disabled — run LDM first.")

    # Status panel (shown after completion)
    if not is_running:
        _render_status_section()
        _render_run_history()


def _card_html(title: str, desc: str, disabled: bool = False) -> str:
    opacity = "0.5" if disabled else "1"
    return (
        f'<div style="border:1px solid var(--color-border-tertiary);border-radius:8px;'
        f'padding:.6rem .8rem;margin-bottom:.3rem;opacity:{opacity}">'
        f'<div style="font-size:12px;font-weight:500;margin-bottom:3px">{title}</div>'
        f'<div style="font-size:11px;color:var(--color-text-secondary)">{desc}</div>'
        f'</div>'
    )
