"""
Pipeline UI — executes CDM / LDM / PDM pipelines with live progress.

All four modes run in a background thread so the Cancel button is always
responsive. The main thread polls the shared _PipelineRun state every
~500 ms and re-renders progress cards until the thread finishes.

Cancel flow:
  1. User clicks "🛑 Cancel" (or types "cancel" in chat)
  2. _PipelineRun.cancel_event is set
  3. pipeline_agent / ldm_pipeline check the event before each step and
     raise PipelineCancelledError
  4. Thread sets state.cancelled = True, state.done = True
  5. Next poll: _handle_completion() sees cancelled=True, shows warning,
     clears pipeline_running
"""

import sys, os, time, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
import streamlit as st
from dataclasses import dataclass, field
from src.agents.pipeline_agent import PipelineCancelledError
from src.tools.result_store import (
    save_ldm, save_pdm, latest_cdm, latest_ldm,
    save_dmg_cdm, save_dmg_ldm, save_dmg_pdm,
    save_run_log,
)
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, OLLAMA_URL, CHROMA_PATH

# ── Step lists ────────────────────────────────────────────────────────────────

CDM_STEPS = [
    ("📖", "Document parsing"),
    ("🧬", "Ontology building"),
    ("🕸️", "GraphRAG pipeline"),
    ("🔍", "Entity extraction"),
    ("🔗", "Relationship detection"),
    ("🧠", "Ontology enrichment"),
    ("🦉", "OWL/SHACL rules"),
    ("🏗️", "CDM generation"),
]

LDM_STEPS = [
    ("📚", "Step A — Oracle seeder"),
    ("🔀", "Step B — CDM→LDM"),
    ("✅", "Step V — LDM Validation"),
]

PDM_STEPS = [
    ("🔷", "Step P — BigQuery PDM"),
]


def _fmt(s: float) -> str:
    if s < 1:   return f"{s*1000:.0f}ms"
    if s < 60:  return f"{s:.1f}s"
    m, sec = divmod(int(s), 60)
    return f"{m}m {sec}s"


# ── Shared run state (thread-safe) ────────────────────────────────────────────

@dataclass
class _PipelineRun:
    """Accumulates progress from the background thread. Stored in session state."""
    mode:         str                 = ""
    cancel_event: threading.Event    = field(default_factory=threading.Event)
    _lock:        threading.Lock     = field(default_factory=threading.Lock)

    # Step state: name → {status, detail, start_t, end_t}
    step_states:  dict               = field(default_factory=dict)
    last_log:     str                = ""

    # Results (written by thread, read by main after thread finishes)
    done:         bool               = False
    cancelled:    bool               = False
    error:        str                = ""
    error_tb:     str                = ""
    result:       dict | None        = None
    ldm_result:   dict | None        = None
    pdm_result:   dict | None        = None
    t0:           float              = field(default_factory=time.time)

    def step_start(self, name: str):
        with self._lock:
            self.step_states[name] = {
                "status": "running", "detail": "",
                "start_t": time.time(), "end_t": None,
            }

    def step_done(self, name: str, detail: str = ""):
        with self._lock:
            prev = self.step_states.get(name, {})
            self.step_states[name] = {
                "status": "done", "detail": detail,
                "start_t": prev.get("start_t", time.time()),
                "end_t": time.time(),
            }

    def log(self, msg: str):
        with self._lock:
            self.last_log = msg

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "step_states": dict(self.step_states),
                "last_log":    self.last_log,
                "done":        self.done,
                "cancelled":   self.cancelled,
                "error":       self.error,
                "elapsed":     time.time() - self.t0,
            }


# ── Background thread function ────────────────────────────────────────────────

def _pipeline_thread(run: _PipelineRun, **kwargs):
    """Runs in a daemon thread. Writes results into `run`; never touches st.*"""
    mode = run.mode
    try:
        # ── CDM ───────────────────────────────────────────────────────────
        if mode in ("CDM only", "CDM + LDM + PDM"):
            from src.agents.pipeline_agent import run_pipeline

            def on_start(i):
                run.step_start(CDM_STEPS[i][1])

            def on_done(i, detail=""):
                run.step_done(CDM_STEPS[i][1], detail)

            result = run_pipeline(
                file           = kwargs["file"],
                ollama_url     = kwargs["ollama_url"],
                model          = kwargs["model"],
                chroma_path    = kwargs["chroma_path"],
                temperature    = kwargs["temperature"],
                top_k          = kwargs["top_k"],
                neo4j_uri      = kwargs["neo4j_uri"],
                neo4j_user     = kwargs["neo4j_user"],
                neo4j_password = kwargs["neo4j_password"],
                cancel_event   = run.cancel_event,
                on_step_start  = on_start,
                on_step_done   = on_done,
                on_log         = run.log,
            )
            run.result = result

        # ── LDM ───────────────────────────────────────────────────────────
        if mode in ("LDM only", "CDM + LDM + PDM"):
            from src.agents.ldm_pipeline import run_ldm_pipeline

            cdm = run.result if mode == "CDM + LDM + PDM" else kwargs.get("cdm_result")

            def on_ldm_start(name):
                run.step_start(name)

            def on_ldm_done(name, detail=""):
                run.step_done(name, detail)

            ldm_result = run_ldm_pipeline(
                cdm_result    = cdm,
                brd_text      = cdm.get("_brd_text", "") if cdm else "",
                ollama_url    = kwargs["ollama_url"],
                model         = kwargs["model"],
                chroma_path   = kwargs["chroma_path"],
                temperature   = kwargs["temperature"],
                run_validation= True,
                run_pdm       = (mode == "CDM + LDM + PDM"),
                bq_project    = kwargs.get("bq_project", ""),
                bq_dataset    = kwargs.get("bq_dataset", ""),
                cancel_event  = run.cancel_event,
                on_step_start = on_ldm_start,
                on_step_done  = on_ldm_done,
                on_log        = run.log,
            )

            # Extract embedded PDM if full pipeline
            if mode == "CDM + LDM + PDM" and ldm_result.get("_pdm"):
                run.pdm_result = ldm_result.pop("_pdm")

            run.ldm_result = ldm_result

        # ── PDM only ──────────────────────────────────────────────────────
        if mode == "PDM only":
            from src.pipeline.step_pdm_bq import build_pdm_output

            ldm = kwargs.get("ldm_result")
            run.step_start(PDM_STEPS[0][1])
            pdm_result = build_pdm_output(
                ldm_result = ldm,
                project    = kwargs.get("bq_project", "your_gcp_project"),
                dataset    = kwargs.get("bq_dataset", "MERCH_DW"),
                on_log     = run.log,
            )
            run.step_done(PDM_STEPS[0][1],
                          f"{pdm_result['table_count']} tables · "
                          f"{len(pdm_result['audit_cols'])} audit cols")
            run.pdm_result = pdm_result

    except PipelineCancelledError:
        run.cancelled = True
    except Exception as exc:
        import traceback
        run.error    = str(exc)
        run.error_tb = traceback.format_exc()
    finally:
        run.done = True


# ── Progress renderer ─────────────────────────────────────────────────────────

def _steps_for_mode(mode: str) -> list[tuple[str, str]]:
    if mode == "CDM only":
        return CDM_STEPS
    if mode == "LDM only":
        return LDM_STEPS
    if mode == "PDM only":
        return PDM_STEPS
    return CDM_STEPS + LDM_STEPS + PDM_STEPS  # CDM + LDM + PDM


def _render_progress(snap: dict, mode: str):
    steps      = _steps_for_mode(mode)
    step_states = snap["step_states"]
    elapsed    = snap["elapsed"]

    n_done  = sum(1 for _, n in steps if step_states.get(n, {}).get("status") == "done")
    n_total = len(steps)
    pct     = n_done / n_total if n_total else 0

    st.progress(pct, text=f"{n_done}/{n_total} steps · {_fmt(elapsed)} elapsed")

    # Render in rows of 4 cards
    for row_start in range(0, len(steps), 4):
        row = steps[row_start:row_start + 4]
        cols = st.columns(len(row))
        for col, (icon, name) in zip(cols, row):
            with col:
                s      = step_states.get(name, {})
                status = s.get("status", "waiting")
                detail = s.get("detail", "")
                dur    = ""
                if s.get("start_t") and s.get("end_t"):
                    dur = f"  ·  {_fmt(s['end_t'] - s['start_t'])}"

                st.markdown(f"**{icon}** {name}")
                if status == "waiting":
                    st.caption("⬜ waiting")
                elif status == "running":
                    st.caption("⏳ running…")
                elif status == "done":
                    marker = "⚡" if detail.startswith("⚡") else "✅"
                    st.caption(f"{marker} {detail}{dur}")
                else:
                    st.caption(f"❌ {detail[:60]}")

    if snap["last_log"]:
        st.caption(f"🔧 {snap['last_log']}")


# ── Status persistence ────────────────────────────────────────────────────────

def _store_status(mode, total_dur, steps, files, brd_hash,
                  status="Completed", error=""):
    entry = {
        "mode":           mode,
        "status":         status,
        "error":          error,
        "total_duration": total_dur,
        "steps":          steps,
        "files":          files,
        "brd_hash":       brd_hash,
        "timestamp":      time.time(),
    }
    st.session_state["pipeline_status"]      = entry
    st.session_state["show_pipeline_status"] = True
    try:
        save_run_log(entry)
    except Exception:
        pass


def _step_timings(run: _PipelineRun, mode: str) -> list[dict]:
    steps = _steps_for_mode(mode)
    rows  = []
    for icon, name in steps:
        s = run.step_states.get(name, {})
        dur = 0.0
        if s.get("start_t") and s.get("end_t"):
            dur = s["end_t"] - s["start_t"]
        rows.append({"icon": icon, "name": name,
                     "duration": dur, "detail": s.get("detail", "")})
    return rows


# ── Completion handler ────────────────────────────────────────────────────────

def _handle_completion(run: _PipelineRun):
    mode     = run.mode
    total    = time.time() - run.t0
    brd_hash = (run.result or {}).get("_brd_hash") or \
               st.session_state.get("previous_brd_hash", "unknown")
    dmg_files: dict = {}

    if run.cancelled:
        st.warning("🚫 Pipeline cancelled — partial results may be available.")
        _store_status(mode, total, _step_timings(run, mode), {},
                      brd_hash, status="Cancelled")

    elif run.error:
        st.error(f"❌ Pipeline failed: {run.error}")
        with st.expander("Traceback"):
            st.code(run.error_tb, language="python")
        _store_status(mode, total, _step_timings(run, mode), {},
                      brd_hash, status="Failed", error=run.error)

    else:
        # ── Persist CDM ───────────────────────────────────────────────────
        if run.result:
            st.session_state["pipeline_result"]        = run.result
            st.session_state["cached_pipeline_result"] = run.result
            try:
                from src.pipeline.cdm_builder import result_to_mermaid
                dmg_files.update(save_dmg_cdm(
                    brd_hash, run.result, result_to_mermaid(run.result)
                ))
            except Exception as e:
                st.warning(f"⚠️ CDM file save failed: {e}")

        # ── Persist LDM ───────────────────────────────────────────────────
        if run.ldm_result:
            save_ldm(brd_hash, run.ldm_result)
            st.session_state["ldm_result"] = run.ldm_result
            try:
                from src.pipeline.step_ldm_ddl import generate_ddl
                dmg_files.update(save_dmg_ldm(
                    brd_hash,
                    generate_ddl(run.ldm_result, "ansi"),
                    generate_ddl(run.ldm_result, "snowflake"),
                ))
            except Exception as e:
                st.warning(f"⚠️ LDM file save failed: {e}")

        # ── Persist PDM ───────────────────────────────────────────────────
        if run.pdm_result:
            save_pdm(brd_hash, run.pdm_result)
            st.session_state["pdm_result"] = run.pdm_result
            ddl_bq  = run.pdm_result.get("ddl_bq", "")
            dataset = run.pdm_result.get("dataset", "MERCH_DW")
            if ddl_bq:
                try:
                    dmg_files.update(save_dmg_pdm(brd_hash, ddl_bq, dataset))
                except Exception as e:
                    st.warning(f"⚠️ PDM file save failed: {e}")

        _store_status(mode, total, _step_timings(run, mode), dmg_files, brd_hash)
        total_dur = time.time() - run.t0
        st.success(f"✅ {mode} complete in {_fmt(total_dur)}")

    # Clean up
    st.session_state["pipeline_running"] = False
    st.session_state.pop("_pipeline_run",    None)
    st.session_state.pop("_pipeline_thread", None)
    st.session_state.pop("trigger_file",     None)
    st.rerun()


# ── Main entry point ──────────────────────────────────────────────────────────

def render_pipeline(uploaded_file):
    if st.session_state.get("use_cache"):
        return
    if not st.session_state.get("pipeline_running"):
        return

    mode = st.session_state.get("pipeline_mode", "CDM only")

    # ── Start thread on first call ─────────────────────────────────────────
    if "_pipeline_run" not in st.session_state:
        run = _PipelineRun(mode=mode)
        st.session_state["_pipeline_run"] = run

        # Gather kwargs from session state
        base_kwargs = dict(
            ollama_url     = st.session_state.get("ollama_url", OLLAMA_URL),
            model          = st.session_state.get("ollama_model", "llama3.1:8b"),
            chroma_path    = st.session_state.get("chroma_path", CHROMA_PATH),
            temperature    = st.session_state.get("temperature", 0.1),
            top_k          = st.session_state.get("top_ontology_k", 3),
            neo4j_uri      = st.session_state.get("neo4j_uri", NEO4J_URI),
            neo4j_user     = st.session_state.get("neo4j_user", NEO4J_USER),
            neo4j_password = st.session_state.get("neo4j_password", NEO4J_PASSWORD),
            bq_project     = st.session_state.get("bq_project", ""),
            bq_dataset     = st.session_state.get("bq_dataset", ""),
        )

        if mode in ("CDM only", "CDM + LDM + PDM"):
            base_kwargs["file"] = uploaded_file
        elif mode == "LDM only":
            cdm = st.session_state.get("pipeline_result") or latest_cdm()
            if not cdm:
                st.error("No CDM found. Run CDM first.")
                st.session_state["pipeline_running"] = False
                return
            base_kwargs["cdm_result"] = cdm
        elif mode == "PDM only":
            ldm = st.session_state.get("ldm_result") or latest_ldm()
            if not ldm:
                st.error("No LDM found. Run LDM first.")
                st.session_state["pipeline_running"] = False
                return
            base_kwargs["ldm_result"] = ldm

        t = threading.Thread(
            target=_pipeline_thread, kwargs={"run": run, **base_kwargs}, daemon=True
        )
        st.session_state["_pipeline_thread"] = t
        t.start()

    run: _PipelineRun        = st.session_state["_pipeline_run"]
    thread: threading.Thread = st.session_state["_pipeline_thread"]

    # ── Header + Cancel button ─────────────────────────────────────────────
    st.divider()
    col_title, col_cancel = st.columns([5, 1])
    with col_title:
        st.subheader(f"⚡ {mode} Pipeline — running…")
    with col_cancel:
        if st.button("🛑 Cancel", use_container_width=True, type="secondary",
                     key="btn_cancel_pipeline"):
            run.cancel_event.set()
            st.session_state["_pipeline_cancelled_by_user"] = True
            st.toast("Cancel requested — waiting for current step to finish…")

    # ── Render progress ────────────────────────────────────────────────────
    snap = run.snapshot()
    _render_progress(snap, mode)

    # ── Check completion ───────────────────────────────────────────────────
    if snap["done"] or not thread.is_alive():
        _handle_completion(run)
        return

    # ── Poll ───────────────────────────────────────────────────────────────
    time.sleep(0.5)
    st.rerun()
