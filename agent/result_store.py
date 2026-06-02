"""
Result store — persists CDM and LDM results to disk.

CDM and LDM results are stored as JSON files keyed by BRD hash:
    ontology/generated/<brd_hash>_cdm_result.json
    ontology/generated/<brd_hash>_ldm_result.json

This means:
  - Results survive Streamlit session restarts
  - LDM-only mode can reload the CDM without re-running the pipeline
  - Different BRDs have independent cached results
  - Results can be inspected / debugged outside Streamlit

Usage:
    from agent.result_store import save_cdm, load_cdm, save_ldm, load_ldm, list_stored
"""

import os, json, hashlib

GENERATED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ontology", "generated")
os.makedirs(GENERATED_DIR, exist_ok=True)


def _brd_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _cdm_path(brd_hash: str) -> str:
    return os.path.join(GENERATED_DIR, f"{brd_hash}_cdm_result.json")


def _ldm_path(brd_hash: str) -> str:
    return os.path.join(GENERATED_DIR, f"{brd_hash}_ldm_result.json")


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


# ── Inventory ─────────────────────────────────────────────────────────────────

def list_stored() -> list[dict]:
    """
    List all stored CDM and LDM results with metadata.
    Returns list of dicts: {brd_hash, has_cdm, has_ldm, cdm_path, ldm_path, modified}
    """
    hashes = set()
    for f in os.listdir(GENERATED_DIR):
        if f.endswith(("_cdm_result.json", "_ldm_result.json")):
            hashes.add(f.split("_")[0])

    results = []
    for brd_hash in sorted(hashes):
        cdm_p = _cdm_path(brd_hash)
        ldm_p = _ldm_path(brd_hash)
        has_cdm = os.path.exists(cdm_p)
        has_ldm = os.path.exists(ldm_p)
        modified = (
            os.path.getmtime(ldm_p if has_ldm else cdm_p)
            if (has_cdm or has_ldm) else 0
        )
        results.append({
            "brd_hash":  brd_hash,
            "has_cdm":   has_cdm,
            "has_ldm":   has_ldm,
            "cdm_path":  cdm_p if has_cdm else None,
            "ldm_path":  ldm_p if has_ldm else None,
            "modified":  modified,
        })
    return sorted(results, key=lambda r: r["modified"], reverse=True)
