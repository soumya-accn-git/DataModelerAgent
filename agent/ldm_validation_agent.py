"""
LDM Validation Agent — sub-agent that validates the LDM result against
the BRD requirements and structural rules, then triggers targeted repairs.

Three checks run in sequence:
  Check 1 — FR coverage        (LLM call: reads BRD + LDM, maps every FR)
  Check 2 — Structural rules   (rule-based: mandatory FKs, SCD, naming)
  Check 3 — Grain validation   (LLM call: verifies fact grains match BRD)

If any check fails the agent generates a targeted repair prompt and
re-runs Step B (CDM→LDM promotion) with the specific gap as context.
Maximum 3 repair iterations before accepting with flagged issues.

Persona: You are an experienced subject matter expert in Data Modeling,
specifically in Dimensional Modeling and able to precisely design data
models Ontology and Graph RAG. Use your knowledge and experience in
modeling the DWH schema for CDM and LDM.
"""

import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from agent.ollama_client   import chat, extract_json
from agent.ldm_conventions import (
    MANDATORY_FACT_FKS, FACTS_WITHOUT_PRODUCT, SCD_ASSIGNMENTS,
    FORBIDDEN_SUFFIXES, enforce_ldm_naming, enforce_mandatory_fks,
    TABLE_PREFIXES,
)

PERSONA = (
    "You are an experienced subject matter expert in Data Modeling, "
    "specifically in Dimensional Modeling and able to precisely design "
    "data models Ontology and Graph RAG. Use your knowledge and experience "
    "in modeling the DWH schema for CDM and LDM.\n\n"
)

MAX_RETRIES = 3


# ── Check 1 — FR coverage (LLM) ──────────────────────────────────────────────

SYSTEM_FR = PERSONA + """Validate that a Logical Data Model satisfies the
Functional Requirements in a Business Requirements Document.

For each FR in the BRD, determine:
- Is it COVERED by at least one table or column in the LDM?
- If not, what specific table or column is missing?

Respond ONLY with valid JSON, no explanation, no markdown."""

USER_FR = """Check whether the LDM satisfies every Functional Requirement.

BRD FUNCTIONAL REQUIREMENTS:
{brd_frs}

LDM TABLES (summary):
{ldm_summary}

For each FR return:
- "fr_id": e.g. "FR-001"
- "status": "COVERED" or "GAP"
- "covered_by": table or column name (if COVERED)
- "gap_description": what is missing (if GAP)
- "repair_hint": specific table/column to add (if GAP)

Return: {{"fr_checks": [...]}}
JSON:"""


# ── Check 2 — Structural rules (rule-based) ───────────────────────────────────

def _check_structural(ldm_result: dict) -> list[dict]:
    """
    Rule-based structural validation. No LLM calls.
    Returns list of issues: {rule, table, issue, severity, fix}
    """
    issues = []
    all_tables = (
        ldm_result.get("dimension_tables", []) +
        ldm_result.get("fact_tables", []) +
        ldm_result.get("bridge_tables", []) +
        ldm_result.get("reference_tables", [])
    )

    for table in all_tables:
        name = table.get("table_name", "")
        cols  = {c.get("name","").upper() for c in table.get("columns",[])}

        # Rule S1 — naming convention
        if name.startswith("DIM_") or name.startswith("FACT_") or \
           name.startswith("BRIDGE_") or name.startswith("REF_"):
            pass  # correct
        else:
            issues.append({
                "rule": "S1-Naming",
                "table": name,
                "issue": f"Table name '{name}' missing required prefix (DIM_/FACT_/BRIDGE_/REF_)",
                "severity": "ERROR",
                "fix": f"Rename to DIM_{name} or FACT_{name} as appropriate",
            })

        # Rule S2 — SCD2 columns on SCD2 dimensions
        if name in SCD_ASSIGNMENTS and SCD_ASSIGNMENTS[name] == 2:
            for scd_col in ("EFFECTIVE_DATE", "EXPIRY_DATE", "CURRENT_FLAG"):
                if scd_col not in cols:
                    issues.append({
                        "rule": "S2-SCD2",
                        "table": name,
                        "issue": f"SCD2 table '{name}' missing column '{scd_col}'",
                        "severity": "ERROR",
                        "fix": f"Add '{scd_col}' column to {name}",
                    })

        # Rule S3 — mandatory FK columns on fact tables
        if name.startswith("FACT_") and name not in FACTS_WITHOUT_PRODUCT:
            for fk_col in MANDATORY_FACT_FKS:
                if fk_col not in cols:
                    issues.append({
                        "rule": "S3-MandatoryFK",
                        "table": name,
                        "issue": f"Fact table '{name}' missing mandatory FK '{fk_col}'",
                        "severity": "ERROR",
                        "fix": f"Add '{fk_col}' FK column to {name}",
                    })

        # Rule S4 — no metric columns in dimension tables
        if name.startswith("DIM_"):
            for col in table.get("columns", []):
                cname = col.get("name","").upper()
                dtype = col.get("data_type","").upper()
                if ("NUMBER(18,4)" in dtype or "NUMBER(12,2)" in dtype) and \
                   not col.get("is_fk") and not col.get("is_pk"):
                    issues.append({
                        "rule": "S4-NoMetricInDim",
                        "table": name,
                        "issue": f"Dimension table '{name}' has metric column '{cname}' (NUMBER(18,4) — looks like a measure)",
                        "severity": "WARNING",
                        "fix": f"Move '{cname}' to appropriate FACT_ table",
                    })

        # Rule S5 — fact tables must have ANALYSIS_MODE_CODE for As-Is/As-Was
        if name in ("FACT_SALES", "FACT_MARKDOWN") and \
           "ANALYSIS_MODE_CODE" not in cols:
            issues.append({
                "rule": "S5-AnalysisMode",
                "table": name,
                "issue": f"'{name}' missing ANALYSIS_MODE_CODE column (required for FR-018 As-Is/As-Was)",
                "severity": "ERROR",
                "fix": "Add ANALYSIS_MODE_CODE VARCHAR2(15) NOT NULL to " + name,
            })

        # Rule S6 — SOURCE_SYSTEM_CODE on all tables
        if "SOURCE_SYSTEM_CODE" not in cols and not name.startswith("BRIDGE_"):
            issues.append({
                "rule": "S6-SourceTracking",
                "table": name,
                "issue": f"'{name}' missing SOURCE_SYSTEM_CODE column",
                "severity": "WARNING",
                "fix": f"Add SOURCE_SYSTEM_CODE VARCHAR2(10) to {name}",
            })

    return issues


# ── Check 3 — Grain validation (LLM) ─────────────────────────────────────────

SYSTEM_GRAIN = PERSONA + """Validate that the grain declarations of fact tables
in a Logical Data Model are correct and match the BRD requirements.

For each fact table verify:
- The declared grain is appropriate for the business requirement
- The grain columns (FK set) match the declared grain
- Each metric is correctly classified as additive/semi-additive/non-additive

Respond ONLY with valid JSON, no explanation, no markdown."""

USER_GRAIN = """Validate the grain declarations for these fact tables.

FACT TABLES:
{fact_summary}

BRD CONTEXT:
{brd_context}

For each fact table return:
- "table_name": e.g. "FACT_SALES"
- "declared_grain": grain as stated in LDM
- "grain_status": "CORRECT" or "ISSUE"
- "grain_issue": description of issue if any
- "metric_issues": list of any mis-classified metrics
- "repair_hint": what to fix if issues found

Return: {{"grain_checks": [...]}}
JSON:"""


# ── Repair prompt builder ─────────────────────────────────────────────────────

def _build_repair_prompt(
    fr_gaps:    list[dict],
    struct_errors: list[dict],
    grain_issues: list[dict],
) -> str:
    """Build a targeted repair prompt for Step B re-run."""
    parts = ["The LDM has the following gaps that must be fixed:\n"]

    if fr_gaps:
        parts.append("FR COVERAGE GAPS:")
        for g in fr_gaps:
            parts.append(
                f"  [{g['fr_id']}] {g['gap_description']} → Fix: {g['repair_hint']}"
            )

    if struct_errors:
        parts.append("\nSTRUCTURAL ERRORS:")
        for e in struct_errors:
            if e["severity"] == "ERROR":
                parts.append(f"  [{e['rule']}] {e['table']}: {e['issue']} → Fix: {e['fix']}")

    if grain_issues:
        parts.append("\nGRAIN ISSUES:")
        for g in grain_issues:
            if g.get("grain_status") == "ISSUE":
                parts.append(
                    f"  {g['table_name']}: {g.get('grain_issue','')} → Fix: {g.get('repair_hint','')}"
                )

    parts.append(
        "\nRe-expand the affected tables to address ALL issues above. "
        "Keep all correct tables unchanged."
    )
    return "\n".join(parts)


# ── Helper — extract FRs from BRD text ───────────────────────────────────────

def _extract_frs(brd_text: str) -> str:
    """Extract FR lines from BRD text for the validation prompt."""
    lines = []
    for line in brd_text.splitlines():
        if re.search(r'\bFR[-\s]?\d+\b', line, re.IGNORECASE) or \
           re.search(r'functional requirement', line, re.IGNORECASE):
            lines.append(line.strip())
    return "\n".join(lines[:60]) if lines else brd_text[:2000]


def _summarise_ldm(ldm_result: dict) -> str:
    """Compact LDM summary for validation prompts."""
    lines = []
    for table in ldm_result.get("dimension_tables", []):
        cols = [c["name"] for c in table.get("columns", [])[:6]]
        lines.append(f"[DIM] {table['table_name']}: {', '.join(cols)}...")
    for table in ldm_result.get("fact_tables", []):
        cols = [c["name"] for c in table.get("columns", [])[:8]]
        lines.append(f"[FACT] {table['table_name']}: {', '.join(cols)}...")
    for table in ldm_result.get("bridge_tables", []):
        lines.append(f"[BRIDGE] {table['table_name']}")
    for table in ldm_result.get("reference_tables", []):
        lines.append(f"[REF] {table['table_name']}")
    return "\n".join(lines)


def _summarise_facts(ldm_result: dict) -> str:
    """Fact table summary for grain validation."""
    lines = []
    for t in ldm_result.get("fact_tables", []):
        grain = t.get("grain", "not declared")
        gcols = ", ".join(t.get("grain_columns", []))
        additive = ", ".join(t.get("additive_metrics", [])[:4])
        lines.append(
            f"{t['table_name']}:\n"
            f"  Grain: {grain}\n"
            f"  Grain columns: {gcols}\n"
            f"  Additive metrics: {additive}"
        )
    return "\n\n".join(lines)


# ── Main agent ────────────────────────────────────────────────────────────────

def run_validation_agent(
    ldm_result:  dict,
    brd_text:    str,
    ollama_url:  str,
    model:       str,
    temperature: float = 0.1,
    on_log             = None,
    on_check_done      = None,
) -> dict:
    """
    Run all three validation checks against the LDM result.

    Args:
        ldm_result:   Output from step_ldm_promote / ldm_pipeline
        brd_text:     Full BRD text
        ollama_url:   Ollama base URL
        model:        Ollama model name
        temperature:  LLM temperature
        on_log:       Logging callback fn(str)
        on_check_done: Callback fn(check_name, status, issues_count)

    Returns:
        {
            passed:           bool
            fr_checks:        list
            structural_checks: list
            grain_checks:     list
            repair_prompt:    str | None  (None if passed)
            fr_gaps:          int
            structural_errors: int
            grain_issues:     int
            total_issues:     int
        }
    """
    def log(msg):
        if on_log: on_log(msg)

    def check_done(name, status, n):
        if on_check_done: on_check_done(name, status, n)

    log("Validation agent starting…")
    brd_frs  = _extract_frs(brd_text)
    ldm_sum  = _summarise_ldm(ldm_result)
    fact_sum = _summarise_facts(ldm_result)
    brd_ctx  = brd_text[:2500]

    # ── Check 1 — FR coverage ─────────────────────────────────────────────
    log("Check 1 — FR coverage (LLM)…")
    fr_checks = []
    try:
        raw1 = chat(
            base_url=ollama_url, model=model,
            messages=[
                {"role": "system", "content": SYSTEM_FR},
                {"role": "user",   "content": USER_FR.format(
                    brd_frs=brd_frs, ldm_summary=ldm_sum,
                )},
            ],
            temperature=temperature, format="json",
        )
        data1 = extract_json(raw1)
        fr_checks = data1.get("fr_checks", []) if isinstance(data1, dict) else []
        log(f"  {len(fr_checks)} FRs checked")
    except Exception as e:
        log(f"  Check 1 failed: {e}")

    fr_gaps = [c for c in fr_checks if c.get("status") == "GAP"]
    check_done("FR coverage", "PASS" if not fr_gaps else "FAIL", len(fr_gaps))
    log(f"  FR gaps: {len(fr_gaps)}")

    # ── Check 2 — Structural rules ────────────────────────────────────────
    log("Check 2 — Structural rules (rule-based)…")
    structural_issues = _check_structural(ldm_result)
    struct_errors = [i for i in structural_issues if i["severity"] == "ERROR"]
    struct_warns  = [i for i in structural_issues if i["severity"] == "WARNING"]
    check_done("Structural rules", "PASS" if not struct_errors else "FAIL", len(struct_errors))
    log(f"  Structural errors: {len(struct_errors)}, warnings: {len(struct_warns)}")

    # ── Check 3 — Grain validation ────────────────────────────────────────
    log("Check 3 — Grain validation (LLM)…")
    grain_checks = []
    if ldm_result.get("fact_tables"):
        try:
            raw3 = chat(
                base_url=ollama_url, model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_GRAIN},
                    {"role": "user",   "content": USER_GRAIN.format(
                        fact_summary=fact_sum, brd_context=brd_ctx,
                    )},
                ],
                temperature=temperature, format="json",
            )
            data3 = extract_json(raw3)
            grain_checks = data3.get("grain_checks", []) if isinstance(data3, dict) else []
            log(f"  {len(grain_checks)} fact tables grain-checked")
        except Exception as e:
            log(f"  Check 3 failed: {e}")

    grain_issues = [g for g in grain_checks if g.get("grain_status") == "ISSUE"]
    check_done("Grain validation", "PASS" if not grain_issues else "FAIL", len(grain_issues))
    log(f"  Grain issues: {len(grain_issues)}")

    # ── Build result ──────────────────────────────────────────────────────
    total = len(fr_gaps) + len(struct_errors) + len(grain_issues)
    passed = total == 0

    repair_prompt = None
    if not passed:
        repair_prompt = _build_repair_prompt(fr_gaps, struct_errors, grain_issues)
        log(f"Validation FAILED — {total} issue(s) found")
        log("Repair prompt generated for Step B re-run")
    else:
        log("Validation PASSED — LDM approved ✅")

    return {
        "passed":             passed,
        "fr_checks":          fr_checks,
        "structural_checks":  structural_issues,
        "grain_checks":       grain_checks,
        "repair_prompt":      repair_prompt,
        "fr_gaps":            len(fr_gaps),
        "structural_errors":  len(struct_errors),
        "structural_warnings":len(struct_warns),
        "grain_issues":       len(grain_issues),
        "total_issues":       total,
    }


# ── Iterative repair loop ─────────────────────────────────────────────────────

def run_with_repair(
    ldm_result:  dict,
    cdm_result:  dict,
    brd_text:    str,
    ollama_url:  str,
    model:       str,
    chroma_path: str,
    temperature: float = 0.1,
    max_retries: int   = MAX_RETRIES,
    on_log             = None,
    on_check_done      = None,
    on_iteration       = None,
) -> dict:
    """
    Run validation + repair loop.
    On failure: re-runs Step B with targeted repair prompt.
    Stops when all checks pass or max_retries is reached.

    Returns:
        {
            ldm_result:        final LDM (repaired or original)
            validation_result: final validation result
            iterations:        number of repair iterations run
            repaired:          bool — whether any repair was made
        }
    """
    def log(msg):
        if on_log: on_log(msg)

    from agent.step_ldm_promote import promote_cdm_to_ldm

    current_ldm = ldm_result
    iterations  = 0
    repaired    = False

    for attempt in range(max_retries + 1):
        log(f"Validation attempt {attempt + 1}/{max_retries + 1}…")
        if on_iteration: on_iteration(attempt + 1)

        result = run_validation_agent(
            ldm_result=current_ldm,
            brd_text=brd_text,
            ollama_url=ollama_url,
            model=model,
            temperature=temperature,
            on_log=log,
            on_check_done=on_check_done,
        )

        if result["passed"]:
            log(f"✅ Validation passed on attempt {attempt + 1}")
            return {
                "ldm_result":        current_ldm,
                "validation_result": result,
                "iterations":        iterations,
                "repaired":          repaired,
            }

        if attempt >= max_retries:
            log(f"⚠️  Max retries ({max_retries}) reached — accepting LDM with flagged issues")
            result["accepted_with_issues"] = True
            return {
                "ldm_result":        current_ldm,
                "validation_result": result,
                "iterations":        iterations,
                "repaired":          repaired,
            }

        # Re-run Step B with repair prompt injected as additional context
        log(f"Re-running Step B with targeted repair prompt…")
        log(f"  Issues to fix: {result['total_issues']}")
        iterations += 1
        repaired    = True

        try:
            # Inject repair prompt into BRD context for Step B
            repair_brd = (
                result["repair_prompt"] +
                "\n\n=== ORIGINAL BRD ===\n" + brd_text
            )
            current_ldm = promote_cdm_to_ldm(
                cdm_result=cdm_result,
                brd_text=repair_brd,
                ollama_url=ollama_url,
                model=model,
                chroma_path=chroma_path,
                temperature=temperature,
                on_log=log,
            )
            log(f"  Repair iteration {iterations} complete")
        except Exception as e:
            log(f"  Repair failed: {e} — stopping")
            return {
                "ldm_result":        current_ldm,
                "validation_result": result,
                "iterations":        iterations,
                "repaired":          repaired,
            }

    return {
        "ldm_result":        current_ldm,
        "validation_result": result,
        "iterations":        iterations,
        "repaired":          repaired,
    }
