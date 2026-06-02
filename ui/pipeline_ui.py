import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
from agent.pipeline_agent import run_pipeline
from agent.result_store import save_ldm, load_cdm, latest_cdm
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, OLLAMA_URL, CHROMA_PATH

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
]

STEPS = CDM_STEPS  # default — overridden at runtime


def _fmt(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"



def _render_ldm_only(uploaded_file):
    """Run LDM Steps A+B using a stored CDM result — no CDM re-run."""
    st.divider()
    st.subheader("⚡ LDM pipeline (LDM only mode)")

    # Find stored CDM
    cdm_result = st.session_state.get("pipeline_result") or latest_cdm()

    if not cdm_result:
        st.error(
            "No CDM result found. Run **CDM only** or **CDM + LDM** first "
            "to generate and store a CDM result."
        )
        st.session_state["pipeline_running"] = False
        return

    domain_name = cdm_result.get("domain", {}).get("name", "Unknown")
    entity_count = cdm_result.get("stats", {}).get("entity_count", 0)
    brd_hash = cdm_result.get("_brd_hash", "unknown")
    st.info(
        f"Using stored CDM: **{domain_name}** — "
        f"{entity_count} entities · hash `{brd_hash}`"
    )

    # Step cards
    ldm_cols = st.columns(2)
    ldm_steps_ph = []
    for i, (icon, name) in enumerate(LDM_STEPS):
        with ldm_cols[i]:
            ph_h = st.empty(); ph_b = st.empty(); ph_s = st.empty()
            ph_h.markdown(f"**{icon}** {name}")
            ph_b.progress(0)
            ph_s.caption("⬜ waiting")
            ldm_steps_ph.append((ph_h, ph_b, ph_s))

    overall_bar = st.progress(0, text="Starting LDM pipeline…")
    log_ph = st.empty()
    t0 = time.time()

    def ldm_start(name):
        idx = next((i for i,(ic,n) in enumerate(LDM_STEPS) if name.startswith(n[:8])), None)
        if idx is not None:
            ldm_steps_ph[idx][1].progress(0.1)
            ldm_steps_ph[idx][2].caption("⏳ running…")
            overall_bar.progress((idx) / len(LDM_STEPS), text=f"{name}…")

    def ldm_done(name, detail=""):
        idx = next((i for i,(ic,n) in enumerate(LDM_STEPS) if name.startswith(n[:8])), None)
        if idx is not None:
            marker = "⚡" if detail.startswith("⚡") else "✅"
            ldm_steps_ph[idx][1].progress(1.0)
            ldm_steps_ph[idx][2].caption(f"{marker} {detail}")
            overall_bar.progress((idx+1) / len(LDM_STEPS))

    def ldm_log(msg):
        log_ph.caption(f"🔧 {msg}")

    try:
        from agent.ldm_pipeline import run_ldm_pipeline
        brd_text = cdm_result.get("_brd_text","")
        ldm_result = run_ldm_pipeline(
            cdm_result=cdm_result,
            brd_text=brd_text,
            ollama_url=st.session_state.get("ollama_url", OLLAMA_URL),
            model=st.session_state.get("ollama_model","llama3.1:8b"),
            chroma_path=st.session_state.get("chroma_path", CHROMA_PATH),
            temperature=st.session_state.get("temperature", 0.1),
            on_step_start=ldm_start,
            on_step_done=ldm_done,
            on_log=ldm_log,
        )
        log_ph.empty()
        dur = time.time() - t0
        overall_bar.progress(1.0, text=f"✅ LDM complete in {_fmt(dur)}")
        st.success(
            f"🎉 LDM complete in **{_fmt(dur)}** — "
            f"{ldm_result.get('entity_count',0)} tables defined"
        )
        # Save to disk
        try:
            ldm_path = save_ldm(brd_hash, ldm_result)
            st.caption(f"Saved → `ontology/generated/{os.path.basename(ldm_path)}`")
        except Exception as se:
            st.caption(f"Save warning: {se}")
        st.session_state["ldm_result"] = ldm_result
        st.rerun()  # triggers render_output to show LDM tab immediately
    except Exception as e:
        log_ph.empty()
        st.error(f"❌ LDM pipeline failed: {e}")
        import traceback
        st.code(traceback.format_exc(), language="python")
    finally:
        st.session_state["pipeline_running"] = False
        st.session_state.pop("trigger_file", None)


def render_pipeline(uploaded_file):
    if st.session_state.get("use_cache"):
        return
    if not st.session_state.get("pipeline_running"):
        return

    mode = st.session_state.get("pipeline_mode", "CDM only")

    # ── LDM only — skip CDM, reuse stored CDM result ──────────────────────
    if mode == "LDM only":
        _render_ldm_only(uploaded_file)
        return

    st.divider()
    st.subheader("⚡ Pipeline")

    # ── Step cards (one column per step) ────────────────────────────────────
    cols = st.columns(len(STEPS))
    ph_name   = []   # step name placeholder
    ph_bar    = []   # individual progress bar placeholder
    ph_status = []   # status / duration line placeholder

    for i, (icon, name) in enumerate(STEPS):
        with cols[i]:
            ph_name.append(st.empty())
            ph_bar.append(st.empty())
            ph_status.append(st.empty())
            ph_name[i].markdown(f"**{icon}** {name}")
            ph_bar[i].progress(0)
            ph_status[i].caption("⬜ waiting")

    # ── Overall bar + log ────────────────────────────────────────────────────
    st.markdown("")
    overall_bar = st.progress(0, text="Starting…")
    log_ph      = st.empty()

    # ── Timing ───────────────────────────────────────────────────────────────
    step_start: dict[int, float] = {}
    step_dur:   dict[int, float] = {}
    pipeline_t0 = time.time()

    # ── Callbacks (called from main thread inside run_pipeline) ───────────────
    def on_start(i: int):
        step_start[i] = time.time()
        icon, name = STEPS[i]
        ph_name[i].markdown(f"**{icon}** {name}")
        ph_bar[i].progress(0.05)
        ph_status[i].caption("⏳ running…")
        overall_bar.progress(
            i / len(STEPS),
            text=f"Step {i+1}/{len(STEPS)}: {name}…"
        )

    def on_done(i: int, detail: str = ""):
        dur = time.time() - step_start.get(i, time.time())
        step_dur[i] = dur
        icon, name = STEPS[i]
        marker = "⚡" if detail.startswith("⚡") else "✅"
        ph_name[i].markdown(f"**{icon}** {name}")
        ph_bar[i].progress(1.0)
        ph_status[i].caption(f"{marker} {detail}  ·  **{_fmt(dur)}**")
        overall_bar.progress(
            (i + 1) / len(STEPS),
            text=f"Step {i+1}/{len(STEPS)} done: {name}"
        )

    def on_log(msg: str):
        log_ph.caption(f"🔧 {msg}")

    # ── Run ───────────────────────────────────────────────────────────────────
    try:
        result = run_pipeline(
            file=uploaded_file,
            ollama_url=st.session_state.get("ollama_url", OLLAMA_URL),
            model=st.session_state.get("ollama_model", "llama3.1:8b"),
            chroma_path=st.session_state.get("chroma_path", CHROMA_PATH),
            temperature=st.session_state.get("temperature", 0.1),
            top_k=st.session_state.get("top_ontology_k", 3),
            neo4j_uri=st.session_state.get("neo4j_uri", "bolt://localhost:7687"),
            neo4j_user=st.session_state.get("neo4j_user", NEO4J_USER),
            neo4j_password=st.session_state.get("neo4j_password", NEO4J_PASSWORD),
            on_step_start=on_start,
            on_step_done=on_done,
            on_log=on_log,
        )

        log_ph.empty()

        # ── LDM pipeline (if mode = CDM + LDM) ───────────────────────────
        ldm_result = None
        if st.session_state.get("pipeline_mode") == "CDM + LDM":
            st.info("Running LDM pipeline (Steps A & B)…")
            from agent.ldm_pipeline import run_ldm_pipeline
            ldm_log_ph = st.empty()

            ldm_steps_ph = []
            ldm_cols = st.columns(2)
            for i, (icon, name) in enumerate(LDM_STEPS):
                with ldm_cols[i]:
                    ph_h = st.empty(); ph_b = st.empty(); ph_s = st.empty()
                    ph_h.markdown(f"**{icon}** {name}")
                    ph_b.progress(0)
                    ph_s.caption("⬜ waiting")
                    ldm_steps_ph.append((ph_h, ph_b, ph_s))

            def ldm_start(name):
                idx = next((i for i,(ic,n) in enumerate(LDM_STEPS) if name.startswith(n[:8])), None)
                if idx is not None:
                    ldm_steps_ph[idx][1].progress(0.1)
                    ldm_steps_ph[idx][2].caption("⏳ running…")

            def ldm_done(name, detail=""):
                idx = next((i for i,(ic,n) in enumerate(LDM_STEPS) if name.startswith(n[:8])), None)
                if idx is not None:
                    marker = "⚡" if detail.startswith("⚡") else "✅"
                    ldm_steps_ph[idx][1].progress(1.0)
                    ldm_steps_ph[idx][2].caption(f"{marker} {detail}")

            def ldm_log(msg):
                ldm_log_ph.caption(f"🔧 {msg}")

            try:
                ldm_result = run_ldm_pipeline(
                    cdm_result=result,
                    brd_text=result.get("_brd_text", ""),
                    ollama_url=st.session_state.get("ollama_url", OLLAMA_URL),
                    model=st.session_state.get("ollama_model", "llama3.1:8b"),
                    chroma_path=st.session_state.get("chroma_path", CHROMA_PATH),
                    temperature=st.session_state.get("temperature", 0.1),
                    on_step_start=ldm_start,
                    on_step_done=ldm_done,
                    on_log=ldm_log,
                )
                ldm_log_ph.empty()
                # Save LDM to disk keyed by BRD hash
                brd_h = result.get("_brd_hash") or st.session_state.get("previous_brd_hash","unknown")
                try:
                    ldm_path = save_ldm(brd_h, ldm_result)
                    st.caption(f"LDM saved → `{os.path.basename(ldm_path)}`")
                except Exception as se:
                    st.caption(f"LDM save warning: {se}")
                st.session_state["ldm_result"] = ldm_result
                st.success(f"🎉 LDM complete — {ldm_result.get('entity_count',0)} tables defined")
            except Exception as ldm_e:
                ldm_log_ph.empty()
                st.error(f"❌ LDM pipeline failed: {ldm_e}")

        total_dur = time.time() - pipeline_t0
        overall_bar.progress(1.0, text=f"✅ Complete in {_fmt(total_dur)}")
        st.success(f"🎉 Pipeline complete in **{_fmt(total_dur)}**")

        # Attach timing to result for the output Pipeline tab
        result["_pipeline_timing"] = {
            "steps": [
                {
                    "idx":      i,
                    "icon":     STEPS[i][0],
                    "name":     STEPS[i][1],
                    "duration": step_dur.get(i, 0),
                }
                for i in range(len(STEPS))
            ],
            "total_duration": total_dur,
        }

        st.session_state["pipeline_result"]        = result
        st.session_state["cached_pipeline_result"] = result

    except Exception as e:
        log_ph.empty()
        overall_bar.progress(0, text="❌ Pipeline failed")
        st.error(f"❌ Pipeline failed: {e}")
        import traceback
        st.code(traceback.format_exc(), language="python")

    finally:
        st.session_state["pipeline_running"] = False
        st.session_state.pop("trigger_file", None)
