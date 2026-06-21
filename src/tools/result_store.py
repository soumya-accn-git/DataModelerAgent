"""
Result store — persists CDM, LDM, and PDM results to disk.

Results are stored as JSON files keyed by BRD hash:
    ontology/generated/<brd_hash>_cdm_result.json
    ontology/generated/<brd_hash>_ldm_result.json
    ontology/generated/<brd_hash>_pdm_result.json

This means:
  - Results survive Streamlit session restarts
  - LDM-only mode can reload the CDM without re-running the pipeline
  - Different BRDs have independent cached results
  - Results can be inspected / debugged outside Streamlit

Usage:
    from src.tools.result_store import (
        save_cdm, load_cdm, save_ldm, load_ldm,
        save_pdm, load_pdm, list_stored,
    )
"""

import os, json, hashlib

GENERATED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ontology", "generated")
os.makedirs(GENERATED_DIR, exist_ok=True)

# ── Data Models Generated (human-readable output folder) ─────────────────────
DMG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "Data Models Generated")


def get_dmg_dir(sub: str = "") -> str:
    """Return the Data Models Generated directory (or a CDM/LDM/PDM subfolder),
    creating it on first call."""
    d = os.path.join(DMG_DIR, sub) if sub else DMG_DIR
    os.makedirs(d, exist_ok=True)
    return d


def save_dmg_cdm(brd_hash: str, cdm_result: dict, mermaid: str = "") -> dict:
    """Save CDM artefacts to Data Models Generated/CDM/. Returns {label: abs_path}."""
    d = get_dmg_dir("CDM")
    paths: dict[str, str] = {}
    jp = os.path.join(d, f"{brd_hash}_CDM.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(cdm_result, f, indent=2, default=str)
    paths["CDM JSON"] = jp
    if mermaid:
        mp = os.path.join(d, f"{brd_hash}_CDM.mmd")
        with open(mp, "w", encoding="utf-8") as f:
            f.write(mermaid)
        paths["CDM Mermaid"] = mp
    return paths


def save_dmg_ldm(brd_hash: str, ddl_ansi: str, ddl_sf: str) -> dict:
    """Save LDM DDL artefacts to Data Models Generated/LDM/. Returns {label: abs_path}."""
    d = get_dmg_dir("LDM")
    ap = os.path.join(d, f"{brd_hash}_LDM_ANSI.sql")
    sp = os.path.join(d, f"{brd_hash}_LDM_Snowflake.sql")
    with open(ap, "w", encoding="utf-8") as f:
        f.write(ddl_ansi)
    with open(sp, "w", encoding="utf-8") as f:
        f.write(ddl_sf)
    return {"LDM ANSI SQL": ap, "LDM Snowflake SQL": sp}


def save_dmg_pdm(brd_hash: str, ddl_bq: str, dataset: str = "MERCH_DW") -> dict:
    """Save PDM BigQuery DDL to Data Models Generated/PDM/. Returns {label: abs_path}."""
    d = get_dmg_dir("PDM")
    bp = os.path.join(d, f"{brd_hash}_PDM_BigQuery_{dataset}.sql")
    with open(bp, "w", encoding="utf-8") as f:
        f.write(ddl_bq)
    return {"PDM BigQuery SQL": bp}


def _brd_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _cdm_path(brd_hash: str) -> str:
    return os.path.join(GENERATED_DIR, f"{brd_hash}_cdm_result.json")


def _ldm_path(brd_hash: str) -> str:
    return os.path.join(GENERATED_DIR, f"{brd_hash}_ldm_result.json")


def _pdm_path(brd_hash: str) -> str:
    return os.path.join(GENERATED_DIR, f"{brd_hash}_pdm_result.json")


# ── CDM ───────────────────────────────────────────────────────────────────────

def save_cdm(brd_hash: str, cdm_result: dict) -> str:
    """Save CDM result to disk. Returns path."""
    path = _cdm_path(brd_hash)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cdm_result, f, indent=2, default=str)
    return path


def load_cdm(brd_hash: str) -> dict | None:
    """Load CDM result from disk. Returns None if not found."""
    path = _cdm_path(brd_hash)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def latest_cdm() -> dict | None:
    """Return the most recently modified CDM result, or None."""
    files = [
        f for f in os.listdir(GENERATED_DIR)
        if f.endswith("_cdm_result.json")
    ]
    if not files:
        return None
    latest = max(files, key=lambda f: os.path.getmtime(
        os.path.join(GENERATED_DIR, f)
    ))
    try:
        with open(os.path.join(GENERATED_DIR, latest), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ── LDM ───────────────────────────────────────────────────────────────────────

def save_ldm(brd_hash: str, ldm_result: dict) -> str:
    """Save LDM result to disk. Returns path."""
    path = _ldm_path(brd_hash)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ldm_result, f, indent=2, default=str)
    return path


def load_ldm(brd_hash: str) -> dict | None:
    """Load LDM result from disk. Returns None if not found."""
    path = _ldm_path(brd_hash)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ── PDM ───────────────────────────────────────────────────────────────────────

def save_pdm(brd_hash: str, pdm_result: dict) -> str:
    """Save PDM result to disk. Returns path."""
    path = _pdm_path(brd_hash)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pdm_result, f, indent=2, default=str)
    return path


def load_pdm(brd_hash: str) -> dict | None:
    """Load PDM result from disk. Returns None if not found."""
    path = _pdm_path(brd_hash)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def latest_pdm() -> dict | None:
    """Return the most recently modified PDM result, or None."""
    files = [f for f in os.listdir(GENERATED_DIR) if f.endswith("_pdm_result.json")]
    if not files:
        return None
    latest = max(files, key=lambda f: os.path.getmtime(os.path.join(GENERATED_DIR, f)))
    try:
        with open(os.path.join(GENERATED_DIR, latest), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def latest_ldm() -> dict | None:
    """Return the most recently modified LDM result, or None."""
    files = [
        f for f in os.listdir(GENERATED_DIR)
        if f.endswith("_ldm_result.json")
    ]
    if not files:
        return None
    latest = max(files, key=lambda f: os.path.getmtime(
        os.path.join(GENERATED_DIR, f)
    ))
    try:
        with open(os.path.join(GENERATED_DIR, latest), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ── Run log ───────────────────────────────────────────────────────────────────

_RUN_LOG_PATH = os.path.join(GENERATED_DIR, "run_log.json")
_RUN_LOG_MAX  = 2


def save_run_log(entry: dict) -> None:
    """Append entry to the run log, keeping only the last _RUN_LOG_MAX entries."""
    entries = load_run_log()
    entries.append(entry)
    entries = entries[-_RUN_LOG_MAX:]
    with open(_RUN_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, default=str)


def load_run_log() -> list[dict]:
    """Load run log from disk. Returns [] if absent or unreadable."""
    if not os.path.exists(_RUN_LOG_PATH):
        return []
    try:
        with open(_RUN_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


# ── Inventory ─────────────────────────────────────────────────────────────────

def list_stored() -> list[dict]:
    """
    List all stored CDM, LDM, and PDM results with metadata.
    Returns list of dicts: {brd_hash, has_cdm, has_ldm, has_pdm, ..., modified}
    """
    hashes = set()
    for f in os.listdir(GENERATED_DIR):
        if f.endswith(("_cdm_result.json", "_ldm_result.json", "_pdm_result.json")):
            hashes.add(f.split("_")[0])

    results = []
    for brd_hash in sorted(hashes):
        cdm_p = _cdm_path(brd_hash)
        ldm_p = _ldm_path(brd_hash)
        pdm_p = _pdm_path(brd_hash)
        has_cdm = os.path.exists(cdm_p)
        has_ldm = os.path.exists(ldm_p)
        has_pdm = os.path.exists(pdm_p)
        newest  = max(
            (p for p in [cdm_p, ldm_p, pdm_p] if os.path.exists(p)),
            key=os.path.getmtime,
            default=None,
        )
        modified = os.path.getmtime(newest) if newest else 0
        results.append({
            "brd_hash":  brd_hash,
            "has_cdm":   has_cdm,
            "has_ldm":   has_ldm,
            "has_pdm":   has_pdm,
            "cdm_path":  cdm_p if has_cdm else None,
            "ldm_path":  ldm_p if has_ldm else None,
            "pdm_path":  pdm_p if has_pdm else None,
            "modified":  modified,
        })
    return sorted(results, key=lambda r: r["modified"], reverse=True)
