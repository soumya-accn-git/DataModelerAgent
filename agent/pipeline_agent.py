"""
Agent pipeline orchestrator — 7 steps.
Step 1  — Document parsing
Step 1b — Dynamic ontology builder (OWL/SHACL from BRD)
Step 2  — Entity extraction  (uses updated SKILL.md)
Step 3  — Relationship detection
Step 4  — Ontology enrichment (ChromaDB)
Step 4b — OWL/SHACL rules engine
Step 5  — CDM generation
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from typing import Callable, Optional
from agent.step1_parser          import parse_docx
from agent.step1b_ontology_builder import build_ontology_from_brd
from agent.step2_entities         import extract_entities
from agent.step3_relationships     import detect_relationships
from agent.step4_ontology          import enrich_with_ontology
from agent.step4b_owl_rules        import apply_owl_rules
from agent.cdm_builder             import build_cdm

STEPS = [
    "Document parsing",
    "Ontology building",
    "Entity extraction",
    "Relationship detection",
    "Ontology enrichment",
    "OWL/SHACL rules",
    "CDM generation",
]

def run_pipeline(
    file,
    ollama_url: str,
    model: str,
    chroma_path: str,
    temperature: float = 0.1,
    top_k: int = 3,
    on_step_start: Optional[Callable[[int], None]] = None,
    on_step_done:  Optional[Callable[[int, str], None]] = None,
    on_log:        Optional[Callable[[str], None]] = None,
) -> dict:

    def _start(i):
        if on_step_start: on_step_start(i)

    def _done(i, detail=""):
        if on_step_done: on_step_done(i, detail)

    def _log(msg):
        if on_log: on_log(msg)

    # ── Step 1 — Document parsing ──────────────────────────────────────────
    _start(0)
    _log("Reading and cleaning .docx file…")
    parsed = parse_docx(file)
    _done(0, f"{len(parsed['sections'])} sections, {len(parsed['full_text']):,} chars")
    brd_text = parsed["full_text"]

    # ── Step 1b — Dynamic ontology builder ────────────────────────────────
    _start(1)
    _log("Analysing BRD to build domain ontology and SHACL shapes…")
    domain = build_ontology_from_brd(
        brd_text=brd_text,
        ollama_url=ollama_url,
        model=model,
        temperature=temperature,
        on_log=_log,
    )
    domain_name = domain.get("_domain_name", "Unknown")
    dim_count   = len(domain.get("dimension_concepts", []))
    fact_count  = len(domain.get("fact_concepts", []))
    _done(1,
        f"Domain: {domain_name} — "
        f"{dim_count} dims, {fact_count} facts identified"
    )

    # ── Step 2 — Entity extraction ─────────────────────────────────────────
    _start(2)
    _log(f"Extracting entities using updated SKILL.md guardrails…")
    entities = extract_entities(
        brd_text=brd_text,
        ollama_url=ollama_url,
        model=model,
        temperature=temperature,
    )
    _done(2, f"{len(entities)} entities found")
    if not entities:
        raise ValueError(
            "No entities extracted. Check Ollama is running and the BRD has content."
        )

    # ── Step 3 — Relationship detection ───────────────────────────────────
    _start(3)
    _log(f"Detecting relationships among {len(entities)} entities…")
    relationships = detect_relationships(
        entities=entities,
        brd_text=brd_text,
        ollama_url=ollama_url,
        model=model,
        temperature=temperature,
    )
    _done(3, f"{len(relationships)} relationships detected")

    # ── Step 4 — Ontology enrichment (ChromaDB) ────────────────────────────
    _start(4)
    _log("Querying ChromaDB for ontology matches…")
    entities, relationships = enrich_with_ontology(
        entities=entities,
        relationships=relationships,
        chroma_path=chroma_path,
        top_k=top_k,
    )
    matched = sum(
        1 for e in entities
        if e.get("ontology_matches") and
           e["ontology_matches"] != ["(ontology not seeded)"]
    )
    _done(4, f"{matched}/{len(entities)} entities matched")

    # ── Step 4b — OWL/SHACL rules ─────────────────────────────────────────
    _start(5)
    _log("Applying OWL Rules R1–R6 and SHACL validation…")
    entities, relationships, inferred_entities, violations = apply_owl_rules(
        entities=entities,
        relationships=relationships,
        on_log=_log,
    )
    _done(5,
        f"{len(inferred_entities)} inferred, "
        f"{len(violations)} SHACL issues"
    )

    # ── Step 5 — CDM generation ────────────────────────────────────────────
    _start(6)
    _log("Assembling Conceptual Data Model…")
    cdm = build_cdm(
        parsed_doc=parsed,
        entities=entities,
        relationships=relationships,
    )
    cdm["inferred_entities"] = inferred_entities
    cdm["shacl_violations"]  = violations
    cdm["domain"]            = {
        "name":        domain_name,
        "description": domain.get("domain_description", ""),
        "owl_file":    os.path.basename(domain.get("_owl_path", "")),
        "shacl_file":  os.path.basename(domain.get("_shacl_path", "")),
        "dimensions":  [d.get("name") for d in domain.get("dimension_concepts", [])],
        "facts":       [f.get("name") for f in domain.get("fact_concepts", [])],
        "key_metrics": domain.get("key_metrics", []),
        "filters":     domain.get("filters_and_prompts", []),
    }
    _done(6,
        f"{cdm['stats']['entity_count']} entities, "
        f"{cdm['stats']['relationship_count']} relationships"
    )

    return cdm
