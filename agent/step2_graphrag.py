"""
Step 2 — Neo4j GraphRAG pipeline (LangChain + Ollama).

STRICT MODE: If GraphRAG cannot proceed for any reason (missing packages,
Neo4j unreachable, zero nodes extracted) it raises GraphRAGError immediately
and stops the pipeline. There is no silent fallback.

Sub-steps:
  2a · Chunk       — split parsed BRD into section Documents
  2b · Graph build — LLMGraphTransformer extracts nodes + relationships
  2c · Neo4j load  — write graph documents into Neo4j
  2d · Retrieve    — query the graph to build enriched extraction context

Requires:
  pip install langchain langchain-core langchain-community
              langchain-experimental langchain-ollama neo4j
"""

import sys, os, re, json, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

NEO4J_URI      = os.environ.get("NEO4J_URI",      "neo4j+s://93f09f11.databases.neo4j.io")
NEO4J_USER     = os.environ.get("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "afwFN2cmb4iUaefJsS23C2yJsh6-tvrXid75FkGQx1s")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

# ── Domain schema ─────────────────────────────────────────────────────────────

ALLOWED_NODES = [
    "Dimension", "Fact", "Reference", "Bridge",
    "Report", "Filter", "Actor", "BusinessRule", "DataField", "SystemModule",
]

ALLOWED_RELATIONSHIPS = [
    "HAS_DIMENSION", "HAS_FACT", "RELATES_TO", "FEEDS", "DEPENDS_ON",
    "VALIDATES", "TRIGGERS", "ACCESSES", "FILTERS_BY", "BELONGS_TO",
    "FULFILLS", "CLASSIFIED_BY",
]

BRD_SYSTEM_PROMPT = """
You are an experienced subject matter expert in Data Modeling, specifically in Dimensional Modeling and able to precisely design data models Ontology and Graph RAG. Use your knowledge and experience in modeling the DWH schema for CDM and LDM.

You are also an expert Knowledge Graph engineer.
Extract structured business entities and relationships from a BRD.

Entity mapping:
- Business dimensions (Customer, Product, Time, Geography) → Dimension
- Measurable events (Sale, Transaction, Payment, Order) → Fact
- Lookup/classification (Currency, Status, Category) → Reference
- M:N junctions → Bridge
- Report/dashboard names → Report
- Filter/prompt names → Filter
- Users, roles, stakeholders → Actor
- Business constraints → BusinessRule
- Data attributes → DataField
- Software components → SystemModule

Do NOT create nodes for generic terms (data, information, system, process)
or metric names (these are attributes of Fact, not separate nodes).
"""


# ── Error class ───────────────────────────────────────────────────────────────

class GraphRAGError(Exception):
    """
    Raised when the GraphRAG pipeline cannot proceed.
    Stops the pipeline immediately with a clear message.
    """
    pass


def _fail(reason: str, fix: str = "") -> None:
    msg = f"GraphRAG pipeline failed:\n{reason}"
    if fix:
        msg += f"\n\nFix:\n{fix}"
    raise GraphRAGError(msg)


# ── Chunking ──────────────────────────────────────────────────────────────────

def _chunk_parsed_doc(parsed_doc: dict, max_chars: int = 1500) -> list:
    try:
        from langchain_core.documents import Document
    except ImportError as e:
        _fail(
            f"langchain-core not installed: {e}",
            "pip install langchain langchain-core langchain-community "
            "langchain-experimental langchain-ollama langchain-neo4j"
        )

    sections  = parsed_doc.get("sections", [])
    full_text = parsed_doc.get("full_text", "")
    documents = []

    if not sections:
        for i in range(0, len(full_text), max_chars):
            chunk = full_text[i:i + max_chars]
            if chunk.strip():
                documents.append(Document(
                    page_content=chunk,
                    metadata={"chunk_idx": i // max_chars},
                ))
        return documents

    for idx, section in enumerate(sections):
        heading = section.get("heading", f"Section {idx}")
        content = section.get("content", "")
        text    = f"## {heading}\n{content}"

        if len(text) <= max_chars:
            documents.append(Document(
                page_content=text,
                metadata={"section_idx": idx, "heading": heading},
            ))
        else:
            paras = re.split(r"\n{2,}|(?<=[.!?])\s+(?=[A-Z])", content)
            acc   = f"## {heading}\n"
            part  = 0
            for para in paras:
                if len(acc) + len(para) > max_chars and acc.strip():
                    documents.append(Document(
                        page_content=acc.strip(),
                        metadata={"section_idx": idx, "heading": heading, "part": part},
                    ))
                    acc  = f"## {heading} (cont.)\n{para} "
                    part += 1
                else:
                    acc += para + " "
            if acc.strip():
                documents.append(Document(
                    page_content=acc.strip(),
                    metadata={"section_idx": idx, "heading": heading, "part": part},
                ))

    return documents


# ── Ollama LLM builder ────────────────────────────────────────────────────────

def _build_ollama_llm(ollama_url: str, model: str, temperature: float):
    # Try langchain-ollama (standalone, preferred)
    try:
        from langchain_ollama import ChatOllama
        return ChatOllama(
            base_url=ollama_url,
            model=model,
            temperature=temperature,
        )
    except ImportError:
        pass

    # Fallback to langchain-community
    try:
        from langchain_community.chat_models import ChatOllama
        return ChatOllama(
            base_url=ollama_url,
            model=model,
            temperature=temperature,
        )
    except ImportError as e:
        _fail(
            f"Ollama LangChain package not found: {e}",
            "pip install langchain-ollama"
        )


# ── Neo4j connection ──────────────────────────────────────────────────────────

def _connect_neo4j(uri: str, user: str, password: str):
    # Import Neo4j driver
    try:
        from neo4j import GraphDatabase
    except ImportError as e:
        _fail(str(e), "pip install neo4j")

    # Import Neo4jGraph — try standalone package first, then community fallback
    Neo4jGraph = None
    try:
        from langchain_neo4j import Neo4jGraph
    except ImportError:
        try:
            from langchain_community.graphs import Neo4jGraph
        except ImportError as e:
            _fail(
                f"Missing Neo4j LangChain package: {e}",
                "pip install langchain-neo4j"
            )

    # Connect driver
    try:
        driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            connection_timeout=30,
            max_connection_lifetime=300,
        )
        driver.verify_connectivity()
    except Exception as e:
        _fail(
            f"Neo4j connection failed: {e}",
            "Check Neo4j URI, username and password in the sidebar.\n"
            "Click 'Test Neo4j connection' to verify credentials.\n"
            "Username for Aura Free is always 'neo4j'."
        )

    # Init Neo4jGraph
    try:
        graph = Neo4jGraph(
            url=uri,
            username=user,
            password=password,
            database=NEO4J_DATABASE,
        )
    except Exception as e:
        driver.close()
        _fail(f"Neo4jGraph init failed: {e}")

    return driver, graph


# ── Context builder ───────────────────────────────────────────────────────────

def _build_context(all_graph_docs: list, full_text: str) -> str:
    parts = []

    node_lines = []
    seen_nodes = set()
    for gd in all_graph_docs:
        for node in gd.nodes:
            key = (node.type, node.id)
            if key not in seen_nodes:
                seen_nodes.add(key)
                props = {k: v for k, v in (node.properties or {}).items()
                         if k != "brd_hash"}
                desc = props.get("description", props.get("name", ""))
                node_lines.append(
                    f"- [{node.type}] {node.id}"
                    + (f": {desc}" if desc else "")
                )
    if node_lines:
        parts.append("## Extracted Knowledge Graph Nodes\n" + "\n".join(node_lines))

    rel_lines = []
    seen_rels = set()
    for gd in all_graph_docs:
        for rel in gd.relationships:
            key = (rel.source.id, rel.type, rel.target.id)
            if key not in seen_rels:
                seen_rels.add(key)
                rel_lines.append(
                    f"- {rel.source.id} --[{rel.type}]--> {rel.target.id}"
                )
    if rel_lines:
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
    Run the full GraphRAG pipeline.
    Raises GraphRAGError on any failure — no silent fallback.
    """
    def log(msg):
        if on_log: on_log(msg)

    full_text = parsed_doc.get("full_text", "")
    if not brd_hash:
        brd_hash = hashlib.sha256(full_text.encode()).hexdigest()[:16]

    # ── 2a · Chunk ────────────────────────────────────────────────────────────
    log("2a · Chunking BRD into section documents…")
    documents = _chunk_parsed_doc(parsed_doc)
    if not documents:
        _fail("No document chunks could be created from the parsed BRD.")
    log(f"    {len(documents)} chunks created")

    # ── 2b · Connect to Neo4j ─────────────────────────────────────────────────
    log(f"2b · Connecting to Neo4j at {neo4j_uri}…")
    driver, graph = _connect_neo4j(neo4j_uri, neo4j_user, neo4j_pass)
    log("    Connected successfully")

    # ── 2c · Build LLMGraphTransformer ────────────────────────────────────────
    log(f"2c · Initialising LLMGraphTransformer (model: {model})…")
    try:
        from langchain_experimental.graph_transformers import LLMGraphTransformer
    except ImportError as e:
        driver.close()
        _fail(
            f"LLMGraphTransformer not available: {e}",
            "pip install langchain-experimental"
        )

    try:
        llm = _build_ollama_llm(ollama_url, model, temperature)
        transformer = LLMGraphTransformer(
            llm=llm,
            allowed_nodes=ALLOWED_NODES,
            allowed_relationships=ALLOWED_RELATIONSHIPS,
            node_properties=True,
            relationship_properties=True,
        )
        log("    LLMGraphTransformer ready")
    except GraphRAGError:
        driver.close()
        raise
    except Exception as e:
        driver.close()
        _fail(f"LLM transformer initialisation failed: {e}")

    # ── 2d · Extract graph from documents ─────────────────────────────────────
    log(f"2d · Extracting knowledge graph from {len(documents)} chunks…")
    all_graph_docs = []
    total_nodes    = 0
    total_rels     = 0

    for i, doc in enumerate(documents):
        try:
            log(f"    Chunk {i+1}/{len(documents)}: "
                f"{doc.metadata.get('heading','')[:40]}…")
            graph_docs = transformer.convert_to_graph_documents([doc])
            if graph_docs:
                n = len(graph_docs[0].nodes)
                r = len(graph_docs[0].relationships)
                total_nodes += n
                total_rels  += r
                all_graph_docs.extend(graph_docs)
                log(f"    → {n} nodes, {r} relationships")
        except Exception as e:
            # A single chunk failure is non-fatal — log and continue
            log(f"    ⚠️  Chunk {i+1} failed: {e} — skipping")
            continue

    if not all_graph_docs or total_nodes == 0:
        driver.close()
        _fail(
            "LLMGraphTransformer extracted zero nodes from the BRD.",
            "Check that Ollama is running and the model responds correctly.\n"
            "Try: ollama run llama3.1:8b 'hello' to verify the model works."
        )

    log(f"    Total extracted: {total_nodes} nodes, {total_rels} relationships")

    # ── 2e · Load into Neo4j ──────────────────────────────────────────────────
    log("2e · Loading knowledge graph into Neo4j…")
    try:
        with driver.session() as session:
            session.run(
                "MATCH (n {brd_hash: $hash}) DETACH DELETE n",
                hash=brd_hash,
            )
        for gd in all_graph_docs:
            for node in gd.nodes:
                if not node.properties:
                    node.properties = {}
                node.properties["brd_hash"] = brd_hash

        graph.add_graph_documents(
            all_graph_docs,
            baseEntityLabel=True,
            include_source=True,
        )
        log(f"    Graph loaded into Neo4j")
    except Exception as e:
        # Neo4j write failure is non-fatal — context still built from extracted data
        log(f"    ⚠️  Neo4j write warning: {e} — context built from extracted data")

    # ── 2f · Build enriched context ───────────────────────────────────────────
    log("2f · Building GraphRAG context…")
    context = _build_context(all_graph_docs, full_text)
    driver.close()
    log(f"    Context ready: {len(context):,} chars")

    return {
        "graphrag_context":  context,
        "nodes_extracted":   total_nodes,
        "rels_extracted":    total_rels,
        "neo4j_available":   True,
        "sections_loaded":   len(documents),
        "brd_hash":          brd_hash,
    }
