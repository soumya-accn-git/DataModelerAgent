"""
Step A — Oracle Retail Reference Seeder

Seeds ChromaDB collection 'oracle_retail_reference' with dimension
attributes and metric definitions scraped from Oracle Retail Insights
Sections 5 & 6.

Each chunk = one dimension group or one metric group, stored with
metadata (section, entity_type, table_hint) for precise RAG retrieval.

Usage:
    from agent.ldm_seeder import seed_oracle_reference
    n = seed_oracle_reference(chroma_path="./chroma_db")
    # returns number of chunks seeded

Run once — subsequent calls skip if collection already populated.
Force re-seed: seed_oracle_reference(chroma_path, force=True)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

COLLECTION_NAME = "oracle_retail_reference"

# ── Oracle reference corpus ───────────────────────────────────────────────────
# Structured from Oracle Retail Insights User Guide Release 15.0
# Sections 5 (Dimensions and Attributes) and 6 (Metrics)

ORACLE_REFERENCE_CHUNKS = [

    # ── Section 5: Dimensions ──────────────────────────────────────────────

    {
        "id": "dim_product",
        "section": "5",
        "entity_type": "dimension",
        "table_hint": "DIM_PRODUCT",
        "text": """Oracle Retail Product Dimension — Section 5

The Product dimension represents the merchandise hierarchy used to organise
and analyse products. Data is stored at item level for maximum flexibility.

Hierarchy: Company → Division → Group → Department → Class → Subclass → Item

Key attributes and their definitions:
- Division: Top-level merchandising grouping below company level
- Group: Second level, grouping of departments
- Department (Dept): Third level, grouping of similar merchandise classes
- Class: Fourth level, grouping of related subclasses
- Subclass: Fifth level, the lowest planning level above item
- Item: The individual SKU or style/colour combination at the lowest level
- Style/Colour differentiators: Style ID and Colour ID distinguish variants
- Profit Calc Type: Method used to calculate profit — RETAIL or COST basis
- Purchase Type: How the item is purchased — OWNED or CONSIGNMENT
- Market Item Flag: Indicates if item is a market item (season reporting excluded)

SCD Type: SCD2 — product reclassification tracked via effective/expiry dates
and CURRENT_FLAG. Required for As-Was reporting across reclassification events.

Source system: Oracle Retail Merchandising System (RMS)
Grain: One row per item per effective date period"""
    },

    {
        "id": "dim_organisation",
        "section": "5",
        "entity_type": "dimension",
        "table_hint": "DIM_ORGANISATION",
        "text": """Oracle Retail Organisation Dimension — Section 5

The Organisation dimension mirrors the retail company structure enabling
analysis at every level from company to individual store location.

Hierarchy: Company → Chain → Area → Region → District → Store/Location

Key attributes and their definitions:
- Company: The top-level legal entity
- Chain: A group of stores with common branding or ownership
- Area: Geographic or operational grouping of regions
- Region: Grouping of districts; key reporting level for regional managers
- District: Grouping of stores within a region
- Store/Location: The physical retail location — lowest reporting level
- Channel Type: STORE / ONLINE / WHOLESALE — channel classification
- Store Format: Physical format of the location (e.g. hypermarket, express)
- Selling Area Sqf: Square footage of the selling floor area
- Comp Store Flag: Y when store has been open 53+ weeks — used to exclude
  new/closed stores from comparable store analysis (FR-015)
- Store Open Date: Date the store began trading
- Store Close Date: Date the store ceased trading (NULL if still open)
- VAT Region: VAT region code for tax calculation
- Currency Code: Primary trading currency for the location
- Store Class: Classification grouping for performance comparison

SCD Type: SCD2 — org reclassification tracked via effective/expiry dates
and CURRENT_FLAG. Required for As-Was reporting.

Source system: Oracle Retail Merchandising System (RMS)"""
    },

    {
        "id": "dim_business_calendar",
        "section": "5",
        "entity_type": "dimension",
        "table_hint": "DIM_BUSINESS_CALENDAR",
        "text": """Oracle Retail Business Calendar Dimension — Section 5

The Business Calendar (fiscal calendar) is based on the retailer's fiscal
year and is not aligned with the Gregorian calendar. It eliminates
discrepancies in the number of days per month and weekend days per month.

Supported calendar types:
- 4-5-4 Calendar: Default. Quarters have two 4-week and one 5-week month.
  Every quarter contains exactly 13 full weeks.
- 13-Period Calendar: Year divided into 13 periods of 4 weeks (28 days).
  Every 5th or 6th year has 53 weeks.
- Gregorian Calendar: Solar calendar — always installed alongside fiscal.

Hierarchy: Fiscal Year → Half Year → Quarter → Period → Week → Day

Key attributes:
- Fiscal Date: The specific fiscal date
- Fiscal Day Name: Name of the fiscal day
- Fiscal Week: Fiscal week number within the year
- Fiscal Week Start/End Date: Boundaries of the fiscal week
- Fiscal Period: Generally equivalent to a month in financial statements
- Fiscal Period Start/End Date: Boundaries of the fiscal period
- Fiscal Quarter: Fiscal quarter number
- Fiscal Half Year: H1 or H2
- Fiscal Year: The fiscal year identifier
- Fiscal Year Start/End Date: Full year boundaries
- Gregorian Date, Month, Year: Parallel Gregorian calendar attributes
- Week Number 52: Week number in 52-week cycle for BOH/Comp metrics

Source system: Oracle Retail Merchandising System (RMS)
Note: Most facts are qualified by a calendar attribute."""
    },

    {
        "id": "dim_product_season",
        "section": "5",
        "entity_type": "dimension",
        "table_hint": "DIM_PRODUCT_SEASON",
        "text": """Oracle Retail Product Season Dimension — Section 5

The Product Season dimension supports seasonal merchandise analysis.
Product seasons do NOT need to align with the business calendar —
they represent the retailer's buying/selling seasons independently.

Hierarchy: Season → Phase → Item

Key attributes:
- Season ID: Unique identifier for the merchandise season
- Season Desc: Description of the season (e.g. Spring/Summer 2026)
- Season Start Date: First date of the season (independent of fiscal calendar)
- Season End Date: Last date of the season
- Phase ID: Sub-division within a season (e.g. Early, Main, Late)
- Phase Desc: Description of the phase
- Phase Start/End Date: Boundaries of the season phase

Important constraint (FR-013): Items belonging to multiple seasons
require a filter on season to prevent double-counting. A Bridge table
(BRIDGE_ITEM_SEASON) is mandatory to resolve the M:N relationship
between items and seasons with a WEIGHTING_FACTOR and PRIMARY_SEASON_FLAG.

Source system: Oracle Retail Merchandising System (RMS)
Note: Season reporting is NOT supported for Market Item and Consumer reports."""
    },

    {
        "id": "dim_retail_price_type",
        "section": "5",
        "entity_type": "dimension",
        "table_hint": "DIM_RETAIL_PRICE_TYPE",
        "text": """Oracle Retail Price Type Dimension — Section 5 / FR-011

The Retail Type dimension classifies sales by the type of price at which
the item was sold. This enables analysis of sales performance by pricing strategy.

Values:
- REGULAR: Items sold at the normal full retail price
- PROMOTION: Items sold as part of a planned promotional event
- CLEARANCE: Items sold at a reduced clearance price

Key attributes:
- Price Type Code: REGULAR / PROMOTION / CLEARANCE
- Price Type Desc: Human-readable description
- Price Type Group: REGULAR or MARKDOWN (Promotion and Clearance are both markdown)

Usage: All sales facts, markdown facts, and forecast facts are held
by retail price type to allow analysis at this level (FR-011).
This dimension is a foreign key on FACT_SALES and FACT_MARKDOWN.

Source: Derived from Oracle Retail Sales Audit (ReSA) transaction data"""
    },

    # ── Section 6: Metrics ──────────────────────────────────────────────────

    {
        "id": "metric_sales",
        "section": "6",
        "entity_type": "fact_metrics",
        "table_hint": "FACT_SALES",
        "text": """Oracle Retail Sales Metrics — Section 6

Sales metrics provide KPIs for merchandising executives to evaluate
operational effectiveness and deviations from sales plans.

Core sales metric definitions:
- Net Sales Amt: Sales amount excluding returns; actual money received.
  Calculated as: Gross Sales Amt - Return Amt
- Gross Sales Amt: Total amount from all units sold before returns.
  Calculated as: Unit Price × Units Sold
- Net Sales Qty: Net number of units sold (gross minus returned units)
- Gross Sales Qty: Total number of units sold before returns
- Return Amt: Value of units returned by customers
- Return Qty: Number of units returned by customers
- Net Profit Amt: Bottom-line profit after returns.
  Calculated as: Net Sales Amt - Cost of Goods Sold
- Gross Profit Amt: Profit before deducting returns.
- Transaction Count: Number of individual sales transactions
- Sales Amt Contribution to Division: Revenue for a division as % of company total
- Profit Item Contribution to Dept: Profit from item as % of total dept profit

Time-series variants (pre-aggregated in ETL):
- Net Sales Amt LY: Prior year net sales for same period
- Net Sales Amt Var LY: Variance vs last year = (Current - LY) / LY
- Net Sales Amt WTD: Week-to-date cumulative net sales
- Net Sales Amt MTD: Month-to-date cumulative net sales
- Net Sales Amt YTD: Year-to-date cumulative net sales
- Gross Sales Qty WTD: Week-to-date gross sales quantity
- Gross Sales Qty WTD Var LY: WTD quantity variance vs last year

Grain: Item × Location × Day × Retail Price Type (detail)
       Subclass × Location × Week × Retail Price Type (aggregate)

Additivity:
- Net/Gross Sales Amt: ADDITIVE across all dimensions
- Net/Gross Sales Qty: ADDITIVE across all dimensions
- Contribution %: NON-ADDITIVE (ratio — never SUM)
- LY comparisons: ADDITIVE across product/org, SEMI-ADDITIVE across time

Source system: Oracle Retail Sales Audit (ReSA)"""
    },

    {
        "id": "metric_markdown",
        "section": "6",
        "entity_type": "fact_metrics",
        "table_hint": "FACT_MARKDOWN",
        "text": """Oracle Retail Markdown and Markup Metrics — Section 6

Markdown metrics support analysis of pricing decisions, inventory
management, and gross margin impact across retail price types.

Metric definitions:
- Markdown Amt: Total markdown = Clearance + Promotion + Permanent markdowns
- Clearance Mkdn Amt: Markdowns on items marked for clearance
- Promo Mkdn Amt: Markdowns associated with planned promotional events
- Pmt Mkdn Amt: Permanent price reductions (not time-limited promotions)
- Markup Amt: Price increases applied to items
- Mkdn to Sales Amt: Ratio of markdown to gross sales — key KPI for buyers
  Calculated as: Markdown Amt / Gross Sales Amt
- Gross Markdown Pct: Actual percentage of markdowns against item/category

Time-series variants:
- Mkdn Amt WTD: Week-to-date markdown amount
- Mkdn Amt MTD: Month-to-date markdown amount
- Mkdn Amt YTD: Year-to-date markdown amount
- Mkdn Amt Var LY: Markdown variance vs last year
- Mkdn to Sales Amt LY WTD/MTD/YTD: Prior year ratios for comparison
- Comp Mkdn Amt: Markdown in comparable stores only (excludes new/closed)

Grain: Item × Location × Week × Retail Price Type
Analysis supports: Regular, Promotion, and Clearance retail types separately

Additivity:
- Markdown Amt: ADDITIVE across product and org dimensions
- Mkdn to Sales Amt: NON-ADDITIVE (ratio)
- Comp Mkdn Amt: SEMI-ADDITIVE (only valid for comp store subset)

Source system: Oracle Retail Sales Audit (ReSA) via RPM"""
    },

    {
        "id": "metric_forecast",
        "section": "6",
        "entity_type": "fact_metrics",
        "table_hint": "FACT_SALES_FORECAST",
        "text": """Oracle Retail Sales Forecast Metrics — Section 6

Sales forecast metrics support forward-looking planning and variance
analysis between actuals and projections.

Metric definitions:
- Fcst Sales Qty: Forecast quantity for the given item-location-week period
- Fcst Sales Qty LW: Last week's forecast quantity (for comparison)
- Fcst Sales Qty MTD: Month-to-date cumulative forecast quantity
- Fcst Sales Qty YTD: Year-to-date cumulative forecast quantity
- Fcst Sales Qty Var: Actual gross sales qty minus forecast qty
- Fcst Sales Qty NW: Next week's forecast quantity (forward-looking)
- Fcst Sales Qty MTD Var: MTD variance of actuals vs forecast
- Fcst Sales Qty YTD Var: YTD variance of actuals vs forecast

Important constraints:
- Forecast quantities EXCLUDE VAT (FR-014)
- Grain is ALWAYS item-location-week — never daily (FR-014)
- Cannot be used for planning/stock-ledger below subclass-week (FR-019)
- VAT Excluded Flag must be Y on all forecast rows

Grain: Item × Location × Week (no daily grain for forecasts)

Additivity: All forecast quantity metrics are ADDITIVE across product and org

Source system: Oracle Retail Merchandise Financial Planning (MFP)"""
    },

    {
        "id": "metric_supplier_cost",
        "section": "6",
        "entity_type": "fact_metrics",
        "table_hint": "FACT_SUPPLIER_COST",
        "text": """Oracle Retail Cost and Profit Metrics — Section 6

Cost metrics provide insight into the financial impact of supplier
relationships, deals, and negotiated discounts across four cost tiers.

Cost tier definitions:
- Supplier Base Cost: Initial cost before any charges, discounts, or deals.
  This is the starting point for all cost calculations.
- Supplier Net Cost: Base cost after trade, cash, and off-invoice discounts.
  Also called 'deal cost'. Held at supplier level.
- Supplier Net Net Cost: Net cost less any bill-back amounts.
  Bill-backs are retrospective payments from suppliers.
- Supplier Dead Net Cost: Net net cost less any rebate amounts.
  The fully-netted cost representing the true economic cost.

Corresponding profit metrics (Sales Amt minus each cost tier):
- Supplier Base Profit: Revenue minus base cost
- Supplier Net Profit: Revenue minus net cost
- Supplier Net Net Profit: Revenue minus net net cost
- Supplier Dead Net Profit: Revenue minus dead net cost

Profit calculation: Net Sales Amt - weighted average cost at end of day

Net cost data source: Oracle Retail Merchandising System (RMS)
with deals from deal partners (suppliers, wholesalers, distributors).

Grain: Item × Supplier × Period

Additivity: All cost and profit amounts are ADDITIVE across product and org
Note: Net profit data is only available by primary supplier

Source system: Oracle Retail Invoice Matching (ReIM) for invoice costs,
Oracle Retail Merchandising System (RMS) for deal costs"""
    },

    {
        "id": "metric_comparable_stores",
        "section": "6",
        "entity_type": "fact_metrics",
        "table_hint": "DIM_ORGANISATION",
        "text": """Oracle Retail Comparable Stores Analysis — Section 6 / FR-015

Comp store metrics exclude new and closed stores from baseline
comparisons to provide stable performance indicators.

A store becomes comp when it has been open for 53 weeks and is
still in operation at the start of the current comp period.

Key comp store attributes on DIM_ORGANISATION:
- Comp Store Flag: Y = comp store, N = non-comp
  Derivable from Store Open Date (53-week rule) or sourced directly
  from Oracle Retail source system
- Store Open Date: Used to calculate the 53-week comp threshold
- Store Close Date: NULL if still open; populated when store closes

Comp store metric implications:
- Comp Mkdn Amt in FACT_MARKDOWN: Markdown for comp stores only
- Comp store metrics are SEMI-ADDITIVE — valid only when filtered
  to the comp store subset

Constraint (FR-016): Comp metrics only supported at week level
and above — require a prompt or filter on week or higher.
Cannot be computed at daily grain.

Rule: stores whose open dates are not in the source system
are excluded from comp comparisons entirely."""
    },

    {
        "id": "metric_currency",
        "section": "6",
        "entity_type": "reference",
        "table_hint": "FACT_CURRENCY_CONVERSION",
        "text": """Oracle Retail Multi-Currency Support — FR-009

All amount metrics must support five currency types simultaneously.
Currency conversion is handled via a lookup table, not column duplication.

Five supported currency types:
- LOCAL: The currency of the store location's country
- DOCUMENT: The currency of the original transaction document
- GLOBAL1: First corporate global currency (e.g. USD)
- GLOBAL2: Second corporate global currency (e.g. EUR)
- GLOBAL3: Third corporate global currency (e.g. GBP)

FACT_CURRENCY_CONVERSION table:
- Grain: From-currency × Currency Type × Date
- Exchange Rate: Rate applied for conversion
- Effective/Expiry Date: Rate validity period
- Source system: Oracle Retail Price Management (RPM)

Usage pattern: BI semantic layer joins FACT_CURRENCY_CONVERSION at
query time to convert any amount metric to the requested currency type.
This avoids duplicating 5× amount columns in every fact table.

Store currency code is on DIM_ORGANISATION (CURRENCY_CODE attribute)."""
    },

    {
        "id": "metric_analysis_modes",
        "section": "3",
        "entity_type": "subject_area",
        "table_hint": "V_SALES_AS_IS V_SALES_AS_WAS V_SALES_POINT_IN_TIME",
        "text": """Oracle Retail Analysis Modes — Section 3 / FR-018

Three analysis modes are supported via separate subject area database views.
As-Is and As-Was results MUST NOT be mixed on the same report (FR-018).

Analysis mode definitions:
- AS_IS (Retail Merchandise Insights As-Is subject area):
  Historical data associated with CURRENT hierarchy (post-reclassification).
  Shows performance as if it always occurred under today's structure.
  Implementation: JOIN DIM_PRODUCT/DIM_ORGANISATION WHERE CURRENT_FLAG = 'Y'

- AS_WAS (Retail Merchandise Insights As-Was subject area):
  Historical data stays linked to the hierarchy at time of transaction.
  Enables before/after reclassification comparison.
  Implementation: JOIN using BETWEEN EFFECTIVE_DATE AND EXPIRY_DATE
  matching the transaction's FISCAL_DATE.

- POINT_IN_TIME (Retail Merchandise Insights Point in Time subject area):
  Hierarchy applied as it existed on a user-supplied date.
  Requires a time dimension prompt on EVERY report (FR-017).
  Cannot use aggregate fact tables.
  Implementation: JOIN using user-supplied :PIT_DATE bind variable.

ANALYSIS_MODE_CODE column on FACT_SALES and FACT_MARKDOWN:
Values: 'AS_IS' / 'AS_WAS' / 'POINT_IN_TIME'
Views V_SALES_AS_IS, V_SALES_AS_WAS, V_SALES_POINT_IN_TIME enforce separation."""
    },

    {
        "id": "dim_supplier",
        "section": "5",
        "entity_type": "dimension",
        "table_hint": "FACT_SUPPLIER_COST",
        "text": """Oracle Retail Supplier Dimension — Section 5

The Supplier dimension stores data about the vendors and suppliers
that provide merchandise to the retailer.

Key attributes:
- Supplier ID: Unique identifier for the supplier
- Supplier Name: Trading name of the supplier
- Primary Supplier Flag: Y if this is the primary supplier for the item
- Supplier Country: Country of origin
- Deal Partner Type: SUPPLIER / WHOLESALER / DISTRIBUTOR / MANUFACTURER

Supplier data is used in:
- FACT_SUPPLIER_COST: Cost tiers by supplier
- Supplier Performance metrics: Net sales, profit, markups by primary supplier
- Supplier Compliance metrics: Timeliness, delivery accuracy, order fulfillment

Net cost measures are held at the supplier level. Unless facts are stored
by supplier, all facts can only be attributed to the primary supplier.

Source system: Oracle Retail Merchandising System (RMS)"""
    },

    {
        "id": "ref_etl_batch",
        "section": "NFR",
        "entity_type": "reference",
        "table_hint": "REF_ETL_BATCH_STATUS",
        "text": """Oracle Retail ETL Batch Status — Non-Functional Requirement

Reports must reflect data from a completed nightly batch ETL run.
Reports shall not be rendered if the batch for the subject area
has not completed successfully.

REF_ETL_BATCH_STATUS table:
- Subject Area Code: Which subject area this batch covers
  (e.g. MERCH_SALES_PROFIT, MARKDOWNS, FORECAST)
- Load Date: The date the ETL batch was run
- Load Start/End Time: Timestamps for monitoring and SLA tracking
- Batch Status: PENDING / SUCCESS / FAILED
- Records Loaded: Count of rows successfully processed
- Error Count: Number of errors encountered
- Source System Code: Which source system was loaded

ETL source systems (FR NFR):
- ReSA (Oracle Retail Sales Audit): Sales transaction data — nightly
- RMS (Oracle Retail Merchandising System): Dimension data — nightly
- MFP (Oracle Retail Merchandise Financial Planning): Forecast — weekly
- ReIM (Oracle Retail Invoice Matching): Invoice cost — nightly
- RPM (Oracle Retail Price Management): Price/promotion — nightly"""
    },
]


# ── Seeder ────────────────────────────────────────────────────────────────────

def seed_oracle_reference(
    chroma_path: str = "./chroma_db",
    force: bool = False,
    on_log = None,
) -> int:
    """
    Seed ChromaDB with Oracle Retail Insights reference chunks.

    Args:
        chroma_path: Path to ChromaDB persistent directory
        force:       Re-seed even if collection already populated
        on_log:      Optional logging callback

    Returns:
        Number of chunks seeded (0 if skipped)
    """
    def log(msg):
        if on_log: on_log(msg)

    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        raise ImportError("chromadb not installed. Run: pip install chromadb onnxruntime")

    # Embedding function — ONNX (no torchvision needed)
    try:
        ef = embedding_functions.ONNXMiniLM_L6_V2()
    except Exception:
        ef = embedding_functions.DefaultEmbeddingFunction()

    client = chromadb.PersistentClient(path=chroma_path)

    # Check if already seeded
    try:
        existing = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
        )
        count = existing.count()
        if count > 0 and not force:
            log(f"Oracle reference already seeded ({count} chunks) — skipping")
            log("Use force=True to re-seed")
            return 0
        if force:
            client.delete_collection(COLLECTION_NAME)
            log("Deleted existing collection for re-seed")
    except Exception:
        pass  # Collection doesn't exist yet

    # Create collection
    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={
            "description": "Oracle Retail Insights User Guide — Sections 5 & 6",
            "source": "https://docs.oracle.com/cd/E22577_01/pdf/150/ri/html/user_guide/",
            "version": "Release 15.0",
        }
    )
    log(f"Created ChromaDB collection: {COLLECTION_NAME}")

    # Batch-add all chunks
    ids        = [c["id"]         for c in ORACLE_REFERENCE_CHUNKS]
    documents  = [c["text"]       for c in ORACLE_REFERENCE_CHUNKS]
    metadatas  = [
        {
            "section":     c["section"],
            "entity_type": c["entity_type"],
            "table_hint":  c["table_hint"],
        }
        for c in ORACLE_REFERENCE_CHUNKS
    ]

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    n = len(ORACLE_REFERENCE_CHUNKS)
    log(f"Seeded {n} Oracle Retail reference chunks into '{COLLECTION_NAME}'")
    log("Chunks cover: dimensions (Product, Organisation, Calendar, Season, Price Type)")
    log("             metrics (Sales, Markdown, Forecast, Supplier Cost)")
    log("             reference (Currency, ETL Batch, Analysis Modes)")
    return n


def query_oracle_reference(
    query: str,
    chroma_path: str = "./chroma_db",
    top_k: int = 3,
    entity_type_filter: str = None,
) -> list[dict]:
    """
    Query the Oracle reference collection for relevant context.

    Args:
        query:               Natural language query (e.g. "product dimension attributes")
        chroma_path:         Path to ChromaDB persistent directory
        top_k:               Number of results to return
        entity_type_filter:  Optional filter ('dimension', 'fact_metrics', 'reference')

    Returns:
        List of {text, metadata, distance} dicts
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
        collection = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
        )
    except Exception:
        return []

    where = {"entity_type": entity_type_filter} if entity_type_filter else None

    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, collection.count()),
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    output = []
    for i in range(len(results["ids"][0])):
        output.append({
            "text":     results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })
    return output


if __name__ == "__main__":
    import sys
    chroma = sys.argv[1] if len(sys.argv) > 1 else "./chroma_db"
    force  = "--force" in sys.argv
    n = seed_oracle_reference(chroma_path=chroma, force=force, on_log=print)
    print(f"\nDone. {n} chunks seeded.")

    # Quick test query
    if n > 0:
        print("\nTest query: 'product dimension attributes hierarchy'")
        results = query_oracle_reference("product dimension attributes hierarchy", chroma)
        for r in results:
            print(f"  [{r['metadata']['table_hint']}] distance={r['distance']:.3f}")
