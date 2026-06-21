"""
Step 2 — GraphRAG pipeline (direct Ollama extraction + Neo4j persistence).

Replaces LLMGraphTransformer with a single direct LLM call over the full BRD
text, using a domain-specific prompt.  This solves four problems with the old
approach:
  - LLMGraphTransformer is designed for frontier models; it performs poorly with
    small local models (llama3.1:8b).
  - The custom BRD_SYSTEM_PROMPT was defined but never delivered to the LLM.
  - Chunking caused boundary-split entity loss and multiplied LLM calls N×.
  - ALLOWED_NODES made the prompt ultra-restrictive, suppressing recall.

New flow:
  2a · Extract — single Ollama call, full BRD text, domain-specific prompt
  2b · Persist — write nodes + rels to Neo4j via raw Cypher (optional, non-blocking)
  2c · Context — build enriched graphrag_context string for downstream steps
"""

import sys, os, re, json, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.tools.ollama_client import chat, extract_json

NEO4J_URI      = os.environ.get("NEO4J_URI",      "")
NEO4J_USER     = os.environ.get("NEO4J_USERNAME",  "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD",  "")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE",  "neo4j")

# ── Node / relationship vocabulary ────────────────────────────────────────────

NODE_TYPES = [
    "Dimension", "Fact", "Reference", "Bridge",
    "Actor", "BusinessRule", "DataField", "SystemModule",
]

RELATIONSHIP_TYPES = [
    "HAS_DIMENSION", "HAS_FACT", "RELATES_TO", "FEEDS", "DEPENDS_ON",
    "VALIDATES", "TRIGGERS", "ACCESSES", "FILTERS_BY", "BELONGS_TO",
    "FULFILLS", "CLASSIFIED_BY",
]

# ── Extraction prompts ────────────────────────────────────────────────────────

_SYSTEM = """You are an expert data modeling knowledge graph engineer specialising in \
dimensional modeling (CDM / LDM / DWH schema design).

Read the entire Business Requirements Document and extract ALL business entities \
and ALL relationships between them.

Be exhaustive — a typical BRD yields 20-50 nodes and 30-80 relationships.

Node types:
  Dimension   — descriptive axis (Customer, Product, Time, Geography, Store)
  Fact        — measurable event or transaction (Sales, Orders, Inventory, Markdowns)
  Reference   — lookup / code table (Currency, Status, Category, Country)
  Bridge      — M:N junction between dimensions
  Actor       — user, role, or stakeholder mentioned in the BRD
  BusinessRule — explicit constraint or calculation rule
  DataField   — a named data attribute or measure mentioned by name
  SystemModule — a named software component or integration system

Relationship types (use exactly these strings):
  HAS_DIMENSION  RELATES_TO  FEEDS       DEPENDS_ON  VALIDATES
  HAS_FACT       TRIGGERS    ACCESSES    FILTERS_BY  BELONGS_TO
  FULFILLS       CLASSIFIED_BY

Rules:
- Node id must be PascalCase, no spaces (e.g. SalesFact, ProductDimension)
- Extract EVERY distinct named concept — do not merge or skip any
- Filters and prompts imply Dimension nodes — extract the underlying dimension
- Report and dashboard names are NOT nodes — extract the entities they report on
- Return ONLY the JSON object, no explanation, no markdown fences

Return format:
{
  "nodes": [
    {"id": "PascalCaseName", "type": "NodeType", "description": "one sentence"}
  ],
  "relationships": [
    {"source": "SourceId", "type": "REL_TYPE", "target": "TargetId"}
  ]
}"""

_USER = """Extract the complete knowledge graph from this BRD.

BRD TEXT:
---
{brd_text}
---

JSON:"""


# ── Error class ───────────────────────────────────────────────────────────────

class GraphRAGError(Exception):
    pass


def _fail(reason: str, fix: str = "") -> None:
    msg = f"GraphRAG pipeline failed:\n{reason}"
    if fix:
        msg += f"\n\nFix:\n{fix}"
    raise GraphRAGError(msg)


# ── Direct LLM extraction ─────────────────────────────────────────────────────

def _extract_graph(
    full_text: str,
    ollama_url: str,
    model: str,
    temperature: float,
    log,
) -> tuple[list[dict], list[dict]]:
    """
    Single Ollama call over the full BRD text.
    Returns (graph_nodes, graph_rels) as plain dicts.
    Falls back to an empty graph rather than raising — extraction failures
    are non-fatal; downstream steps still run with LLM Pass 1 entities.
    """
    # num_ctx: BRDs are typically 3–8K tokens; 16384 covers even large BRDs
    #          without the 32K KV-cache allocation used by entity extraction.
    # num_predict: JSON output for 30–50 nodes + 50–80 rels ≈ 1500–2500 tokens;
    #              3000 gives headroom without padding with unused capacity.
    # Both cuts reduce Ollama's per-token generation time significantly.
    input_tokens  = max(8192, min(16384, (len(full_text) // 3) + 1024))
    output_tokens = 3000

    log(f"2a · Extracting knowledge graph — single call, {len(full_text):,} chars "
        f"(ctx={input_tokens}, predict={output_tokens})…")
    try:
        raw = chat(
            base_url=ollama_url,
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": _USER.format(brd_text=full_text)},
            ],
            temperature=temperature,
            format="json",
            num_ctx=input_tokens,
            num_predict=output_tokens,
        )
        data = extract_json(raw)
    except Exception as e:
        log(f"    ⚠️  LLM extraction failed: {e} — graph will be empty")
        return [], []

    if not isinstance(data, dict):
        log("    ⚠️  Unexpected response format — graph will be empty")
        return [], []

    raw_nodes = data.get("nodes", [])
    raw_rels  = data.get("relationships", [])

    # ── Validate and normalise nodes ──────────────────────────────────────────
    valid_types = set(NODE_TYPES)
    seen_ids    = set()
    nodes: list[dict] = []
    for n in raw_nodes:
        if not isinstance(n, dict):
            continue
        node_id   = str(n.get("id", "")).strip()
        node_type = str(n.get("type", "")).strip()
        if not node_id or not re.match(r'^[A-Z][A-Za-z0-9]+$', node_id):
            continue
        if node_id.lower() in seen_ids:
            continue
        if node_type not in valid_types:
            node_type = "Dimension"   # safe default rather than dropping
        seen_ids.add(node_id.lower())
        nodes.append({
            "id":          node_id,
            "type":        node_type,
            "properties":  {"description": str(n.get("description", ""))},
        })

    # ── Validate and normalise relationships ──────────────────────────────────
    valid_ids  = {n["id"] for n in nodes}
    seen_rels  = set()
    rels: list[dict] = []
    for r in raw_rels:
        if not isinstance(r, dict):
            continue
        src  = str(r.get("source", "")).strip()
        tgt  = str(r.get("target", "")).strip()
        rtype = str(r.get("type", "RELATES_TO")).strip().upper()
        if src not in valid_ids or tgt not in valid_ids:
            continue
        if rtype not in RELATIONSHIP_TYPES:
            rtype = "RELATES_TO"
        key = (src, rtype, tgt)
        if key in seen_rels:
            continue
        seen_rels.add(key)
        rels.append({"source": src, "type": rtype, "target": tgt})

    log(f"    Extracted: {len(nodes)} nodes, {len(rels)} relationships")
    return nodes, rels


# ── Neo4j persistence (optional, non-blocking) ────────────────────────────────

def _persist_to_neo4j(
    nodes: list[dict],
    rels:  list[dict],
    brd_hash: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
    log,
) -> bool:
    """
    Write extracted nodes and relationships to Neo4j via raw Cypher.
    Returns True on success, False on any failure (non-fatal).
    No LangChain dependency — only the neo4j Python driver is needed.
    """
    if not neo4j_uri or not neo4j_user or not neo4j_pass:
        log("2b · Neo4j skipped — credentials not configured")
        return False

    try:
        from neo4j import GraphDatabase
    except ImportError:
        log("2b · Neo4j skipped — driver not installed (pip install neo4j)")
        return False

    try:
        log(f"2b · Connecting to Neo4j at {neo4j_uri}…")
        driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_pass),
            connection_timeout=5,
        )
        driver.verify_connectivity()
        log("    Connected")
    except Exception as e:
        log(f"    ⚠️  Neo4j connection failed: {e} — skipping persistence")
        return False

    try:
        with driver.session(database=NEO4J_DATABASE or "neo4j") as session:
            # Clear previous graph for this BRD
            session.run(
                "MATCH (n:BRDEntity {brd_hash: $h}) DETACH DELETE n",
                h=brd_hash,
            )
            # Write nodes
            for node in nodes:
                session.run(
                    """
                    MERGE (n:BRDEntity {id: $id, brd_hash: $h})
                    SET n.type = $type, n.description = $desc
                    """,
                    id=node["id"], h=brd_hash,
                    type=node["type"],
                    desc=node["properties"].get("description", ""),
                )
            # Write relationships
            for rel in rels:
                session.run(
                    """
                    MATCH (a:BRDEntity {id: $src, brd_hash: $h}),
                          (b:BRDEntity {id: $tgt, brd_hash: $h})
                    MERGE (a)-[r:GRAPH_REL {type: $rtype}]->(b)
                    """,
                    src=rel["source"], tgt=rel["target"],
                    rtype=rel["type"], h=brd_hash,
                )
        log(f"    Written {len(nodes)} nodes + {len(rels)} rels to Neo4j")
        return True
    except Exception as e:
        log(f"    ⚠️  Neo4j write warning: {e}")
        return False
    finally:
        driver.close()


# ── Context builder ───────────────────────────────────────────────────────────

def _build_context(
    nodes: list[dict],
    rels:  list[dict],
    full_text: str,
) -> str:
    parts = []

    if nodes:
        node_lines = [
            f"- [{n['type']}] {n['id']}"
            + (f": {n['properties'].get('description','')}"
               if n['properties'].get('description') else "")
            for n in nodes
        ]
        parts.append("## Extracted Knowledge Graph Nodes\n" + "\n".join(node_lines))

    if rels:
        rel_lines = [
            f"- {r['source']} --[{r['type']}]--> {r['target']}"
            for r in rels
        ]
        parts.append("## Extracted Knowledge Graph Relationships\n" + "\n".join(rel_lines))

    parts.append("## Original BRD Text\n" + full_text[:3000])
    return "\n\n".join(parts)


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_graphrag_pipeline(
    parsed_doc:    dict,
    ollama_url:    str   = "http://localhost:11434",
    model:         str   = "llama3.1:8b",
    temperature:   float = 0.1,
    neo4j_uri:     str   = NEO4J_URI,
    neo4j_user:    str   = NEO4J_USER,
    neo4j_pass:    str   = NEO4J_PASSWORD,
    brd_hash:      str   = "",
    on_log               = None,
) -> dict:
    """
    Run the GraphRAG pipeline.

    Extraction is a single direct Ollama call — no LLMGraphTransformer,
    no chunking, no LangChain dependency for extraction.

    Neo4j persistence is optional and non-blocking: if Neo4j is unreachable
    the pipeline continues and returns the full graph from the LLM call.
    """
    def log(msg):
        if on_log: on_log(msg)

    full_text = parsed_doc.get("full_text", "")
    sections  = parsed_doc.get("sections", [])
    if not brd_hash:
        brd_hash = hashlib.sha256(full_text.encode()).hexdigest()[:16]

    if not full_text.strip():
        _fail("BRD full_text is empty — nothing to extract.")

    # ── 2a · Extract knowledge graph (single LLM call) ────────────────────────
    graph_nodes, graph_rels = _extract_graph(
        full_text=full_text,
        ollama_url=ollama_url,
        model=model,
        temperature=temperature,
        log=log,
    )

    if not graph_nodes:
        _fail(
            "Knowledge graph extraction returned zero nodes.",
            "Check that Ollama is running and responding:\n"
            "  ollama run llama3.1:8b 'hello'\n"
            "If Ollama is running, the BRD may be empty or unreadable.",
        )

    # ── 2b · Persist to Neo4j (optional) ─────────────────────────────────────
    neo4j_ok = _persist_to_neo4j(
        nodes=graph_nodes, rels=graph_rels,
        brd_hash=brd_hash,
        neo4j_uri=neo4j_uri, neo4j_user=neo4j_user, neo4j_pass=neo4j_pass,
        log=log,
    )

    # ── 2c · Build enriched context string ────────────────────────────────────
    log("2c · Building GraphRAG context…")
    context = _build_context(graph_nodes, graph_rels, full_text)
    log(f"    Context ready: {len(context):,} chars")

    return {
        "graphrag_context": context,
        "graph_nodes":      graph_nodes,
        "graph_rels":       graph_rels,
        "nodes_extracted":  len(graph_nodes),
        "rels_extracted":   len(graph_rels),
        "neo4j_available":  neo4j_ok,
        "sections_loaded":  len(sections),
        "brd_hash":         brd_hash,
    }
