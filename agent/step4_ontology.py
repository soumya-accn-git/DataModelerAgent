"""
Step 4 — Ontology enrichment
Queries ChromaDB to find matching ontology concepts for each entity and relationship.
Uses sentence-level embedding similarity (ChromaDB default: all-MiniLM-L6-v2).
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import chromadb
from chromadb.utils import embedding_functions


COLLECTION_NAME = "ontology_concepts"


def _get_embedding_function():
    """
    Return the best available embedding function.
    Tries in order:
      1. ONNXMiniLM (fast, no torchvision needed)
      2. DefaultEmbeddingFunction (requires sentence-transformers + torchvision)
      3. None (fallback — ChromaDB uses its own internal embedder)
    """
    try:
        return embedding_functions.ONNXMiniLM_L6_V2()
    except Exception:
        pass
    try:
        return embedding_functions.DefaultEmbeddingFunction()
    except Exception:
        pass
    return None


def _get_collection(chroma_path: str):
    client = chromadb.PersistentClient(path=chroma_path)
    ef = _get_embedding_function()
    try:
        if ef:
            collection = client.get_collection(
                name=COLLECTION_NAME,
                embedding_function=ef,
            )
        else:
            collection = client.get_collection(name=COLLECTION_NAME)
        return collection
    except Exception:
        return None


def enrich_with_ontology(
    entities: list[dict],
    relationships: list[dict],
    chroma_path: str,
    top_k: int = 3,
) -> tuple[list[dict], list[dict]]:
    """
    For each entity, query ChromaDB for the top-k matching ontology concepts.
    For each relationship, query ChromaDB for the best matching property type.

    Returns updated (entities, relationships) lists.
    """
    collection = _get_collection(chroma_path)

    if collection is None or collection.count() == 0:
        # Ontology not seeded — return as-is with a warning flag
        for e in entities:
            e["ontology_matches"] = ["(ontology not seeded)"]
        for r in relationships:
            r["ontology_type"] = ""
        return entities, relationships

    # Enrich entities
    for entity in entities:
        query_text = f"{entity['name']}: {entity['description']}"
        try:
            results = collection.query(
                query_texts=[query_text],
                n_results=min(top_k, collection.count()),
                include=["documents", "metadatas", "distances"],
            )
            matches = []
            if results and results["documents"]:
                for doc, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                ):
                    concept = meta.get("label", doc[:60])
                    score = round(1 - dist, 3)  # cosine similarity approx
                    if score > 0.3:
                        matches.append(f"{concept} ({score})")
            entity["ontology_matches"] = matches if matches else ["(no match)"]
        except Exception as e:
            entity["ontology_matches"] = [f"(error: {e})"]

    # Enrich relationships
    for rel in relationships:
        query_text = (
            f"{rel['from_entity']} {rel['label']} {rel['to_entity']}: "
            f"{rel['description']}"
        )
        try:
            results = collection.query(
                query_texts=[query_text],
                n_results=1,
                where={"concept_type": "property"},
                include=["documents", "metadatas"],
            )
            if results and results["metadatas"] and results["metadatas"][0]:
                meta = results["metadatas"][0][0]
                rel["ontology_type"] = meta.get("label", "")
        except Exception:
            # where filter may fail if no property concepts exist — skip silently
            rel["ontology_type"] = ""

    return entities, relationships
