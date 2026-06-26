"""
LDM Pipeline Orchestrator

Runs after the CDM pipeline completes. Calls Steps A–B
(seeder and CDM→LDM promotion). Steps C–F (SCD, grain,
normalisation, DDL) are called separately once built.

Entry point: run_ldm_pipeline(cdm_result, brd_text, ...)
"""

import sys, os, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from src.agents.pipeline_agent import PipelineCancelledError
from src.knowledge.ldm_seeder           import seed_oracle_reference, query_oracle_reference
from src.knowledge.ri_metrics           import seed_ri_metrics
from src.knowledge.oracle_rdm_seeder    import seed_oracle_rdm
from src.knowledge.oltp_schema_seeder  import seed_oltp_schema
from src.pipeline.step_ldm_promote     import promote_cdm_to_ldm
from src.agents.ldm_validation_agent import run_with_repair


def run_ldm_pipeline(
    cdm_result:    dict,
    brd_text:      str,
    ollama_url:    str,
    model:         str,
    chroma_path:   str,
    temperature:   float = 0.1,
    run_validation: bool = True,
    run_pdm:        bool = False,
    bq_project:     str  = "",
    bq_dataset:     str  = "",
    cancel_event:   threading.Event | None = None,
    on_step_start  = None,
    on_step_done   = None,
    on_log         = None,
) -> dict:
    """
    Run the LDM pipeline from CDM output.

    Steps:
      A — Seed Oracle reference into ChromaDB (skipped if already done)
      B — Promote CDM entities to full LDM table definitions via RAG
      V — Validation agent: FR coverage + structural + grain checks
          (with up to 3 targeted repair iterations)
    """
    def _check_cancel():
        if cancel_event and cancel_event.is_set():
            raise PipelineCancelledError("LDM pipeline cancelled by user")

    def start(name):
        _check_cancel()
        if on_step_start: on_step_start(name)

    def done(name, detail=""):
        if on_step_done: on_step_done(name, detail)

    def log(msg):
        if on_log: on_log(msg)

    # ── Step A — Oracle reference seeder ──────────────────────────────────────
    start("Step A — Oracle seeder")
    log("Checking Oracle Retail reference collection…")
    try:
        n = seed_oracle_reference(
            chroma_path=chroma_path,
            force=False,
            on_log=log,
        )
        # Also seed the Retail Insights metric-definitions catalog so fact-table
        # expansion can ground its measure columns in the Oracle standard.
        log("Checking Oracle Retail Insights metrics collection…")
        m = seed_ri_metrics(chroma_path=chroma_path, force=False, on_log=log)

        # And the full Oracle Retail Data Model (927 logical entities + physical
        # tables, BRD-domain scoped), used as RAG grounding for CDM/LDM/Physical
        # design. Requires oracle_rdm_entities.json / oracle_rdm_tables.json in
        # agent/data/ — if absent, log and continue (RAG falls back to the
        # Oracle Retail Insights reference).
        rdm_bit = "RDM skipped"
        try:
            log("Checking Oracle Retail Data Model collections…")
            counts = seed_oracle_rdm(chroma_path=chroma_path, force=False, on_log=log)
            ldm_n, pdm_n = counts.get("ldm", 0), counts.get("pdm", 0)
            rdm_bit = ("⚡ RDM cached" if ldm_n == 0 and pdm_n == 0
                       else f"{ldm_n} entities · {pdm_n} tables")
        except FileNotFoundError:
            log("Oracle RDM JSON data files not found — skipping RDM seed "
                "(run the PDF extractor to enable). RAG falls back to Insights reference.")
        except Exception as e:
            log(f"Oracle RDM seed warning: {e} — continuing")

        # Seed the OLTP source schema (retail merchandising OLTP tables as RAG
        # grounding for column-level LDM/PDM generation).
        oltp_bit = "OLTP skipped"
        try:
            log("Checking OLTP source schema collection…")
            oltp_n = seed_oltp_schema(chroma_path=chroma_path, force=False, on_log=log)
            oltp_bit = ("⚡ OLTP schema cached" if oltp_n == 0
                        else f"{oltp_n} OLTP tables seeded")
        except Exception as e:
            log(f"OLTP schema seed warning: {e} — continuing")

        seeded_bits = []
        seeded_bits.append("⚡ reference cached" if n == 0 else f"{n} reference chunks")
        seeded_bits.append("⚡ metrics cached" if m == 0 else f"{m} metric areas")
        seeded_bits.append(rdm_bit)
        seeded_bits.append(oltp_bit)
        done("Step A — Oracle seeder", " · ".join(seeded_bits))
    except Exception as e:
        log(f"Oracle seeder warning: {e} — continuing with empty reference")
        done("Step A — Oracle seeder", f"⚠️ {e}")

    # ── Step B — CDM → LDM promotion ─────────────────────────────────────────
    start("Step B — CDM→LDM")
    log("Promoting CDM entities to LDM table definitions…")
    try:
        ldm_result = promote_cdm_to_ldm(
            cdm_result=cdm_result,
            brd_text=brd_text,
            ollama_url=ollama_url,
            model=model,
            chroma_path=chroma_path,
            temperature=temperature,
            on_log=log,
        )
        n_tables = ldm_result.get("entity_count", 0)
        done("Step B — CDM→LDM",
             f"{n_tables} tables defined "
             f"({len(ldm_result.get('dimension_tables',[]))} dims, "
             f"{len(ldm_result.get('fact_tables',[]))} facts)")
    except Exception as e:
        log(f"LDM promotion failed: {e}")
        raise RuntimeError(f"LDM pipeline failed at Step B: {e}") from e

    # ── Step V — Validation agent ────────────────────────────────────────────
    if run_validation and brd_text:
        start("Step V — LDM Validation")
        log("Running validation agent (FR coverage + structural + grain)…")

        def on_check(check_name, status, n):
            icon = "✅" if status == "PASS" else "❌"
            log(f"  {icon} {check_name}: {status} ({n} issues)")

        def on_iter(i):
            log(f"  Repair iteration {i}…")

        try:
            repair_result = run_with_repair(
                ldm_result=ldm_result,
                cdm_result=cdm_result,
                brd_text=brd_text,
                ollama_url=ollama_url,
                model=model,
                chroma_path=chroma_path,
                temperature=temperature,
                on_log=log,
                on_check_done=on_check,
                on_iteration=on_iter,
            )
            ldm_result  = repair_result["ldm_result"]
            val_result  = repair_result["validation_result"]
            iterations  = repair_result["iterations"]
            repaired    = repair_result["repaired"]

            total_issues = val_result.get("total_issues", 0)
            accepted_with = val_result.get("accepted_with_issues", False)

            if val_result.get("passed"):
                status_str = f"✅ Passed · {iterations} repair(s)"
            elif accepted_with:
                status_str = f"⚠️ Accepted with {total_issues} issue(s)"
            else:
                status_str = f"✅ Passed after {iterations} repair(s)"

            done("Step V — LDM Validation", status_str)
            ldm_result["_validation"] = val_result

        except Exception as e:
            log(f"Validation agent error: {e} — continuing with unvalidated LDM")
            done("Step V — LDM Validation", f"⚠️ Skipped: {e}")
    else:
        log("Validation skipped (no BRD text or run_validation=False)")

    # ── Step P — BigQuery PDM ─────────────────────────────────────────────────
    if run_pdm:
        start("Step P — BigQuery PDM")
        log("Generating BigQuery Physical Data Model DDL…")
        try:
            from src.pipeline.step_pdm_bq import build_pdm_output, BQ_PROJECT_DEFAULT, BQ_DATASET_DEFAULT
            project = bq_project or BQ_PROJECT_DEFAULT
            dataset = bq_dataset or BQ_DATASET_DEFAULT
            pdm_result = build_pdm_output(
                ldm_result=ldm_result,
                project=project,
                dataset=dataset,
                on_log=log,
            )
            ldm_result["_pdm"] = pdm_result
            done("Step P — BigQuery PDM",
                 f"{pdm_result['table_count']} tables · "
                 f"{len(pdm_result['audit_cols'])} audit cols · "
                 f"project={project}")
        except Exception as e:
            log(f"PDM step warning: {e} — continuing without PDM")
            done("Step P — BigQuery PDM", f"⚠️ {e}")

    return ldm_result
