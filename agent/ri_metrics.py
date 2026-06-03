"""
Oracle Retail Insights — Metric Definitions catalog + ChromaDB seeder.

Source: Oracle Retail Insights User Guide, "Metrics" appendix
  https://docs.oracle.com/cd/E22577_01/pdf/150/ri/html/user_guide/metrics_list_apx.htm

The appendix defines ~1,500 metrics across 9 functional areas (most are
time-period variants — LW/LY/WTD/MTD/YTD/Var/Comp — of a smaller set of base
measures). This module captures the BASE measures per area and maps each one to
a candidate LDM fact column: column name, Oracle data type, additivity, target
fact table, and definition. The time-variant suffix convention is documented in
each seeded chunk rather than enumerated row-by-row.

Seeds into ChromaDB collection 'oracle_retail_metrics' (one rich chunk per
functional area) so Step B (CDM->LDM promotion) can retrieve the standard metric
columns for each fact entity and ground the generated fact tables in them.

Usage:
    from agent.ri_metrics import seed_ri_metrics, query_ri_metrics
    n = seed_ri_metrics(chroma_path="./chroma_db")
    hits = query_ri_metrics("daily sales and profit", chroma_path="./chroma_db")
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

COLLECTION_NAME = "oracle_retail_metrics"
SOURCE_URL = ("https://docs.oracle.com/cd/E22577_01/pdf/150/ri/html/"
              "user_guide/metrics_list_apx.htm")

# Time-period / comparison variants that apply to most base measures. Documented
# rather than enumerated — the ETL pre-aggregates these as extra columns.
VARIANT_SUFFIXES = (
    "_LW (last week), _LY (last year), _WTD (week-to-date), _MTD (month-to-date), "
    "_YTD (year-to-date), _VAR_LW / _VAR_LY (variance vs prior period), "
    "_COMP (comparable-store subset, semi-additive)"
)

# ── Base measure catalog (metric name, column, additivity, definition) ────────
# additivity: 'additive' | 'semi_additive' | 'non_additive'

RI_METRIC_AREAS = [
    {
        "area": "Cost / Profit",
        "table_c": "C-1",
        "fact_table_hint": "FACT_SUPPLIER_COST",
        "metrics": [
            ("Supplier Base Cost",     "SUPPLIER_BASE_COST",     "additive",     "Initial cost before handling, shipping, tax, deals or discounts."),
            ("Supplier Net Cost",      "SUPPLIER_NET_COST",      "additive",     "Base cost after trade, cash or off-invoice discounts (deal cost)."),
            ("Supplier Net Net Cost",  "SUPPLIER_NET_NET_COST",  "additive",     "Net cost less bill-back amounts."),
            ("Supplier Dead Net Cost", "SUPPLIER_DEAD_NET_COST", "additive",     "Net net cost less rebates — fully-netted true economic cost."),
            ("Supplier Base Profit",   "SUPPLIER_BASE_PROFIT",   "additive",     "Sales revenue minus base cost."),
            ("Supplier Net Profit",    "SUPPLIER_NET_PROFIT",    "additive",     "Sales revenue minus net cost."),
            ("Supplier Net Net Profit","SUPPLIER_NET_NET_PROFIT","additive",     "Sales revenue minus net net cost."),
            ("Supplier Dead Net Profit","SUPPLIER_DEAD_NET_PROFIT","additive",   "Sales revenue minus dead net cost."),
        ],
    },
    {
        "area": "Markdowns",
        "table_c": "C-2",
        "fact_table_hint": "FACT_MARKDOWN",
        "metrics": [
            ("Mkdn Amt",           "MKDN_AMT",            "additive",     "Total markdown = original retail minus selling price."),
            ("Clr Mkdn Amt",       "CLR_MKDN_AMT",        "additive",     "Clearance markdown amount (obsolescence, competition, excess supply)."),
            ("Pro Mkdn Amt",       "PRO_MKDN_AMT",        "additive",     "Promotional markdown amount (temporary, time-limited)."),
            ("Pmt Mkdn Amt",       "PMT_MKDN_AMT",        "additive",     "Permanent markdown amount (slow-moving / obsolete items)."),
            ("Mkup Amt",           "MKUP_AMT",            "additive",     "Extra amount over supplier cost (selling price minus original retail)."),
            ("Mkdn Cancelled Amt", "MKDN_CANCELLED_AMT",  "additive",     "Value of cancelled clearance markdown."),
            ("Mkup Cancelled Amt", "MKUP_CANCELLED_AMT",  "additive",     "Value of cancelled markup."),
            ("Mkdn Qty",           "MKDN_QTY",            "additive",     "Units on clearance, promotion or permanent markdown."),
            ("Clr Mkdn Qty",       "CLR_MKDN_QTY",        "additive",     "Units on clearance markdown."),
            ("Pro Mkdn Qty",       "PRO_MKDN_QTY",        "additive",     "Units on promotion markdown."),
            ("Pmt Mkdn Qty",       "PMT_MKDN_QTY",        "additive",     "Units on permanent markdown."),
            ("Mkup Qty",           "MKUP_QTY",            "additive",     "Units on markup."),
            ("Mkdn to Sales Amt",  "MKDN_TO_SALES_AMT",   "non_additive", "Markdown amount / gross sales amount — efficiency ratio (never SUM)."),
            ("Gross Markdown %",   "GROSS_MKDN_PCT",      "non_additive", "Actual percentage of markdowns against item or category (never SUM)."),
        ],
    },
    {
        "area": "Forecast",
        "table_c": "C-3",
        "fact_table_hint": "FACT_SALES_FORECAST",
        "metrics": [
            ("Fcst Sales Qty",     "FCST_SALES_QTY",      "additive",     "Sales units forecast for the period (item x location x week)."),
            ("Fcst Sales Qty NW",  "FCST_SALES_QTY_NW",   "additive",     "Next week's forecast quantity (forward-looking)."),
            ("Fcst Sales Qty Var", "FCST_SALES_QTY_VAR",  "additive",     "Actual gross sales qty minus forecast qty."),
        ],
    },
    {
        "area": "Inventory Receipts",
        "table_c": "C-4",
        "fact_table_hint": "FACT_INVENTORY_RECEIPTS",
        "metrics": [
            ("Receipts Qty",    "RECEIPTS_QTY",    "additive",     "Quantity of inventory units received."),
            ("Receipts Cost",   "RECEIPTS_COST",   "additive",     "Cost value of inventory received."),
            ("Receipts Retail", "RECEIPTS_RETAIL", "additive",     "Retail value of inventory received."),
            ("IMU %",           "IMU_PCT",         "non_additive", "Initial markup % required to cover costs, expenses and profit (never SUM)."),
        ],
    },
    {
        "area": "Sales",
        "table_c": "C-5",
        "fact_table_hint": "FACT_SALES",
        "metrics": [
            ("Gross Sales Amt",            "GROSS_SALES_AMT",          "additive",     "Retail value of units sold (includes VAT, excludes discounts)."),
            ("Return Amt",                 "RETURN_AMT",               "additive",     "Retail value of units returned (lost revenue)."),
            ("Net Sales Amt",              "NET_SALES_AMT",            "additive",     "Sales amount excluding returns = Gross Sales Amt - Return Amt."),
            ("Net Clr Sales Amt",          "NET_CLR_SALES_AMT",        "additive",     "Net clearance sales amount (excludes returns)."),
            ("Net Pro Sales Amt",          "NET_PRO_SALES_AMT",        "additive",     "Net promotion sales amount (excludes returns)."),
            ("Net Reg Sales Amt",          "NET_REG_SALES_AMT",        "additive",     "Net regular-price sales amount (excludes returns)."),
            ("Gross Sales Qty",            "GROSS_SALES_QTY",          "additive",     "Total units of merchandise sold."),
            ("Return Qty",                 "RETURN_QTY",               "additive",     "Number of units returned."),
            ("Net Sales Qty",              "NET_SALES_QTY",            "additive",     "Gross qty minus return qty."),
            ("Gross Profit",               "GROSS_PROFIT_AMT",         "additive",     "Sales revenue minus cost of units sold."),
            ("Return Profit",              "RETURN_PROFIT_AMT",        "additive",     "Returns amount minus cost of returned units."),
            ("Net Profit",                 "NET_PROFIT_AMT",           "additive",     "Gross profit minus return profit."),
            ("Net Emp Disc",               "NET_EMP_DISC_AMT",         "additive",     "Gross employee discount minus returns employee discount."),
            ("Gross Tax",                  "GROSS_TAX_AMT",            "additive",     "Tax on total sales revenue."),
            ("Return Tax",                 "RETURN_TAX_AMT",           "additive",     "Tax on returned merchandise."),
            ("Net Tax",                    "NET_TAX_AMT",              "additive",     "Gross tax minus return tax."),
            ("Trx Count",                  "TRX_COUNT",                "additive",     "Quantity of sales transactions."),
            ("Unique Item Count",          "UNIQUE_ITEM_COUNT",        "non_additive", "Distinct items in a transaction (counted once per item — never SUM across grain)."),
            ("Avg Trx Amt",                "AVG_TRX_AMT",              "non_additive", "Average transaction amount (ratio — never SUM)."),
            ("Avg Trx Unit Qty",           "AVG_TRX_UNIT_QTY",         "non_additive", "Average units per transaction (ratio — never SUM)."),
            ("Avg Net Retail",             "AVG_NET_RETAIL",           "non_additive", "Average retail price of sold items (ratio — never SUM)."),
            ("Gross Profit to Sales Amt",  "GROSS_PROFIT_TO_SALES_PCT","non_additive", "Gross profit / total sales — efficiency ratio (never SUM)."),
            ("Net Profit to Sales Amt",    "NET_PROFIT_TO_SALES_PCT",  "non_additive", "Net profit / net sales — profitability ratio (never SUM)."),
            ("Sales Amt Contribution to Tot","SALES_AMT_CONTRIB_TO_TOT_PCT","non_additive","Entity sales as % of company total (never SUM)."),
        ],
    },
    {
        "area": "Sales Pack",
        "table_c": "C-6",
        "fact_table_hint": "FACT_SALES_PACK",
        "metrics": [
            ("Pack Gross Sales Amt",  "PACK_GROSS_SALES_AMT",  "additive", "Total value of pack sales before returns."),
            ("Pack Return Amt",       "PACK_RETURN_AMT",       "additive", "Retail value of returned pack units."),
            ("Pack Net Sales Amt",    "PACK_NET_SALES_AMT",    "additive", "Pack sales excluding returns."),
            ("Pack Gross Sales Qty",  "PACK_GROSS_SALES_QTY",  "additive", "Total pack quantity before returns."),
            ("Pack Net Profit",       "PACK_NET_PROFIT_AMT",   "additive", "Pack bottom-line profit after returns."),
            ("Pack Liability Amt",    "PACK_LIABILITY_AMT",    "additive", "Retail value of sales packs tied in liability (unfulfilled orders)."),
            ("Pack Liability Qty",    "PACK_LIABILITY_QTY",    "additive", "Quantity of packs in liability."),
        ],
    },
    {
        "area": "Supplier Invoice",
        "table_c": "C-7",
        "fact_table_hint": "FACT_SUPPLIER_INVOICE",
        "metrics": [
            ("Invoice Qty",                "INVOICE_QTY",                 "additive",     "Units the supplier is requesting payment for."),
            ("PO Unit Cost",               "PO_UNIT_COST",                "non_additive", "Unit cost when the order was placed (per-unit — never SUM)."),
            ("Invoice Unit Cost",          "INVOICE_UNIT_COST",           "non_additive", "Unit cost charged by the supplier (per-unit — never SUM)."),
            ("Tot PO Unit Cost",           "TOT_PO_UNIT_COST",            "additive",     "Order qty x PO unit cost."),
            ("Tot Invoice Unit Cost",      "TOT_INVOICE_UNIT_COST",       "additive",     "Order qty x invoice unit cost."),
            ("Tot PO to Invoice Cost Diff","TOT_PO_TO_INVOICE_COST_DIFF", "additive",     "Difference between PO and invoice total costs."),
        ],
    },
    {
        "area": "Supplier Compliance",
        "table_c": "C-8",
        "fact_table_hint": "FACT_SUPPLIER_COMPLIANCE",
        "metrics": [
            ("Unfulfilled ASN Count", "UNFULFILLED_ASN_COUNT", "additive",     "ASNs not yet received."),
            ("Unfulfilled PO Count",  "UNFULFILLED_PO_COUNT",  "additive",     "POs not yet fully received."),
            ("PO Met Count",          "PO_MET_COUNT",          "additive",     "POs where ordered qty = received qty."),
            ("PO Under Count",        "PO_UNDER_COUNT",        "additive",     "POs where ordered qty > received qty."),
            ("PO Over Count",         "PO_OVER_COUNT",         "additive",     "POs where ordered qty < received qty."),
            ("Ship Late Count",       "SHIP_LATE_COUNT",       "additive",     "Shipments after the PO end date."),
            ("Ship Early Count",      "SHIP_EARLY_COUNT",      "additive",     "Shipments before the PO start date."),
            ("Ship On Time Count",    "SHIP_ON_TIME_COUNT",    "additive",     "Shipments within the PO date window."),
            ("Days Late Ship",        "DAYS_LATE_SHIP",        "non_additive", "Days after PO end date (per-shipment — average, never SUM)."),
            ("Days Early Ship",       "DAYS_EARLY_SHIP",       "non_additive", "Days before PO start date (per-shipment — average, never SUM)."),
            ("ASN Expected Qty",      "ASN_EXPECTED_QTY",      "additive",     "Quantity expected based on the ASN."),
            ("Ordered Qty",           "ORDERED_QTY",           "additive",     "Quantity ordered in the PO."),
            ("Received Qty",          "RECEIVED_QTY",          "additive",     "Quantity received in the shipment."),
            ("Shipment Count",        "SHIPMENT_COUNT",        "additive",     "Total number of shipments received."),
        ],
    },
    {
        "area": "Inventory Position",
        "table_c": "C-9",
        "fact_table_hint": "FACT_INVENTORY_POSITION",
        "metrics": [
            ("BOH Qty",         "BOH_QTY",         "semi_additive", "Beginning-of-period owned inventory quantity (semi-additive — non-additive over time)."),
            ("BOH Retail",      "BOH_RETAIL",      "semi_additive", "Beginning-of-period retail value (semi-additive over time)."),
            ("BOH Cost",        "BOH_COST",        "semi_additive", "Beginning-of-period cost value (semi-additive over time)."),
            ("EOH Qty",         "EOH_QTY",         "semi_additive", "End-of-period owned inventory quantity (semi-additive over time)."),
            ("EOH Retail",      "EOH_RETAIL",      "semi_additive", "End-of-period retail value (semi-additive over time)."),
            ("EOH Cost",        "EOH_COST",        "semi_additive", "End-of-period cost value (semi-additive over time)."),
            ("In Transit Qty",  "IN_TRANSIT_QTY",  "semi_additive", "Quantity shipped but not received (semi-additive over time)."),
            ("In Transit Cost", "IN_TRANSIT_COST", "semi_additive", "Cost value of in-transit inventory (semi-additive over time)."),
            ("On Order Qty",    "ON_ORDER_QTY",    "semi_additive", "Quantity ordered but not received (semi-additive over time)."),
            ("On Order Cost",   "ON_ORDER_COST",   "semi_additive", "Cost value of on-order inventory (semi-additive over time)."),
            ("Inv Unit Retail", "INV_UNIT_RETAIL", "non_additive",  "Retail value per standard unit (per-unit — never SUM)."),
            ("Inv Unit Cost",   "INV_UNIT_COST",   "non_additive",  "PO estimated landed cost per unit (per-unit — never SUM)."),
            ("Inv Avg Cost",    "INV_AVG_COST",    "non_additive",  "Weighted average cost, adjusted on receipt (per-unit — never SUM)."),
        ],
    },
]


# ── Type inference ────────────────────────────────────────────────────────────

def infer_data_type(column: str, additivity: str) -> str:
    """Map a metric column to an Oracle data type using its suffix + additivity."""
    if additivity == "non_additive" or column.endswith("_PCT"):
        return "NUMBER(10,6)"          # ratios / percentages
    if column.endswith("_COUNT"):
        return "NUMBER(12)"            # whole counts
    if column.startswith("DAYS_"):
        return "NUMBER(8,2)"
    if column.endswith("_QTY"):
        return "NUMBER(12,2)"          # quantities
    # amounts, costs, retail values, profit, diffs
    return "NUMBER(18,4)"


# ── Chunk rendering ───────────────────────────────────────────────────────────

def _render_area_chunk(area: dict) -> str:
    lines = [
        f"Oracle Retail Insights Metrics — {area['area']} ({area['fact_table_hint']})",
        f"Source: {SOURCE_URL} (Table {area['table_c']})",
        "",
        "Candidate fact measure columns "
        "(metric -> column : data_type : additivity -- definition):",
    ]
    for name, col, add, defn in area["metrics"]:
        dtype = infer_data_type(col, add)
        lines.append(f"- {name} -> {col} : {dtype} : {add} -- {defn}")
    lines.append("")
    lines.append(f"Time-variant columns available for most measures: {VARIANT_SUFFIXES}.")
    lines.append("Additivity rules: SUM additive measures freely; sum semi-additive "
                 "measures across all dimensions EXCEPT time (use last/average over "
                 "time); NEVER SUM non-additive ratios/percentages/per-unit measures.")
    return "\n".join(lines)


def all_columns() -> list[dict]:
    """Flat list of every candidate metric column across all areas."""
    out = []
    for area in RI_METRIC_AREAS:
        for name, col, add, defn in area["metrics"]:
            out.append({
                "metric": name,
                "column": col,
                "data_type": infer_data_type(col, add),
                "additivity": add,
                "definition": defn,
                "fact_table_hint": area["fact_table_hint"],
                "area": area["area"],
            })
    return out


# ── Seeder ────────────────────────────────────────────────────────────────────

def seed_ri_metrics(
    chroma_path: str = "./chroma_db",
    force: bool = False,
    on_log=None,
) -> int:
    """
    Seed ChromaDB collection 'oracle_retail_metrics' with one chunk per RI
    functional area. Returns number of chunks seeded (0 if skipped).
    """
    def log(msg):
        if on_log:
            on_log(msg)

    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        raise ImportError("chromadb not installed. Run: pip install chromadb onnxruntime")

    try:
        ef = embedding_functions.ONNXMiniLM_L6_V2()
    except Exception:
        ef = embedding_functions.DefaultEmbeddingFunction()

    client = chromadb.PersistentClient(path=chroma_path)

    try:
        existing = client.get_collection(name=COLLECTION_NAME, embedding_function=ef)
        count = existing.count()
        if count > 0 and not force:
            log(f"RI metrics already seeded ({count} chunks) — skipping (force=True to re-seed)")
            return 0
        if force:
            client.delete_collection(COLLECTION_NAME)
            log("Deleted existing oracle_retail_metrics collection for re-seed")
    except Exception:
        pass  # not yet created

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={
            "description": "Oracle Retail Insights — Metric Definitions appendix",
            "source": SOURCE_URL,
            "version": "Release 15.0",
        },
    )

    ids        = [f"ri_metrics_{a['fact_table_hint'].lower()}" for a in RI_METRIC_AREAS]
    documents  = [_render_area_chunk(a) for a in RI_METRIC_AREAS]
    metadatas  = [
        {
            "area": a["area"],
            "fact_table_hint": a["fact_table_hint"],
            "table_c": a["table_c"],
            "entity_type": "fact_metrics",
            "metric_count": len(a["metrics"]),
        }
        for a in RI_METRIC_AREAS
    ]

    collection.add(ids=ids, documents=documents, metadatas=metadatas)

    total_metrics = sum(len(a["metrics"]) for a in RI_METRIC_AREAS)
    log(f"Seeded {len(RI_METRIC_AREAS)} RI metric-area chunks "
        f"({total_metrics} base measures) into '{COLLECTION_NAME}'")
    log("Areas: " + ", ".join(a["area"] for a in RI_METRIC_AREAS))
    return len(RI_METRIC_AREAS)


def query_ri_metrics(
    query: str,
    chroma_path: str = "./chroma_db",
    top_k: int = 3,
    fact_table_hint: str = None,
) -> list[dict]:
    """
    Query the RI metrics collection for the most relevant metric-area chunks.

    Returns a list of {text, metadata, distance} dicts (empty on any failure).
    """
    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        return []

    try:
        ef = embedding_functions.ONNXMiniLM_L6_V2()
    except Exception:
        ef = embedding_functions.DefaultEmbeddingFunction()

    client = chromadb.PersistentClient(path=chroma_path)
    try:
        collection = client.get_collection(name=COLLECTION_NAME, embedding_function=ef)
    except Exception:
        return []

    where = {"fact_table_hint": fact_table_hint} if fact_table_hint else None
    n = min(top_k, collection.count())
    if n <= 0:
        return []
    results = collection.query(
        query_texts=[query],
        n_results=n,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    out = []
    for i in range(len(results["ids"][0])):
        out.append({
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })
    return out


if __name__ == "__main__":
    chroma = sys.argv[1] if len(sys.argv) > 1 else "./chroma_db"
    force = "--force" in sys.argv
    n = seed_ri_metrics(chroma_path=chroma, force=force, on_log=print)
    print(f"\nDone. {n} chunks seeded ({len(all_columns())} candidate metric columns).")
    if n > 0 or "--query" in sys.argv:
        print("\nTest query: 'daily sales returns and profit'")
        for r in query_ri_metrics("daily sales returns and profit", chroma):
            print(f"  [{r['metadata']['fact_table_hint']}] "
                  f"({r['metadata']['area']}) distance={r['distance']:.3f}")
