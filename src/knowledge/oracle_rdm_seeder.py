"""
Oracle Retail Data Model — Full Seeder with BRD-domain filtering at query time.

Seeds ALL 927 logical entities + 439 physical tables into ChromaDB.
Each chunk is tagged with brd_domain=Y/N metadata.
Queries filter to BRD-relevant results via ChromaDB where clause.

Collections:
  oracle_rdm_ldm  — 927 logical entity chunks  (Chapter 2)
  oracle_rdm_pdm  — 439 physical table chunks  (Chapter 3)

Metadata on every chunk:
  entity_type   — Reference / Lookup / Base / Derived / Aggregate
  subject_areas — pipe-separated Oracle subject area list
  brd_domain    — Y = in scope for Merchandising Sales & Profit BRD
  name          — entity/table name

BRD domain scope subject areas:
  Retail Sales, Item, SKU Item, Organization Business Unit, Calendar,
  Retail Inventory, Vendor, Vendor Item, Financial Ledger,
  Promotion/Campaign, Cost, Supply Chain, Geography, Inventory
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

COLLECTION_LDM = "oracle_rdm_ldm"
COLLECTION_PDM = "oracle_rdm_pdm"

# ── BRD domain scope ──────────────────────────────────────────────────────────
BRD_SUBJECT_AREAS = {
    "Retail Sales", "Item", "SKU Item", "Organization Business Unit",
    "Calendar", "Time", "Retail Inventory", "Vendor", "Vendor Item",
    "Financial Ledger", "Promotion / Campaign", "Cost", "Supply Chain",
    "Invoice", "Geography", "Inventory",
}

BRD_TABLE_PREFIXES = (
    "DWR_ITEM","DWR_SKU","DWR_ORG","DWR_LOC","DWR_DAY","DWR_BSNS",
    "DWR_CLNDR","DWR_SEASON","DWR_ITEM_SEASON","DWR_VNDR","DWR_PRMO",
    "DWR_RTL","DWR_CURR","DWR_BRND","DWR_ITEM_DIV","DWR_ITEM_GRP",
    "DWR_ITEM_DEPT","DWR_ITEM_CLASS","DWR_ITEM_SBC","DWR_INV",
    "DWD_RTL","DWD_MKDN","DWD_INV","DWD_FNCL","DWD_VNDR","DWD_PRMO",
    "DWA_RTL","DWA_INV","DWA_MKDN",
)

BRD_ENTITY_KEYWORDS = {
    "ITEM","SKU","PRODUCT","SEASON","MARKDOWN","SALES","RETAIL",
    "STORE","LOCATION","ORGANI","CALENDAR","DAY","WEEK","MONTH",
    "YEAR","VENDOR","SUPPLIER","COST","PRICE","CURRENCY","PROFIT",
    "INVENTORY","STOCK","DEPARTMENT","CLASS","SUBCLASS","DIVISION",
    "PROMOTION","CAMPAIGN","BRAND","TAX","VAT",
}


def _entity_in_brd(entity: dict) -> bool:
    if set(entity.get("subject_areas", [])) & BRD_SUBJECT_AREAS:
        return True
    name = entity.get("name", "").upper()
    return any(kw in name for kw in BRD_ENTITY_KEYWORDS)


def _table_in_brd(table: dict) -> bool:
    name = table.get("table_name", "")
    return any(name.startswith(p) for p in BRD_TABLE_PREFIXES)


def _get_ef():
    from chromadb.utils import embedding_functions
    try:
        return embedding_functions.ONNXMiniLM_L6_V2()
    except Exception:
        return embedding_functions.DefaultEmbeddingFunction()


def _entity_text(e: dict, brd: str) -> str:
    subjects = ", ".join(e.get("subject_areas", [])) or "Unclassified"
    scope    = "In scope — Merchandising Sales & Profit" if brd == "Y" else "Out of scope"
    return (
        f"Oracle RDM Logical Entity: {e['name']}\n"
        f"Type: {e.get('type','')}\n"
        f"Subject Areas: {subjects}\n"
        f"BRD Domain: {scope}\n"
        f"Description: {e.get('description','')}"
    )


def _table_text(t: dict, brd: str) -> str:
    ttype = t.get("table_type", t.get("table_name","")[:3])
    labels = {"DWR":"Reference/Dimension","DWD":"Derived/Fact",
              "DWA":"Aggregate","DWB":"Base Transaction",
              "DWL":"Lookup","DWC":"Control"}
    scope = "In scope — Merchandising Sales & Profit" if brd == "Y" else "Out of scope"
    return (
        f"Oracle RDM Physical Table: {t['table_name']}\n"
        f"Type: {ttype} ({labels.get(ttype, ttype)})\n"
        f"BRD Domain: {scope}\n"
        f"Description: {t.get('description','')}"
    )


def seed_oracle_rdm(
    chroma_path: str  = "./chroma_db",
    force:       bool = False,
    data_dir:    str  = None,
    on_log             = None,
) -> dict:
    """
    Seed ALL Oracle RDM entities and tables into ChromaDB.
    Each chunk tagged brd_domain=Y/N for filtering at query time.
    Returns {ldm: n_seeded, pdm: n_seeded}.
    """
    def log(msg):
        if on_log: on_log(msg)

    import chromadb

    # Locate data files
    if data_dir is None:
        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            "/home/claude",
            os.path.dirname(__file__),
        ]
        data_dir = next(
            (d for d in candidates
             if os.path.exists(os.path.join(d, "oracle_rdm_entities.json"))),
            candidates[0]
        )

    entities_path = os.path.join(data_dir, "oracle_rdm_entities.json")
    tables_path   = os.path.join(data_dir, "oracle_rdm_tables.json")

    if not os.path.exists(entities_path):
        raise FileNotFoundError(
            f"oracle_rdm_entities.json not found in {data_dir}.\n"
            "Copy the JSON files extracted from the PDF to this directory."
        )

    with open(entities_path) as f:
        all_entities = json.load(f)
    with open(tables_path) as f:
        all_tables = json.load(f)

    brd_e = sum(1 for e in all_entities if _entity_in_brd(e))
    brd_t = sum(1 for t in all_tables   if _table_in_brd(t))
    log(f"Loaded: {len(all_entities)} entities ({brd_e} BRD-domain), "
        f"{len(all_tables)} tables ({brd_t} BRD-domain)")

    ef     = _get_ef()
    client = chromadb.PersistentClient(path=chroma_path)
    result = {}

    for col_name, items, build_text, build_meta, id_prefix, brd_fn in [
        (
            COLLECTION_LDM, all_entities,
            lambda e, brd: _entity_text(e, brd),
            lambda e, brd: {
                "name":          e.get("name",""),
                "entity_type":   e.get("type",""),
                "subject_areas": "|".join(e.get("subject_areas",[])),
                "brd_domain":    brd,
                "chapter":       "2",
            },
            "ldm_", _entity_in_brd,
        ),
        (
            COLLECTION_PDM, all_tables,
            lambda t, brd: _table_text(t, brd),
            lambda t, brd: {
                "name":        t.get("table_name",""),
                "entity_type": t.get("table_type", t.get("table_name","")[:3]),
                "brd_domain":  brd,
                "chapter":     "3",
            },
            "pdm_", _table_in_brd,
        ),
    ]:
        # Check if already seeded
        try:
            existing = client.get_collection(col_name, embedding_function=ef)
            if existing.count() > 0 and not force:
                log(f"⚡ {col_name}: already seeded ({existing.count()}) — skipping")
                result[col_name.split("_")[-1]] = 0
                continue
            client.delete_collection(col_name)
            log(f"Deleted existing {col_name} for re-seed")
        except Exception:
            pass

        log(f"Seeding {col_name} ({len(items)} items)…")
        col = client.create_collection(
            name=col_name,
            embedding_function=ef,
            metadata={
                "total":    str(len(items)),
                "brd_note": "filter with where={'brd_domain':'Y'} for BRD-scoped results",
            }
        )

        ids, docs, metas = [], [], []
        seen_ids = {}  # de-duplicate: names collide after lower/truncation
        for item in items:
            brd  = "Y" if brd_fn(item) else "N"
            name = item.get("name","") or item.get("table_name","")
            base = f"{id_prefix}{name.lower().replace(' ','_').replace('/','_')[:80]}"
            seen_ids[base] = seen_ids.get(base, 0) + 1
            cid = base if seen_ids[base] == 1 else f"{base}_{seen_ids[base]}"
            ids.append(cid)
            docs.append(build_text(item, brd))
            metas.append(build_meta(item, brd))

        # Batch insert — 100 at a time
        batch = 100
        for i in range(0, len(ids), batch):
            col.add(
                ids=ids[i:i+batch],
                documents=docs[i:i+batch],
                metadatas=metas[i:i+batch],
            )
            log(f"  {col_name}: {min(i+batch, len(ids))}/{len(ids)}")

        key = "ldm" if col_name == COLLECTION_LDM else "pdm"
        result[key] = len(ids)
        log(f"✅ {col_name}: {len(ids)} chunks seeded")

    return result


def query_oracle_rdm(
    query:           str,
    collection:      str  = COLLECTION_LDM,
    chroma_path:     str  = "./chroma_db",
    top_k:           int  = 3,
    brd_domain_only: bool = True,
    entity_type:     str  = None,
) -> list[dict]:
    """
    Query Oracle RDM ChromaDB collection.

    Args:
        brd_domain_only: True = filter to brd_domain=Y (BRD-relevant only)
                         False = search all 927 entities
        entity_type:     Optional filter e.g. "Reference","Derived","DWR","DWD"
    """
    import chromadb

    ef     = _get_ef()
    client = chromadb.PersistentClient(path=chroma_path)

    try:
        col = client.get_collection(collection, embedding_function=ef)
    except Exception:
        return []

    # Build ChromaDB where clause
    filters = []
    if brd_domain_only:
        filters.append({"brd_domain": {"$eq": "Y"}})
    if entity_type:
        filters.append({"entity_type": {"$eq": entity_type}})

    where = None
    if len(filters) == 1:
        where = filters[0]
    elif len(filters) > 1:
        where = {"$and": filters}

    try:
        n = min(top_k, col.count())
        if n == 0:
            return []
        r = col.query(
            query_texts=[query],
            n_results=n,
            where=where,
            include=["documents","metadatas","distances"],
        )
        return [
            {"text":     r["documents"][0][i],
             "metadata": r["metadatas"][0][i],
             "distance": r["distances"][0][i]}
            for i in range(len(r["ids"][0]))
        ]
    except Exception:
        return []


if __name__ == "__main__":
    import sys
    chroma   = sys.argv[1] if len(sys.argv) > 1 else "./chroma_db"
    force    = "--force" in sys.argv
    data_dir = next(
        (sys.argv[i+1] for i,a in enumerate(sys.argv[:-1]) if a == "--data"), None
    )

    counts = seed_oracle_rdm(chroma_path=chroma, force=force,
                              data_dir=data_dir, on_log=print)
    print(f"\nResult: {counts}")

    print("\n--- Test: BRD-domain only ---")
    for q in ["product item hierarchy retail","markdown fact sales","organisation store location"]:
        results = query_oracle_rdm(q, COLLECTION_LDM, chroma,
                                   top_k=2, brd_domain_only=True)
        print(f"  Q: {q!r}")
        for r in results:
            m = r["metadata"]
            print(f"    [{m['entity_type']}] {m['name']} "
                  f"brd={m['brd_domain']} d={r['distance']:.3f}")
