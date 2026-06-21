"""
Natural language chat interface for DataModelerAgent.

Supported intents (regex-matched, case-insensitive):
  Pipeline triggers : create/run CDM, LDM, PDM, full pipeline
  Show results      : show CDM entities, LDM tables, LDM DDL, PDM DDL
  Info              : show files, show status, help
  LLM fallback      : any unmatched message → Ollama chat call
"""

import re, hashlib, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import streamlit as st

# ── Intent patterns ────────────────────────────────────────────────────────────

_INTENTS = [
    ("run_cdm", re.compile(
        r"\b(run|create|build|generate|start|make)\b.{0,30}\bcdm\b"
        r"|\bcdm\s+(only|pipeline|run|please|now)\b"
        r"|\bconceptual\s+(data\s+)?model\b",
        re.IGNORECASE,
    )),
    ("run_ldm", re.compile(
        r"\b(run|create|build|generate|start|make)\b.{0,30}\bldm\b"
        r"|\bldm\s+(only|pipeline|run|please|now)\b"
        r"|\blogical\s+(data\s+)?model\b",
        re.IGNORECASE,
    )),
    ("run_pdm", re.compile(
        r"\b(run|create|build|generate|start|make)\b.{0,30}\bpdm\b"
        r"|\bpdm\s+(only|pipeline|run|please|now)\b"
        r"|\bphysical\s+(data\s+)?model\b"
        r"|\bbigquery\s+(ddl|pipeline|schema)\b",
        re.IGNORECASE,
    )),
    ("run_full", re.compile(
        r"\b(full|complete|entire|end.to.end|all)\b.{0,20}\bpipeline\b"
        r"|\bcdm\s*\+\s*ldm"
        r"|\brun\s+(all|everything)\b"
        r"|\bcomplete\s+pipeline\b",
        re.IGNORECASE,
    )),
    ("show_ldm_ddl", re.compile(
        r"\b(show|display|view|get|print)\b.{0,25}\b(ldm\s+ddl|ddl)\b"
        r"|\bsql\s+(ddl|script|output)\b"
        r"|\bddl\s+(for|of)\s+ldm\b",
        re.IGNORECASE,
    )),
    ("show_cdm", re.compile(
        r"\b(show|display|view|see|get|list)\b.{0,20}\bcdm\b"
        r"|\bcdm\s+(result|output|entities|diagram)\b"
        r"|\b(list|show)\s+(the\s+)?entit(y|ies)\b",
        re.IGNORECASE,
    )),
    ("show_ldm", re.compile(
        r"\b(show|display|view|see|get|list)\b.{0,20}\bldm\b"
        r"|\bldm\s+(result|tables|output|summary)\b",
        re.IGNORECASE,
    )),
    ("show_pdm", re.compile(
        r"\b(show|display|view|see|get)\b.{0,20}\bpdm\b"
        r"|\bpdm\s+(result|output|ddl|bigquery)\b"
        r"|\bbigquery\s+(ddl|output|script)\b",
        re.IGNORECASE,
    )),
    ("show_files", re.compile(
        r"\b(show|list|where\s+are)\b.{0,20}\bfiles\b"
        r"|\b(generated|output)\s+files\b"
        r"|\bwhat\s+(was|were|has\s+been)\s+(saved|generated|created)\b",
        re.IGNORECASE,
    )),
    ("show_status", re.compile(
        r"\b(show|what\s+is|check|get)\b.{0,20}\bstatus\b"
        r"|\b(pipeline|run)\s+status\b"
        r"|\blast\s+run\b"
        r"|\bhow\s+did\s+(the\s+)?(pipeline|it)\s+(go|run|do)\b",
        re.IGNORECASE,
    )),
    ("cancel_pipeline", re.compile(
        r"\b(cancel|stop|abort|halt|kill)\b.{0,25}\b(pipeline|run|job|task|it)\b"
        r"|\b(cancel|stop|abort)\s+now\b"
        r"|\bstop\s+running\b",
        re.IGNORECASE,
    )),
    ("help", re.compile(
        r"^\s*(help|\?|commands?|usage)\s*$"
        r"|\bwhat\s+can\s+you\s+do\b"
        r"|\bwhat\s+commands\b"
        r"|\bhow\s+do\s+i\s+use\b",
        re.IGNORECASE,
    )),
]

_HELP_TEXT = """\
**DataModelerAgent Chat** — type a command or ask a question.

**Run pipelines** *(BRD file must be uploaded above)*
- `create CDM` — 8-step Conceptual Data Model pipeline
- `run LDM` — promote CDM → Logical Data Model *(requires CDM)*
- `run PDM` — generate BigQuery DDL *(requires LDM)*
- `full pipeline` — CDM + LDM + PDM end-to-end

**View results** *(inline in chat)*
- `show CDM` — entity table from the last CDM run
- `show LDM` — table summary from the last LDM run
- `show LDM DDL` — ANSI SQL DDL preview
- `show PDM` — BigQuery DDL preview
- `show files` — all stored result hashes and file paths

**Info**
- `show status` — last pipeline run details and timings
- `cancel pipeline` — request cancellation of the running pipeline
- `help` — this message

**Anything else** is answered by the Ollama LLM using your current model results as context.
"""


# ── Utilities ─────────────────────────────────────────────────────────────────

def _file_hash(uploaded_file) -> str:
    return hashlib.sha256(uploaded_file.getvalue()).hexdigest()[:16]


def _fmt(s: float) -> str:
    if s < 1:
        return f"{s*1000:.0f}ms"
    if s < 60:
        return f"{s:.1f}s"
    m, sec = divmod(int(s), 60)
    return f"{m}m {sec}s"


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


# ── Pipeline trigger ───────────────────────────────────────────────────────────

def _check_prereqs(mode: str) -> tuple[bool, str]:
    uploaded = st.session_state.get("current_uploaded_file")
    if uploaded is None:
        return False, "No BRD file uploaded. Please upload a `.docx` file first using the upload widget above."

    if mode in ("CDM only", "CDM + LDM + PDM"):
        return True, ""

    brd_hash = _file_hash(uploaded)
    if mode == "LDM only":
        if not (st.session_state.get("pipeline_result") or _has_stored_cdm(brd_hash)):
            return False, "LDM requires a CDM result. Run **CDM only** or **full pipeline** first."
        return True, ""

    if mode == "PDM only":
        if not (st.session_state.get("ldm_result") or _has_stored_ldm(brd_hash)):
            return False, "PDM requires an LDM result. Run **LDM only** or **full pipeline** first."
        return True, ""

    return True, ""


def _trigger_pipeline(mode: str) -> str:
    uploaded = st.session_state["current_uploaded_file"]
    st.session_state["pipeline_mode"]           = mode
    st.session_state["pipeline_running"]        = True
    st.session_state["trigger_file"]            = uploaded
    st.session_state["use_cache"]               = False
    st.session_state["pipeline_result"]         = None
    st.session_state["previous_brd_hash"]       = _file_hash(uploaded)
    st.session_state["chat_triggered_pipeline"] = True
    st.session_state["chat_pipeline_mode"]      = mode
    labels = {
        "CDM only":        "CDM pipeline (8 steps)",
        "LDM only":        "LDM pipeline (Steps A + B + V)",
        "PDM only":        "PDM pipeline (BigQuery DDL)",
        "CDM + LDM + PDM": "full CDM + LDM + PDM pipeline",
    }
    return f"🚀 Starting the **{labels.get(mode, mode)}**… *(progress shown below)*"


# ── Completion summary ─────────────────────────────────────────────────────────

def _build_completion_summary(mode: str) -> tuple[str, callable | None]:
    status = st.session_state.get("pipeline_status", {})
    state  = status.get("status", "Completed")
    total  = status.get("total_duration", 0)
    files  = status.get("files", {})
    error  = status.get("error", "")

    icon  = {"Failed": "❌", "Completed with warnings": "⚠️"}.get(state, "✅")
    lines = [f"{icon} **{mode}** finished in **{_fmt(total)}**"]

    cdm = st.session_state.get("pipeline_result")
    if cdm:
        ents   = cdm.get("entities", [])
        n_ent  = cdm.get("stats", {}).get("entity_count", len(ents))
        n_rel  = cdm.get("stats", {}).get("relationship_count", len(cdm.get("relationships", [])))
        domain = cdm.get("domain", {}).get("name", "")
        lines.append(
            f"**CDM** — {n_ent} entities · {n_rel} relationships"
            + (f" · domain: *{domain}*" if domain else "")
        )

    ldm = st.session_state.get("ldm_result")
    if ldm:
        dims    = len(ldm.get("dimension_tables", []))
        facts   = len(ldm.get("fact_tables", []))
        bridges = len(ldm.get("bridge_tables", []))
        refs    = len(ldm.get("reference_tables", []))
        lines.append(f"**LDM** — {dims} dims · {facts} facts · {bridges} bridges · {refs} refs")

    pdm = st.session_state.get("pdm_result")
    if pdm:
        n_tbl   = pdm.get("table_count", 0)
        dataset = pdm.get("dataset", "")
        lines.append(f"**PDM** — {n_tbl} BigQuery tables" + (f" → `{dataset}`" if dataset else ""))

    if files:
        lines.append("**Generated files:**")
        for label, path in files.items():
            lines.append(f"- `{label}`: `{path}`")

    if error:
        lines.append(f"⚠️ {error[:200]}")

    lines.append("Type `show CDM`, `show LDM`, or `show PDM` to view results.")
    return "\n\n".join(lines), None


# ── Inline widgets (stored as callables in message dict) ──────────────────────

def _widget_show_cdm():
    import pandas as pd
    cdm = st.session_state.get("pipeline_result")
    if not cdm:
        st.warning("No CDM in session. Run **create CDM** first.")
        return
    entities = cdm.get("entities", [])
    if not entities:
        st.info("CDM has no entities.")
        return
    rows = [
        {
            "Entity":      e.get("name", ""),
            "Type":        e.get("type", ""),
            "Description": (e.get("description") or "")[:90],
        }
        for e in entities
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    brd_hash = cdm.get("_brd_hash", "")
    if brd_hash:
        from src.tools.result_store import get_dmg_dir
        cdm_dir = get_dmg_dir("CDM")
        files = [f for f in os.listdir(cdm_dir)] if os.path.isdir(cdm_dir) else []
        if files:
            st.caption("Files: " + "  ·  ".join(f"`Data Models Generated/CDM/{f}`" for f in files))


def _widget_show_ldm():
    import pandas as pd
    ldm = st.session_state.get("ldm_result")
    if not ldm:
        st.warning("No LDM in session. Run **run LDM** first.")
        return
    all_tables = (
        ldm.get("dimension_tables", []) + ldm.get("fact_tables", []) +
        ldm.get("bridge_tables", []) + ldm.get("reference_tables", [])
    )
    if not all_tables:
        st.info("LDM has no tables.")
        return
    rows = [
        {
            "Table":   t.get("table_name", ""),
            "Columns": len(t.get("columns", [])),
            "SCD":     f"SCD{t['scd_type']}" if t.get("scd_type") else "—",
            "Grain":   (t.get("grain") or "")[:60],
        }
        for t in all_tables
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _widget_show_ldm_ddl():
    ldm = st.session_state.get("ldm_result")
    if not ldm:
        st.warning("No LDM in session. Run **run LDM** first.")
        return
    try:
        from src.pipeline.step_ldm_ddl import generate_ddl
        ddl = generate_ddl(ldm, "ansi")
        preview = ddl[:4000] + ("\n\n-- ... (truncated — see Data Models Generated/LDM/ for full file)" if len(ddl) > 4000 else "")
        st.code(preview, language="sql")
    except Exception as e:
        st.error(f"DDL generation failed: {e}")


def _widget_show_pdm():
    pdm = st.session_state.get("pdm_result")
    if not pdm:
        st.warning("No PDM in session. Run **run PDM** first.")
        return
    ddl = pdm.get("ddl_bq", "")
    if not ddl:
        st.info("PDM result has no DDL.")
        return
    preview = ddl[:4000] + ("\n\n-- ... (truncated — see Data Models Generated/PDM/ for full file)" if len(ddl) > 4000 else "")
    st.code(preview, language="sql")


def _widget_show_files():
    import pandas as pd, time as _time
    from src.tools.result_store import list_stored
    stored = list_stored()
    if not stored:
        st.info("No stored results found.")
        return
    rows = [
        {
            "Hash":     r["brd_hash"],
            "CDM":      "✅" if r["has_cdm"] else "—",
            "LDM":      "✅" if r["has_ldm"] else "—",
            "PDM":      "✅" if r.get("has_pdm") else "—",
            "Modified": _time.strftime("%d %b %H:%M", _time.localtime(r["modified"])),
        }
        for r in stored[:10]
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Also list Data Models Generated/ folder
    from src.tools.result_store import get_dmg_dir
    dmg = get_dmg_dir()
    if os.path.isdir(dmg):
        all_files = []
        for sub in ("CDM", "LDM", "PDM"):
            d = os.path.join(dmg, sub)
            if os.path.isdir(d):
                for f in os.listdir(d):
                    all_files.append(f"Data Models Generated/{sub}/{f}")
        if all_files:
            st.code("\n".join(all_files), language="")


def _widget_show_status():
    import pandas as pd
    status = st.session_state.get("pipeline_status")
    if not status:
        if st.session_state.get("pipeline_running"):
            st.info("Pipeline is currently running…")
        else:
            st.info("No pipeline run in this session. Check **Run History** below the upload panel.")
        return
    state  = status.get("status", "Completed")
    mode   = status.get("mode", "")
    total  = status.get("total_duration", 0)
    error  = status.get("error", "")
    steps  = status.get("steps", [])
    files  = status.get("files", {})
    icon   = {"Failed": "❌", "Completed with warnings": "⚠️"}.get(state, "✅")
    st.markdown(f"{icon} **{mode}** · {state} · {_fmt(total)}")
    if error:
        st.caption(f"Error: {error[:200]}")
    if steps:
        rows = [
            {"Step": s.get("name", ""), "Duration": _fmt(s.get("duration", 0)), "Detail": s.get("detail", "")}
            for s in steps
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if files:
        for label, path in files.items():
            st.caption(f"`{label}` → `{path}`")


# ── LLM fallback ──────────────────────────────────────────────────────────────

def _llm_fallback(user_text: str) -> str:
    ollama_url = st.session_state.get("ollama_url", "http://localhost:11434")
    model      = st.session_state.get("ollama_model", "llama3.1:8b")
    temp       = st.session_state.get("temperature", 0.1)

    ctx_lines = []
    cdm = st.session_state.get("pipeline_result")
    if cdm:
        n_ent  = cdm.get("stats", {}).get("entity_count", len(cdm.get("entities", [])))
        domain = cdm.get("domain", {}).get("name", "")
        ctx_lines.append(f"- CDM available: {n_ent} entities, domain: {domain}")
    ldm = st.session_state.get("ldm_result")
    if ldm:
        dims  = len(ldm.get("dimension_tables", []))
        facts = len(ldm.get("fact_tables", []))
        ctx_lines.append(f"- LDM available: {dims} dimension tables, {facts} fact tables")
    pdm = st.session_state.get("pdm_result")
    if pdm:
        ctx_lines.append(f"- PDM available: {pdm.get('table_count', 0)} BigQuery tables")

    context = "\n".join(ctx_lines) if ctx_lines else "No pipeline results in session yet."

    system_prompt = (
        "You are DataModelerAgent, an AI assistant specialising in retail data modelling. "
        "You help users understand CDM (Conceptual Data Model), LDM (Logical Data Model), "
        "and PDM (Physical/BigQuery DDL) outputs produced from Business Requirements Documents. "
        "You also explain dimensional modelling, star schema design, ARTS ODM, Oracle Retail, "
        "and BigQuery best practices. Be concise — 2-4 sentences unless a longer answer is clearly needed.\n\n"
        "Current session:\n" + context + "\n\n"
        "If the user asks to run a pipeline or view results, remind them of the chat commands "
        "(type 'help'). Never fabricate entity names or table names — only reference what is "
        "described in the session context above."
    )

    try:
        from src.tools.ollama_client import chat
        return chat(
            base_url    = ollama_url,
            model       = model,
            messages    = [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_text},
            ],
            temperature = temp,
            num_ctx     = 8192,
            num_predict = 512,
            seed        = -1,
        ).strip()
    except Exception as exc:
        return (
            f"I couldn't reach the Ollama model (`{model}` at `{ollama_url}`). "
            f"Error: {exc}\n\nType `help` to see what commands are available."
        )


# ── Intent dispatcher ─────────────────────────────────────────────────────────

def _dispatch(text: str) -> tuple[str, callable | None, bool]:
    """
    Returns (response_text, widget_callable_or_None, should_rerun).
    should_rerun=True only for pipeline triggers (they call st.rerun() anyway).
    """
    for intent_name, pattern in _INTENTS:
        if not pattern.search(text):
            continue

        if intent_name == "run_cdm":
            ok, err = _check_prereqs("CDM only")
            if not ok:
                return err, None, False
            return _trigger_pipeline("CDM only"), None, True

        if intent_name == "run_ldm":
            ok, err = _check_prereqs("LDM only")
            if not ok:
                return err, None, False
            return _trigger_pipeline("LDM only"), None, True

        if intent_name == "run_pdm":
            ok, err = _check_prereqs("PDM only")
            if not ok:
                return err, None, False
            return _trigger_pipeline("PDM only"), None, True

        if intent_name == "run_full":
            ok, err = _check_prereqs("CDM + LDM + PDM")
            if not ok:
                return err, None, False
            return _trigger_pipeline("CDM + LDM + PDM"), None, True

        if intent_name == "show_cdm":
            if not st.session_state.get("pipeline_result"):
                return "No CDM in session yet. Type `create CDM` to run the pipeline.", None, False
            return "Here are the CDM entities:", _widget_show_cdm, False

        if intent_name == "show_ldm":
            if not st.session_state.get("ldm_result"):
                return "No LDM in session yet. Type `run LDM` to run the pipeline.", None, False
            return "Here are the LDM tables:", _widget_show_ldm, False

        if intent_name == "show_ldm_ddl":
            if not st.session_state.get("ldm_result"):
                return "No LDM in session yet. Type `run LDM` to run the pipeline.", None, False
            return "Here is the LDM DDL (ANSI SQL):", _widget_show_ldm_ddl, False

        if intent_name == "show_pdm":
            if not st.session_state.get("pdm_result"):
                return "No PDM in session yet. Type `run PDM` to run the pipeline.", None, False
            return "Here is the BigQuery PDM DDL:", _widget_show_pdm, False

        if intent_name == "show_files":
            return "Here are all stored results and generated files:", _widget_show_files, False

        if intent_name == "show_status":
            return "Current pipeline status:", _widget_show_status, False

        if intent_name == "cancel_pipeline":
            if not st.session_state.get("pipeline_running", False):
                return "No pipeline is currently running.", None, False
            run = st.session_state.get("_pipeline_run")
            if run is None:
                return "Pipeline state not found — it may have already finished.", None, False
            run.cancel_event.set()
            return "🛑 Cancel requested — the pipeline will stop after the current step finishes.", None, False

        if intent_name == "help":
            return _HELP_TEXT, None, False

    # No intent matched — LLM fallback
    return _llm_fallback(text), None, False


# ── Main entry point ──────────────────────────────────────────────────────────

def render_chat():
    """Render the chat panel. Call this from app.py after render_upload()."""

    # ── Session state defaults ─────────────────────────────────────────────
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []
    if "chat_triggered_pipeline" not in st.session_state:
        st.session_state["chat_triggered_pipeline"] = False
    if "chat_pipeline_mode" not in st.session_state:
        st.session_state["chat_pipeline_mode"] = None

    st.divider()
    st.subheader("💬 Chat")

    # ── Quick-action buttons ───────────────────────────────────────────────
    is_running = st.session_state.get("pipeline_running", False)
    has_cdm    = st.session_state.get("pipeline_result") is not None
    has_ldm    = st.session_state.get("ldm_result") is not None
    uploaded   = st.session_state.get("current_uploaded_file")

    qa_cols = st.columns(4)
    with qa_cols[0]:
        if st.button("▶ CDM", disabled=is_running or not uploaded, use_container_width=True,
                     key="qa_cdm", help="Run 8-step CDM pipeline"):
            ok, err = _check_prereqs("CDM only")
            txt = _trigger_pipeline("CDM only") if ok else err
            st.session_state["chat_messages"].append({"role": "user",      "content": "Run CDM", "widget": None})
            st.session_state["chat_messages"].append({"role": "assistant", "content": txt,       "widget": None})
            st.rerun()
    with qa_cols[1]:
        if st.button("⚡ LDM only", disabled=is_running or not has_cdm, use_container_width=True,
                     key="qa_ldm", help="Promote CDM → LDM (Steps A+B+V)"):
            ok, err = _check_prereqs("LDM only")
            txt = _trigger_pipeline("LDM only") if ok else err
            st.session_state["chat_messages"].append({"role": "user",      "content": "Run LDM only", "widget": None})
            st.session_state["chat_messages"].append({"role": "assistant", "content": txt,            "widget": None})
            st.rerun()
    with qa_cols[2]:
        if st.button("🏗️ Full pipeline", disabled=is_running or not uploaded, use_container_width=True,
                     key="qa_full", help="CDM + LDM + PDM end-to-end"):
            ok, err = _check_prereqs("CDM + LDM + PDM")
            txt = _trigger_pipeline("CDM + LDM + PDM") if ok else err
            st.session_state["chat_messages"].append({"role": "user",      "content": "Run full pipeline", "widget": None})
            st.session_state["chat_messages"].append({"role": "assistant", "content": txt,                 "widget": None})
            st.rerun()
    with qa_cols[3]:
        if st.button("🛑 Cancel", disabled=not is_running, use_container_width=True,
                     key="qa_cancel", help="Cancel the running pipeline"):
            run = st.session_state.get("_pipeline_run")
            if run:
                run.cancel_event.set()
                msg = "🛑 Cancel requested — stopping after the current step."
            else:
                msg = "No active pipeline found."
            st.session_state["chat_messages"].append({"role": "assistant", "content": msg, "widget": None})
            st.rerun()

    # ── Post-completion summary ────────────────────────────────────────────
    # Fires once on the rerun after chat-triggered pipeline finishes.
    if (
        st.session_state.get("chat_triggered_pipeline")
        and not st.session_state.get("pipeline_running", False)
    ):
        mode = st.session_state.get("chat_pipeline_mode", "pipeline")
        content, widget = _build_completion_summary(mode)
        st.session_state["chat_messages"].append(
            {"role": "assistant", "content": content, "widget": widget}
        )
        st.session_state["chat_triggered_pipeline"] = False
        st.session_state["chat_pipeline_mode"]      = None

    # ── Replay history ─────────────────────────────────────────────────────
    for msg in st.session_state["chat_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            widget = msg.get("widget")
            if widget:
                try:
                    widget()
                except Exception as e:
                    st.caption(f"(Could not render inline result: {e})")

    # ── Accept input ───────────────────────────────────────────────────────
    user_input = st.chat_input(
        "Ask me anything — or type 'help' for commands",
        key="chat_input_box",
    )
    if not user_input:
        return

    st.session_state["chat_messages"].append(
        {"role": "user", "content": user_input, "widget": None}
    )

    response_text, widget_fn, should_rerun = _dispatch(user_input.strip())

    st.session_state["chat_messages"].append(
        {"role": "assistant", "content": response_text, "widget": widget_fn}
    )

    st.rerun()
