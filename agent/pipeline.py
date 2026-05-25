"""
Agent pipeline orchestrator.
Wires together all 5 steps and exposes callbacks for UI progress reporting.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from typing import Callable, Optional
from agent.step1_parser import parse_docx
from agent.step2_entities import extract_entities
from agent.step3_relationships import detect_relationships
from agent.step4_ontology import enrich_with_ontology
from agent.cdm_builder import build_cdm


def run_pipeline(
    file,
    ollama_url: str,
    model: str,
    chroma_path: str,
    temperature: float = 0.1,
    top_k: int = 3,
    on_step_start: Optional[Callable[[int], None]] = None,
    on_step_done: Optional[Callable[[int, str], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Run the full BRD → CDM pipeline.

    Args:
        file: Streamlit UploadedFile or file-like .docx object
        ollama_url: Ollama base URL
        model: Ollama model name
        chroma_path: ChromaDB persist directory
        temperature: LLM temperature
        top_k: Number of ontology results per entity
        on_step_start(step_idx): called when a step begins
        on_step_done(step_idx, detail): called when a step completes
        on_log(msg): called with intermediate log messages

    Returns:
        CDM result dict (entities, relationships, stats, document_title)
    """

    def _start(i):
        if on_step_start:
            on_step_start(i)

    def _done(i, detail=""):
        if on_step_done:
            on_step_done(i, detail)

    def _log(msg):
        if on_log:
            on_log(msg)

    # ── Step 1 — Document parsing ──────────────────────────────────────────
    _start(0)
    _log("Reading .docx file…")
    parsed = parse_docx(file)
    char_count = len(parsed["full_text"])
    section_count = len(parsed["sections"])
    _done(0, f"{section_count} sections, {char_count:,} chars")

    brd_text = parsed["full_text"]

    # ── Step 2 — Entity extraction ─────────────────────────────────────────
    _start(1)
    _log(f"Sending {min(len(brd_text), 6000):,} chars to {model}…")
    entities = extract_entities(
        brd_text=brd_text,
        ollama_url=ollama_url,
        model=model,
        temperature=temperature,
    )
    _done(1, f"{len(entities)} entities found")

    if not entities:
        raise ValueError(
            "No entities were extracted. The model may not have returned valid JSON, "
            "or the BRD text is too short / poorly structured. "
            "Try a larger model or check Ollama is running."
        )

    # ── Step 3 — Relationship detection ───────────────────────────────────
    _start(2)
    _log(f"Detecting relationships among {len(entities)} entities…")
    relationships = detect_relationships(
        entities=entities,
        brd_text=brd_text,
        ollama_url=ollama_url,
        model=model,
        temperature=temperature,
    )
    _done(2, f"{len(relationships)} relationships detected")

    # ── Step 4 — Ontology enrichment ───────────────────────────────────────
    _start(3)
    _log("Querying ChromaDB for ontology matches…")
    entities, relationships = enrich_with_ontology(
        entities=entities,
        relationships=relationships,
        chroma_path=chroma_path,
        top_k=top_k,
    )
    matched = sum(
        1 for e in entities
        if e.get("ontology_matches") and e["ontology_matches"] != ["(ontology not seeded)"]
    )
    _done(3, f"{matched}/{len(entities)} entities matched")

    # ── Step 5 — CDM generation ────────────────────────────────────────────
    _start(4)
    _log("Assembling Conceptual Data Model…")
    cdm = build_cdm(
        parsed_doc=parsed,
        entities=entities,
        relationships=relationships,
    )
    _done(4, f"{cdm['stats']['entity_count']} entities, {cdm['stats']['relationship_count']} relationships")

    return cdm
