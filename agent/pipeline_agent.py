"""
Agent pipeline orchestrator — 8 steps.

Step 1   — Document parsing (LlamaParse → Unstructured → python-docx)
Step 1b  — Dynamic ontology builder (OWL/SHACL, cached by BRD hash)
Step 2   — Neo4j GraphRAG pipeline (chunk → embed → graph → retrieve)
Step 3   — Entity extraction (GraphRAG context + SKILL.md guardrails)
Step 4   — Relationship detection (GraphRAG context + LLM)
Step 5   — ChromaDB ontology enrichment
Step 5b  — OWL/SHACL rules engine (R1–R6, filter inference, bridges)
Step 6   — CDM generation (Mermaid, JSON-LD, graph view)
"""

import sys, os, json, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from typing import Callable, Optional
from agent.step1_parser            import parse_docx
from agent.step1b_ontology_builder import build_ontology_from_brd
from agent.step2_graphrag          import run_graphrag_pipeline, GraphRAGError
from agent.result_store            import save_cdm
from config import (
    NEO4J_URI      as _CFG_NEO4J_URI,
    NEO4J_USER     as _CFG_NEO4J_USER,
    NEO4J_PASSWORD as _CFG_NEO4J_PASS,
    NEO4J_DATABASE as _CFG_NEO4J_DB,
)
from agent.step2_entities          import extract_entities
from agent.step3_relationships      import detect_relationships
from agent.step4_ontology           import enrich_with_ontology
from agent.step4b_owl_rules         import apply_owl_rules
from agent.cdm_builder              import build_cdm

GENERATED_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "ontology", "generated"
)
os.makedirs(GENERATED_DIR, exist_ok=True)

STEPS = [
    "Document parsing",
    "Ontology building",
    "GraphRAG pipeline",
    "Entity extraction",
    "Relationship detection",
    "Ontology enrichment",
    "OWL/SHACL rules",
    "CDM generation",
]


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _brd_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def _cache_path(brd_hash: str) -> str:
    return os.path.join(GENERATED_DIR, f"{brd_hash}_domain.json")

def _load_cached_domain(brd_hash: str) -> dict | None:
    path = _cache_path(brd_hash)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def _save_cached_domain(brd_hash: str, domain: dict) -> None:
    try:
        with open(_cache_path(brd_hash), "w", encoding="utf-8") as f:
            json.dump(domain, f, indent=2)
    except Exception as e:
        print(f"[pipeline] Cache save warning: {e}")


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(
    file,
    ollama_url:    str,
    model:         str,
    chroma_path:   str,
    temperature:   float = 0.1,
    top_k:         int   = 3,
    max_chunks:    int   = 4,
    neo4j_uri:     str   = "",
    neo4j_user:    str   = "",
    neo4j_password:str   = "",
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
    _log("Reading BRD — trying LlamaParse → Unstructured → python-docx…")
    parsed = parse_docx(file)
    parser_used = parsed.get("parser_used", "python-docx")
    _done(0, f"{len(parsed['sections'])} sections · parser: {parser_used}")
    brd_text = parsed["full_text"]
    brd_h    = _brd_hash(brd_text)

    # ── Step 1b — Dynamic ontology builder (cached) ────────────────────────
    _start(1)
    cached_domain = _load_cached_domain(brd_h)
    if cached_domain:
        domain = cached_domain
        _log(f"BRD unchanged — reusing cached ontology for '{domain.get('_domain_name','')}'")
        _done(1, f"⚡ Cached — {domain.get('_domain_name','Unknown')}")
    else:
        _log("New BRD — building domain ontology and SHACL shapes…")
        domain = build_ontology_from_brd(
            brd_text=brd_text,
            ollama_url=ollama_url,
            model=model,
            temperature=temperature,
            on_log=_log,
        )
        _save_cached_domain(brd_h, domain)
        _done(1, f"Domain: {domain.get('_domain_name','Unknown')}")

    # ── Step 2 — Neo4j GraphRAG (cached by BRD hash) ─────────────────────
    _start(2)
    neo4j_uri_use  = neo4j_uri  or _CFG_NEO4J_URI
    neo4j_user_use = neo4j_user or _CFG_NEO4J_USER
    neo4j_pass_use = neo4j_password or _CFG_NEO4J_PASS

    # Check GraphRAG cache
    graphrag_cache_path = os.path.join(GENERATED_DIR, f"{brd_h}_graphrag.json")
    cached_graphrag = None
    if os.path.exists(graphrag_cache_path):
        try:
            with open(graphrag_cache_path, "r", encoding="utf-8") as f:
                cached_graphrag = json.load(f)
        except Exception:
            cached_graphrag = None

    if cached_graphrag:
        graphrag_result = cached_graphrag
        nodes_c = graphrag_result.get("nodes_extracted", 0)
        rels_c  = graphrag_result.get("rels_extracted", 0)
        _log("BRD unchanged — reusing cached GraphRAG context")
        _done(2, f"⚡ Cached — {nodes_c} nodes · {rels_c} rels")
    else:
        _log(f"Running GraphRAG pipeline — Neo4j at {neo4j_uri_use}…")
        try:
            graphrag_result = run_graphrag_pipeline(
                parsed_doc=parsed,
                ollama_url=ollama_url,
                model=model,
                temperature=temperature,
                neo4j_uri=neo4j_uri_use,
                neo4j_user=neo4j_user_use,
                neo4j_pass=neo4j_pass_use,
                brd_hash=brd_h,
                on_log=_log,
            )
            # Save full result to cache
            try:
                with open(graphrag_cache_path, "w", encoding="utf-8") as f:
                    json.dump(graphrag_result, f)
                _log(f"GraphRAG result cached → {os.path.basename(graphrag_cache_path)}")
            except Exception as ce:
                _log(f"Cache save warning: {ce}")

            nodes_c = graphrag_result.get("nodes_extracted", 0)
            rels_c  = graphrag_result.get("rels_extracted", 0)
            neo4j_ok = graphrag_result.get("neo4j_available", False)
            if neo4j_ok:
                _done(2, f"Neo4j ✅ {nodes_c} nodes · {rels_c} rels")
            else:
                _done(2, "Neo4j ⚠️ fallback mode")

        except GraphRAGError as e:
            raise RuntimeError(
                f"⛔ GraphRAG pipeline stopped:\n\n{e}\n\n"
                f"The pipeline cannot continue without a working GraphRAG setup.\n"
                f"Check the sidebar — use 'Test Neo4j connection' to verify credentials."
            ) from e

    graphrag_context = graphrag_result["graphrag_context"]
    neo4j_available  = graphrag_result.get("neo4j_available", False)
    sections_loaded  = graphrag_result.get("sections_loaded", 0)
    nodes_extracted  = graphrag_result.get("nodes_extracted", 0)
    rels_extracted   = graphrag_result.get("rels_extracted", 0)

    # ── Step 3 — Entity extraction ─────────────────────────────────────────
    _start(3)
    sections = parsed.get("sections", [])
    _log(f"Extracting entities — two-pass (full doc scan + GraphRAG enrichment)…")
    entities = extract_entities(
        brd_text=brd_text,
        ollama_url=ollama_url,
        model=model,
        temperature=temperature,
        graphrag_context=graphrag_context,
        sections=sections,
        on_log=_log,
        max_chunks=max_chunks,
    )
    _done(3, f"{len(entities)} entities found")
    if not entities:
        raise ValueError(
            "No entities extracted. Check Ollama is running and the BRD has content."
        )

    # ── Step 4 — Relationship detection ───────────────────────────────────
    _start(4)
    _log("Detecting relationships — two-pass (full doc + GraphRAG)…")
    relationships = detect_relationships(
        entities=entities,
        brd_text=brd_text,
        ollama_url=ollama_url,
        model=model,
        temperature=temperature,
        graphrag_context=graphrag_context,
        on_log=_log,
    )
    _done(4, f"{len(relationships)} relationships detected")

    # ── Step 5 — ChromaDB ontology enrichment ─────────────────────────────
    _start(5)
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
    _done(5, f"{matched}/{len(entities)} entities matched")

    # ── Step 5b — OWL/SHACL rules ─────────────────────────────────────────
    _start(6)
    _log("Applying OWL Rules R1–R6 and SHACL validation…")
    entities, relationships, inferred_entities, violations = apply_owl_rules(
        entities=entities,
        relationships=relationships,
        on_log=_log,
    )
    _done(6, f"{len(inferred_entities)} inferred · {len(violations)} SHACL issues")

    # ── Step 6 — CDM generation ────────────────────────────────────────────
    _start(7)
    _log("Assembling Conceptual Data Model…")
    cdm = build_cdm(
        parsed_doc=parsed,
        entities=entities,
        relationships=relationships,
    )
    cdm["inferred_entities"] = inferred_entities
    cdm["shacl_violations"]  = violations
    cdm["domain"]            = {
        "name":          domain.get("_domain_name", "Unknown"),
        "description":   domain.get("domain_description", ""),
        "owl_file":      os.path.basename(domain.get("_owl_path", "")),
        "shacl_file":    os.path.basename(domain.get("_shacl_path", "")),
        "dimensions":    [d.get("name") for d in domain.get("dimension_concepts", [])],
        "facts":         [f.get("name") for f in domain.get("fact_concepts", [])],
        "key_metrics":   domain.get("key_metrics", []),
        "filters":       domain.get("filters_and_prompts", []),
        "from_cache":    cached_domain is not None,
    }
    cdm["graphrag"] = {
        "neo4j_available":  neo4j_available,
        "sections_loaded":  sections_loaded,
        "nodes_extracted":  nodes_extracted,
        "rels_extracted":   rels_extracted,
        "parser_used":      parser_used,
        "context_chars":    len(graphrag_context),
    }
    _done(7,
        f"{cdm['stats']['entity_count']} entities · "
        f"{cdm['stats']['relationship_count']} relationships"
    )

    # Persist CDM to disk keyed by BRD hash
    cdm["_brd_hash"] = brd_h
    cdm["_brd_text"] = brd_text   # stored for LDM-only re-runs
    try:
        cdm_path = save_cdm(brd_h, cdm)
        _log(f"CDM saved → {os.path.basename(cdm_path)}")
    except Exception as e:
        _log(f"CDM save warning: {e}")

    return cdm
