"""
Step — BRD parsing via brd_parser_claude.bat (Claude Sonnet 4.6).

Replaces the Ollama-based entity extraction (step2_entities) and
relationship detection (step3_relationships) with a single Claude CLI
call routed through brd_parser_claude.bat.

The bat file:
  1. Saves the uploaded BRD to a temp .docx on disk
  2. Extracts plain text via python-docx
  3. Pipes text + prompt to:  claude --model claude-sonnet-4-6 -p
  4. Returns JSON with {entities, relationships} to stdout
"""

import os
import subprocess
import tempfile

from src.tools.ollama_client import extract_json

# Absolute path to the bat file at project root
_BAT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                 "brd_parser_claude.bat")
)

# Expected entity types — normalise LLM drift
_VALID_TYPES = {"dimension", "fact", "reference", "bridge"}
# Names whose meaning almost always signals a fact table
_FACT_TOKENS = {
    "sales", "sale", "profit", "revenue", "margin", "markdown",
    "forecast", "transaction", "payment", "order", "shipment",
    "receipt", "cost", "spend", "budget", "actuals",
}


def parse_brd_via_bat(file, on_log=None) -> dict:
    """
    Save the Streamlit UploadedFile to a temp path, invoke brd_parser_claude.bat,
    parse the JSON output and return normalised entities + relationships.

    Returns:
        {
          "entities":      [{name, type, attributes, description, source}, ...],
          "relationships": [{source, target, type, name}, ...],
        }
    """
    brd_bytes = file.getvalue() if hasattr(file, "getvalue") else file.read()

    # Write to temp .docx so the bat file can read it
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(brd_bytes)
        tmp_path = tmp.name

    try:
        if on_log:
            on_log(f"Calling brd_parser_claude.bat — {os.path.basename(tmp_path)}")

        proc = subprocess.run(
            ["cmd", "/c", _BAT, tmp_path],
            capture_output=True,
            text=True,
            timeout=300,
        )

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        if on_log:
            on_log(f"Claude response: {len(stdout)} chars · exit {proc.returncode}")

        if not stdout.strip():
            raise RuntimeError(
                f"brd_parser_claude.bat produced no output "
                f"(exit {proc.returncode}).\n{stderr[:400]}"
            )

        # extract_json scans for first { or [ — skips bat echo lines
        data = extract_json(stdout)
        entities      = _normalise_entities(data.get("entities", []))
        relationships = _normalise_relationships(data.get("relationships", []))

        if on_log:
            on_log(
                f"Parsed {len(entities)} entities · "
                f"{len(relationships)} relationships"
            )
        return {"entities": entities, "relationships": relationships}

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Normalisation helpers ─────────────────────────────────────────────────────

def _normalise_entities(raw: list) -> list:
    seen_names: set[str] = set()
    out = []
    for e in raw:
        name = (e.get("name") or "").strip()
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())

        etype = (e.get("type") or "dimension").strip().lower()
        if etype not in _VALID_TYPES:
            etype = "dimension"

        # Force obvious fact entities that the LLM mislabelled
        if etype != "fact" and any(t in name.lower() for t in _FACT_TOKENS):
            etype = "fact"

        attrs = e.get("attributes") or []
        if isinstance(attrs, str):
            attrs = [a.strip() for a in attrs.split(",") if a.strip()]

        out.append({
            "name":        name,
            "type":        etype,
            "attributes":  attrs,
            "description": (e.get("description") or "").strip(),
            "source":      "claude-bat",
        })
    return out


def _normalise_relationships(raw: list) -> list:
    _VALID_REL_TYPES = {
        "MANY_TO_ONE", "ONE_TO_MANY", "ONE_TO_ONE", "MANY_TO_MANY"
    }
    out = []
    for r in raw:
        src = (r.get("source") or "").strip()
        tgt = (r.get("target") or "").strip()
        if not src or not tgt:
            continue

        rtype = (r.get("type") or "MANY_TO_ONE").strip().upper().replace(" ", "_")
        if rtype not in _VALID_REL_TYPES:
            rtype = "MANY_TO_ONE"

        name = (r.get("name") or f"{src}_to_{tgt}").strip()

        out.append({"source": src, "target": tgt, "type": rtype, "name": name})
    return out
