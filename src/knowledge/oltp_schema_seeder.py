"""
OLTP Source Schema Seeder — ChromaDB collection: oltp_source_schema

Seeds the Retail Merchandising OLTP source schema into ChromaDB so it can be
used as RAG grounding during CDM → LDM → PDM generation.

One chunk per OLTP table. Each chunk captures the table's purpose, grain,
column names, source-to-LDM entity mapping, and key metric formulas so the
embedding search returns the right OLTP context for any CDM entity name.

Usage:
    from src.knowledge.oltp_schema_seeder import seed_oltp_schema, query_oltp_schema
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    import chromadb
    from chromadb.utils import embedding_functions
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False

COLLECTION = "oltp_source_schema"

# ── Structured table definitions ──────────────────────────────────────────────
# Each entry drives one ChromaDB document. The text is crafted to embed well
# against queries like "sales fact", "item product dimension", "markdown fact", etc.

_TABLE_DEFS = [
    # ── Sales Transactions ────────────────────────────────────────────────────
    {
        "table_name":       "sales_transaction_line",
        "subject_area":     "sales_transaction",
        "category":         "transaction",
        "grain":            "One row per item line in a POS/order transaction.",
        "purpose":          (
            "Core transaction table. Stores item-level sales, profit, markdown, "
            "and discount amounts for every item line in every POS/order transaction. "
            "Primary source for FACT_SALES, net sales, gross profit, net profit, "
            "markdown attribution, and top-item ranking."
        ),
        "columns": (
            "transaction_line_id BIGINT PK, "
            "transaction_id BIGINT FK→sales_transaction_header, "
            "line_number INTEGER, "
            "item_id BIGINT FK→item, "
            "quantity_sold NUMERIC(18,4), "
            "regular_unit_price NUMERIC(18,4), "
            "actual_unit_price NUMERIC(18,4), "
            "gross_sales_amt NUMERIC(18,4), "
            "discount_amt NUMERIC(18,4), "
            "markdown_amt NUMERIC(18,4), "
            "net_sales_amt NUMERIC(18,4), "
            "unit_cost NUMERIC(18,4), "
            "total_cost_amt NUMERIC(18,4), "
            "gross_profit_amt NUMERIC(18,4), "
            "net_profit_amt NUMERIC(18,4), "
            "retail_type VARCHAR(30) CHECK IN (REGULAR,PROMOTION,CLEARANCE), "
            "promotion_id BIGINT, "
            "return_flag CHAR(1)"
        ),
        "feeds_ldm":        "FACT_SALES, FACT_MARKDOWN",
        "feeds_cdm":        "SalesFact, MarkdownFact",
        "metric_formulas": (
            "net_sales_amt = gross_sales_amt - discount_amt - markdown_amt; "
            "gross_profit_amt = net_sales_amt - total_cost_amt; "
            "net_profit_amt = net_sales_amt - total_cost_amt - allocated_expense"
        ),
        "related_dashboards": (
            "Current Top 10 Sale Items, Current Sales & Profit Contribution, "
            "Daily Sales & Profit, Markdown to Sales Ratio, Season Performance"
        ),
    },
    {
        "table_name":       "sales_transaction_header",
        "subject_area":     "sales_transaction",
        "category":         "transaction",
        "grain":            "One row per POS/order transaction.",
        "purpose":          (
            "Transaction header — one row per POS register sale, e-commerce order, "
            "or return. Carries store_id and business_date links, transaction-level "
            "aggregates (gross_sales_amt, net_sales_amt, markdown_amt), and "
            "transaction_type (SALE/RETURN/EXCHANGE/VOID)."
        ),
        "columns": (
            "transaction_id BIGINT PK, "
            "transaction_number VARCHAR(50) UNIQUE, "
            "store_id BIGINT FK→store, "
            "business_date DATE FK→business_calendar, "
            "transaction_ts TIMESTAMP, "
            "register_number VARCHAR(30), "
            "cashier_id VARCHAR(50), "
            "sales_channel VARCHAR(30), "
            "transaction_type VARCHAR(30) CHECK IN (SALE,RETURN,EXCHANGE,VOID), "
            "transaction_status VARCHAR(30), "
            "customer_id BIGINT, "
            "gross_sales_amt NUMERIC(18,4), "
            "discount_amt NUMERIC(18,4), "
            "markdown_amt NUMERIC(18,4), "
            "net_sales_amt NUMERIC(18,4), "
            "tax_amt NUMERIC(18,4), "
            "total_paid_amt NUMERIC(18,4), "
            "currency_code VARCHAR(10)"
        ),
        "feeds_ldm":        "FACT_SALES",
        "feeds_cdm":        "SalesFact",
        "metric_formulas":  "",
        "related_dashboards": "Daily Sales & Profit, Current Sales & Profit Contribution",
    },

    # ── Markdown / Markup ─────────────────────────────────────────────────────
    {
        "table_name":       "markdown_event",
        "subject_area":     "markdown",
        "category":         "transaction",
        "grain":            "One row per markdown event per item/location/effective period.",
        "purpose":          (
            "Captures markdown events — permanent, temporary, promotional, and clearance. "
            "Stores markdown_amt, markdown_pct, original_price, markdown_price, "
            "retail_type, and reason_code. Primary source for FACT_MARKDOWN, "
            "Markdown to Sales Ratio, and markdown scorecard metrics."
        ),
        "columns": (
            "markdown_event_id BIGINT PK, "
            "markdown_number VARCHAR(50) UNIQUE, "
            "item_id BIGINT FK→item, "
            "store_id BIGINT FK→store, "
            "markdown_type VARCHAR(30) CHECK IN (PERMANENT,TEMPORARY,PROMOTIONAL,CLEARANCE), "
            "retail_type VARCHAR(30) CHECK IN (REGULAR,PROMOTION,CLEARANCE), "
            "business_date DATE FK→business_calendar, "
            "original_price NUMERIC(18,4), "
            "markdown_price NUMERIC(18,4), "
            "markdown_amt NUMERIC(18,4), "
            "markdown_pct NUMERIC(9,4), "
            "reason_code VARCHAR(50), "
            "approved_by VARCHAR(100), "
            "effective_from DATE, "
            "effective_to DATE"
        ),
        "feeds_ldm":        "FACT_MARKDOWN",
        "feeds_cdm":        "MarkdownFact",
        "metric_formulas":  "markdown_to_sales_ratio = markdown_amt / NULLIF(net_sales_amt, 0)",
        "related_dashboards": "Markdown to Sales Ratio, Current Markdown Scorecard",
    },
    {
        "table_name":       "markup_event",
        "subject_area":     "markup",
        "category":         "transaction",
        "grain":            "One row per markup event per item/location/effective period.",
        "purpose":          (
            "Captures markup events — price increases and margin improvement actions. "
            "Stores old_price, new_price, markup_amt, markup_pct, markup_type "
            "(PRICE_INCREASE, COST_RECOVERY, MARGIN_IMPROVEMENT). "
            "Source for FACT_MARKUP and markup metrics."
        ),
        "columns": (
            "markup_event_id BIGINT PK, "
            "markup_number VARCHAR(50) UNIQUE, "
            "item_id BIGINT FK→item, "
            "store_id BIGINT FK→store, "
            "markup_type VARCHAR(30) CHECK IN (PRICE_INCREASE,COST_RECOVERY,MARGIN_IMPROVEMENT), "
            "business_date DATE FK→business_calendar, "
            "old_price NUMERIC(18,4), "
            "new_price NUMERIC(18,4), "
            "markup_amt NUMERIC(18,4), "
            "markup_pct NUMERIC(9,4), "
            "reason_code VARCHAR(50), "
            "approved_by VARCHAR(100), "
            "effective_from DATE, "
            "effective_to DATE"
        ),
        "feeds_ldm":        "FACT_MARKUP",
        "feeds_cdm":        "MarkdownFact",
        "metric_formulas":  "markup_pct = markup_amt / NULLIF(old_price, 0)",
        "related_dashboards": "Markdown to Sales Ratio",
    },

    # ── Inventory / Forecast ──────────────────────────────────────────────────
    {
        "table_name":       "inventory_snapshot",
        "subject_area":     "inventory",
        "category":         "snapshot",
        "grain":            "One row per item/store/business date.",
        "purpose":          (
            "Daily inventory position by item and store. Stores beginning and ending "
            "on-hand quantities, available quantity, reserved and in-transit quantities, "
            "inventory cost and retail value. Supports sell-through analysis, "
            "season performance stock tracking, and current sales projection."
        ),
        "columns": (
            "inventory_snapshot_id BIGINT PK, "
            "item_id BIGINT FK→item, "
            "store_id BIGINT FK→store, "
            "business_date DATE FK→business_calendar, "
            "beginning_on_hand_qty NUMERIC(18,4), "
            "ending_on_hand_qty NUMERIC(18,4), "
            "available_qty NUMERIC(18,4), "
            "reserved_qty NUMERIC(18,4), "
            "in_transit_qty NUMERIC(18,4), "
            "inventory_cost_amt NUMERIC(18,4), "
            "inventory_retail_amt NUMERIC(18,4)"
        ),
        "feeds_ldm":        "FACT_INVENTORY_SNAPSHOT",
        "feeds_cdm":        "InventoryFact",
        "metric_formulas":  "",
        "related_dashboards": "Season Performance, Current Sales Projection",
    },
    {
        "table_name":       "sales_forecast",
        "subject_area":     "forecast",
        "category":         "planning",
        "grain":            "One row per item/store/date/forecast version/grain.",
        "purpose":          (
            "Projected sales, cost, profit, and markdown at item-store, "
            "department-store, or chain-level grain. Supports current sales projection "
            "and forecast variance analysis. Stores forecast_qty, forecast_sales_amt, "
            "forecast_cost_amt, forecast_profit_amt, forecast_markdown_amt, "
            "confidence_pct. Grain choices: ITEM_STORE_DAY, ITEM_STORE_WEEK, "
            "DEPARTMENT_STORE_WEEK, ITEM_CHAIN_WEEK."
        ),
        "columns": (
            "sales_forecast_id BIGINT PK, "
            "forecast_version VARCHAR(50), "
            "item_id BIGINT FK→item, "
            "store_id BIGINT FK→store, "
            "department_id BIGINT FK→department, "
            "season_id BIGINT FK→season, "
            "forecast_date DATE FK→business_calendar, "
            "forecast_grain VARCHAR(30) CHECK IN (ITEM_STORE_DAY,ITEM_STORE_WEEK,DEPARTMENT_STORE_WEEK,ITEM_CHAIN_WEEK), "
            "forecast_qty NUMERIC(18,4), "
            "forecast_sales_amt NUMERIC(18,4), "
            "forecast_cost_amt NUMERIC(18,4), "
            "forecast_profit_amt NUMERIC(18,4), "
            "forecast_markdown_amt NUMERIC(18,4), "
            "forecast_method VARCHAR(50), "
            "confidence_pct NUMERIC(9,4), "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "FACT_SALES_FORECAST",
        "feeds_cdm":        "ForecastFact, SalesForecastFact",
        "metric_formulas":  (
            "forecast_variance_pct = (actual_sales_amt - forecast_sales_amt) "
            "/ NULLIF(forecast_sales_amt, 0)"
        ),
        "related_dashboards": "Current Sales Projection",
    },
    {
        "table_name":       "daily_item_store_sales_summary",
        "subject_area":     "sales_summary",
        "category":         "snapshot",
        "grain":            "One row per item/store/business date (pre-aggregated daily summary).",
        "purpose":          (
            "Optional pre-aggregated daily item-store sales metrics for faster dashboard "
            "reporting. Contains same measures as sales_transaction_line but rolled up to "
            "daily item-store grain: sales_qty, gross_sales_amt, net_sales_amt, "
            "discount_amt, markdown_amt, markup_amt, total_cost_amt, gross_profit_amt, "
            "net_profit_amt, return_qty, return_amt."
        ),
        "columns": (
            "summary_id BIGINT PK, "
            "business_date DATE FK→business_calendar, "
            "store_id BIGINT FK→store, "
            "item_id BIGINT FK→item, "
            "sales_qty NUMERIC(18,4), "
            "gross_sales_amt NUMERIC(18,4), "
            "net_sales_amt NUMERIC(18,4), "
            "discount_amt NUMERIC(18,4), "
            "markdown_amt NUMERIC(18,4), "
            "markup_amt NUMERIC(18,4), "
            "total_cost_amt NUMERIC(18,4), "
            "gross_profit_amt NUMERIC(18,4), "
            "net_profit_amt NUMERIC(18,4), "
            "return_qty NUMERIC(18,4), "
            "return_amt NUMERIC(18,4)"
        ),
        "feeds_ldm":        "FACT_SALES (aggregated daily grain alternative)",
        "feeds_cdm":        "SalesFact",
        "metric_formulas":  "",
        "related_dashboards": "Daily Sales & Profit",
    },

    # ── Item / Product Master ─────────────────────────────────────────────────
    {
        "table_name":       "item",
        "subject_area":     "item_product",
        "category":         "master_data",
        "grain":            "One row per sellable SKU/item.",
        "purpose":          (
            "Item/SKU master. Stores item_number, item_description, brand_name, "
            "item_type, size_desc, color_desc, style_code, uom_code, launch_date, "
            "discontinue_date. Links to merchandise hierarchy via subclass_id. "
            "Primary source for DIM_ITEM / DIM_PRODUCT dimension table."
        ),
        "columns": (
            "item_id BIGINT PK, "
            "item_number VARCHAR(50) UNIQUE, "
            "item_description VARCHAR(255), "
            "subclass_id BIGINT FK→merch_subclass, "
            "brand_name VARCHAR(100), "
            "item_type VARCHAR(50), "
            "size_desc VARCHAR(50), "
            "color_desc VARCHAR(50), "
            "style_code VARCHAR(50), "
            "uom_code VARCHAR(20), "
            "launch_date DATE, "
            "discontinue_date DATE, "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_ITEM, DIM_PRODUCT",
        "feeds_cdm":        "ItemDimension, ProductDimension",
        "metric_formulas":  "",
        "related_dashboards": "Current Top 10 Sale Items, Season Performance",
    },
    {
        "table_name":       "supplier",
        "subject_area":     "supplier_vendor",
        "category":         "master_data",
        "grain":            "One row per supplier/vendor.",
        "purpose":          (
            "Vendor/supplier master. Stores supplier_code, supplier_name, "
            "supplier_type. Linked to item via item_supplier junction. "
            "Source for DIM_SUPPLIER dimension."
        ),
        "columns": (
            "supplier_id BIGINT PK, "
            "supplier_code VARCHAR(30) UNIQUE, "
            "supplier_name VARCHAR(150), "
            "supplier_type VARCHAR(50), "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_SUPPLIER",
        "feeds_cdm":        "SupplierDimension",
        "metric_formulas":  "",
        "related_dashboards": "",
    },
    {
        "table_name":       "item_supplier",
        "subject_area":     "supplier_vendor",
        "category":         "master_data",
        "grain":            "One row per item-supplier relationship per effective period.",
        "purpose":          (
            "Item-supplier junction. Resolves many-to-many between items and suppliers. "
            "Stores primary_supplier_flag, supplier_item_code, effective_from, effective_to. "
            "Source for BRIDGE_ITEM_SUPPLIER or SCD2 supplier attributes on DIM_ITEM."
        ),
        "columns": (
            "item_supplier_id BIGINT PK, "
            "item_id BIGINT FK→item, "
            "supplier_id BIGINT FK→supplier, "
            "primary_supplier_flag CHAR(1), "
            "supplier_item_code VARCHAR(50), "
            "effective_from DATE, "
            "effective_to DATE"
        ),
        "feeds_ldm":        "BRIDGE_ITEM_SUPPLIER, DIM_ITEM (supplier attributes)",
        "feeds_cdm":        "ItemSupplierBridge",
        "metric_formulas":  "",
        "related_dashboards": "",
    },

    # ── Season ────────────────────────────────────────────────────────────────
    {
        "table_name":       "season",
        "subject_area":     "season",
        "category":         "master_data",
        "grain":            "One row per retail season.",
        "purpose":          (
            "Retail season master. Stores season_code, season_name, season_year, "
            "start_date, end_date. Supports seasonal item performance and margin "
            "tracking. Source for DIM_SEASON dimension table."
        ),
        "columns": (
            "season_id BIGINT PK, "
            "season_code VARCHAR(30) UNIQUE, "
            "season_name VARCHAR(100), "
            "season_year INTEGER, "
            "start_date DATE, "
            "end_date DATE, "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_SEASON",
        "feeds_cdm":        "SeasonDimension",
        "metric_formulas":  "",
        "related_dashboards": "Season Performance",
    },
    {
        "table_name":       "item_season",
        "subject_area":     "season",
        "category":         "master_data",
        "grain":            "One row per item-season combination.",
        "purpose":          (
            "Item-season mapping. Stores planned_sales_qty, planned_sales_amt, "
            "planned_margin_amt per item/season. Enables comparison of actual vs. "
            "planned season performance. Source for season performance analysis."
        ),
        "columns": (
            "item_season_id BIGINT PK, "
            "item_id BIGINT FK→item, "
            "season_id BIGINT FK→season, "
            "planned_sales_qty NUMERIC(18,4), "
            "planned_sales_amt NUMERIC(18,4), "
            "planned_margin_amt NUMERIC(18,4)"
        ),
        "feeds_ldm":        "FACT_SALES (season grain), DIM_SEASON",
        "feeds_cdm":        "SeasonDimension, SalesFact",
        "metric_formulas":  "profit_margin_pct = net_profit_amt / NULLIF(net_sales_amt, 0)",
        "related_dashboards": "Season Performance",
    },

    # ── Merchandise Hierarchy ─────────────────────────────────────────────────
    {
        "table_name":       "merch_division",
        "subject_area":     "merchandise_hierarchy",
        "category":         "hierarchy",
        "grain":            "One row per merchandise division (highest hierarchy level).",
        "purpose":          (
            "Top level of the retail merchandise hierarchy. Division → Group → Department "
            "→ Class → Subclass → Item. Source for DIM_PRODUCT hierarchy levels: "
            "DIVISION_CODE, DIVISION_NAME in the product dimension."
        ),
        "columns": (
            "division_id BIGINT PK, "
            "division_code VARCHAR(30) UNIQUE, "
            "division_name VARCHAR(100), "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_PRODUCT (division attributes)",
        "feeds_cdm":        "ProductDimension",
        "metric_formulas":  "",
        "related_dashboards": "Current Sales & Profit Contribution",
    },
    {
        "table_name":       "merch_group",
        "subject_area":     "merchandise_hierarchy",
        "category":         "hierarchy",
        "grain":            "One row per merchandise group.",
        "purpose":          (
            "Merchandise group — second level of hierarchy under division. "
            "division_id links to merch_division. Source for DIM_PRODUCT group attributes."
        ),
        "columns": (
            "group_id BIGINT PK, "
            "division_id BIGINT FK→merch_division, "
            "group_code VARCHAR(30) UNIQUE, "
            "group_name VARCHAR(100), "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_PRODUCT (group attributes)",
        "feeds_cdm":        "ProductDimension",
        "metric_formulas":  "",
        "related_dashboards": "",
    },
    {
        "table_name":       "department",
        "subject_area":     "merchandise_hierarchy",
        "category":         "hierarchy",
        "grain":            "One row per merchandise department.",
        "purpose":          (
            "Merchandise department — third level of hierarchy under group. "
            "Used in department-level sales rollups, forecast graining "
            "(DEPARTMENT_STORE_WEEK), and Top 10 item analysis."
        ),
        "columns": (
            "department_id BIGINT PK, "
            "group_id BIGINT FK→merch_group, "
            "department_code VARCHAR(30) UNIQUE, "
            "department_name VARCHAR(100), "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_PRODUCT (department attributes)",
        "feeds_cdm":        "ProductDimension, DepartmentDimension",
        "metric_formulas":  "",
        "related_dashboards": "Current Top 10 Sale Items, Season Performance",
    },
    {
        "table_name":       "merch_class",
        "subject_area":     "merchandise_hierarchy",
        "category":         "hierarchy",
        "grain":            "One row per merchandise class within a department.",
        "purpose":          (
            "Merchandise class — fourth hierarchy level under department. "
            "Links via department_id. Source for DIM_PRODUCT class-level attributes."
        ),
        "columns": (
            "class_id BIGINT PK, "
            "department_id BIGINT FK→department, "
            "class_code VARCHAR(30), "
            "class_name VARCHAR(100), "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_PRODUCT (class attributes)",
        "feeds_cdm":        "ProductDimension",
        "metric_formulas":  "",
        "related_dashboards": "",
    },
    {
        "table_name":       "merch_subclass",
        "subject_area":     "merchandise_hierarchy",
        "category":         "hierarchy",
        "grain":            "One row per merchandise subclass within a class.",
        "purpose":          (
            "Merchandise subclass — lowest hierarchy level above item. "
            "item.subclass_id is the FK into this table, making merch_subclass "
            "the bridge between item master and the full merchandise hierarchy."
        ),
        "columns": (
            "subclass_id BIGINT PK, "
            "class_id BIGINT FK→merch_class, "
            "subclass_code VARCHAR(30), "
            "subclass_name VARCHAR(100), "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_PRODUCT (subclass attributes)",
        "feeds_cdm":        "ProductDimension",
        "metric_formulas":  "",
        "related_dashboards": "",
    },

    # ── Organization / Location Hierarchy ─────────────────────────────────────
    {
        "table_name":       "org_chain",
        "subject_area":     "organisation_location",
        "category":         "hierarchy",
        "grain":            "One row per retail chain.",
        "purpose":          (
            "Top level of the retail organization hierarchy: Chain → Region → District → Store. "
            "Source for DIM_ORGANISATION / DIM_STORE hierarchy. "
            "Enables chain-wide sales and profit aggregation."
        ),
        "columns": (
            "chain_id BIGINT PK, "
            "chain_code VARCHAR(30) UNIQUE, "
            "chain_name VARCHAR(100), "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_ORGANISATION (chain level)",
        "feeds_cdm":        "OrganisationDimension, StoreDimension",
        "metric_formulas":  "",
        "related_dashboards": "",
    },
    {
        "table_name":       "region",
        "subject_area":     "organisation_location",
        "category":         "hierarchy",
        "grain":            "One row per region within a chain.",
        "purpose":          (
            "Regional level of organisation hierarchy under org_chain. "
            "Supports region-level sales and profit filtering. "
            "Source for DIM_ORGANISATION region attributes."
        ),
        "columns": (
            "region_id BIGINT PK, "
            "chain_id BIGINT FK→org_chain, "
            "region_code VARCHAR(30), "
            "region_name VARCHAR(100), "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_ORGANISATION (region level)",
        "feeds_cdm":        "OrganisationDimension",
        "metric_formulas":  "",
        "related_dashboards": "",
    },
    {
        "table_name":       "district",
        "subject_area":     "organisation_location",
        "category":         "hierarchy",
        "grain":            "One row per district within a region.",
        "purpose":          (
            "District level of the organisation hierarchy between region and store. "
            "Source for DIM_ORGANISATION district attributes."
        ),
        "columns": (
            "district_id BIGINT PK, "
            "region_id BIGINT FK→region, "
            "district_code VARCHAR(30), "
            "district_name VARCHAR(100), "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_ORGANISATION (district level)",
        "feeds_cdm":        "OrganisationDimension",
        "metric_formulas":  "",
        "related_dashboards": "",
    },
    {
        "table_name":       "store",
        "subject_area":     "organisation_location",
        "category":         "master_data",
        "grain":            "One row per physical or logical selling location.",
        "purpose":          (
            "Store/location master — the leaf level of the organisation hierarchy. "
            "Stores store_code, store_name, store_type, channel_code, city, "
            "state_province, country_code, opening_date, closing_date. "
            "Primary source for DIM_STORE / DIM_ORGANISATION dimension table."
        ),
        "columns": (
            "store_id BIGINT PK, "
            "district_id BIGINT FK→district, "
            "store_code VARCHAR(30) UNIQUE, "
            "store_name VARCHAR(150), "
            "store_type VARCHAR(50), "
            "channel_code VARCHAR(30), "
            "city VARCHAR(100), "
            "state_province VARCHAR(100), "
            "country_code VARCHAR(10), "
            "opening_date DATE, "
            "closing_date DATE, "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_STORE, DIM_ORGANISATION",
        "feeds_cdm":        "StoreDimension, OrganisationDimension",
        "metric_formulas":  "",
        "related_dashboards": "Daily Sales & Profit, Current Sales & Profit Contribution",
    },

    # ── Calendar ──────────────────────────────────────────────────────────────
    {
        "table_name":       "business_calendar",
        "subject_area":     "calendar_time",
        "category":         "reference",
        "grain":            "One row per calendar/business date.",
        "purpose":          (
            "Business / fiscal calendar. Enables fiscal time intelligence: WTD, MTD, "
            "YTD, year-over-year comparison, and fiscal period rollups. "
            "Stores fiscal_year, fiscal_quarter, fiscal_month, fiscal_week, "
            "fiscal_day_of_week, calendar_year, week/month/year start and end dates. "
            "Primary source for DIM_BUSINESS_CALENDAR / DIM_TIME dimension table."
        ),
        "columns": (
            "calendar_date DATE PK, "
            "business_date_key INTEGER UNIQUE, "
            "fiscal_year INTEGER, "
            "fiscal_quarter INTEGER, "
            "fiscal_month INTEGER, "
            "fiscal_week INTEGER, "
            "fiscal_day_of_week INTEGER, "
            "calendar_year INTEGER, "
            "calendar_month INTEGER, "
            "calendar_week INTEGER, "
            "day_name VARCHAR(20), "
            "week_start_date DATE, "
            "week_end_date DATE, "
            "month_start_date DATE, "
            "month_end_date DATE, "
            "year_start_date DATE, "
            "year_end_date DATE"
        ),
        "feeds_ldm":        "DIM_BUSINESS_CALENDAR, DIM_TIME",
        "feeds_cdm":        "TimeDimension, CalendarDimension",
        "metric_formulas":  "",
        "related_dashboards": (
            "Markdown to Sales Ratio (WTD/MTD/YTD), Daily Sales & Profit"
        ),
    },

    # ── Price and Cost ────────────────────────────────────────────────────────
    {
        "table_name":       "item_price",
        "subject_area":     "pricing",
        "category":         "master_data",
        "grain":            "One row per item/store/price-type/effective-period.",
        "purpose":          (
            "Current and historical retail prices by item, store, and price type "
            "(REGULAR, PROMOTION, CLEARANCE). Stores selling_price, currency_code, "
            "effective_from, effective_to. Source for price attributes on DIM_ITEM "
            "or a separate DIM_PRICE reference."
        ),
        "columns": (
            "item_price_id BIGINT PK, "
            "item_id BIGINT FK→item, "
            "store_id BIGINT FK→store, "
            "price_type VARCHAR(30) CHECK IN (REGULAR,PROMOTION,CLEARANCE), "
            "selling_price NUMERIC(18,4), "
            "currency_code VARCHAR(10), "
            "effective_from DATE, "
            "effective_to DATE, "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_ITEM (price attributes), DIM_RETAIL_PRICE_TYPE",
        "feeds_cdm":        "ItemDimension, RetailPriceTypeDimension",
        "metric_formulas":  "",
        "related_dashboards": "Markdown to Sales Ratio",
    },
    {
        "table_name":       "item_cost",
        "subject_area":     "costing",
        "category":         "master_data",
        "grain":            "One row per item/store/cost-type/effective-period.",
        "purpose":          (
            "Item unit cost by cost type (STANDARD, LANDED, AVERAGE, REPLACEMENT). "
            "Stores unit_cost, currency_code, effective_from, effective_to. "
            "Used for gross profit and net profit calculations. "
            "Source for cost attributes on DIM_ITEM or FACT_SALES cost metrics."
        ),
        "columns": (
            "item_cost_id BIGINT PK, "
            "item_id BIGINT FK→item, "
            "store_id BIGINT FK→store, "
            "cost_type VARCHAR(30) CHECK IN (STANDARD,LANDED,AVERAGE,REPLACEMENT), "
            "unit_cost NUMERIC(18,4), "
            "currency_code VARCHAR(10), "
            "effective_from DATE, "
            "effective_to DATE, "
            "active_flag CHAR(1)"
        ),
        "feeds_ldm":        "DIM_ITEM (cost attributes), FACT_SALES (cost measures)",
        "feeds_cdm":        "ItemDimension, SalesFact",
        "metric_formulas":  (
            "total_cost_amt = quantity_sold * unit_cost; "
            "gross_profit_amt = net_sales_amt - total_cost_amt"
        ),
        "related_dashboards": "Daily Sales & Profit",
    },
]


def _build_doc(t: dict) -> str:
    """Build rich embedding document text from a table definition dict."""
    parts = [
        f"{t['table_name']} — {t['subject_area']} — OLTP Source Schema",
        f"Purpose: {t['purpose']}",
        f"Grain: {t['grain']}",
        f"Category: {t['category']}",
        f"Columns: {t['columns']}",
    ]
    if t.get("feeds_ldm"):
        parts.append(f"Feeds LDM tables: {t['feeds_ldm']}")
    if t.get("feeds_cdm"):
        parts.append(f"Feeds CDM entities: {t['feeds_cdm']}")
    if t.get("metric_formulas"):
        parts.append(f"Key metric formulas: {t['metric_formulas']}")
    if t.get("related_dashboards"):
        parts.append(f"Related dashboards: {t['related_dashboards']}")
    return "\n".join(parts)


def _get_ef():
    try:
        return embedding_functions.ONNXMiniLM_L6_V2()
    except Exception:
        return embedding_functions.DefaultEmbeddingFunction()


# ── Public API ────────────────────────────────────────────────────────────────

def get_source_summary() -> str:
    """
    Return a compact source-system context string derived directly from
    _TABLE_DEFS — no ChromaDB dependency, always up-to-date.

    Used to inject source table knowledge into CDM entity extraction prompts
    so the LLM knows which fact/dimension entities the source system implies.
    """
    lines = ["SOURCE SYSTEM — Retail Merchandising OLTP tables (use to infer CDM entities):"]
    # Group by category for readability
    order = ["transaction", "snapshot", "planning", "master_data", "hierarchy", "reference"]
    by_cat: dict[str, list] = {}
    for t in _TABLE_DEFS:
        by_cat.setdefault(t["category"], []).append(t)

    for cat in order:
        tables = by_cat.get(cat, [])
        if not tables:
            continue
        label = cat.replace("_", " ").title()
        lines.append(f"\n{label}:")
        for t in tables:
            feeds = t.get("feeds_cdm", "") or t.get("feeds_ldm", "")
            cols_preview = t["columns"].split(", ")[:6]
            cols_str = ", ".join(c.split(" ")[0] for c in cols_preview)
            lines.append(f"  {t['table_name']} -> {feeds}  [{cols_str}...]")

    lines.append(
        "\nInfer CDM entities from these source tables. "
        "Do NOT return source table names as entities — infer the dimensional model entity instead."
    )
    return "\n".join(lines)

def seed_oltp_schema(
    chroma_path: str,
    force: bool = False,
    on_log=None,
) -> int:
    """
    Seed the OLTP source schema into ChromaDB collection 'oltp_source_schema'.
    Returns the number of new documents added (0 if already seeded and force=False).
    """
    def log(msg):
        if on_log: on_log(msg)

    if not _CHROMA_AVAILABLE:
        log("  chromadb not installed — skipping OLTP schema seed")
        return 0

    try:
        client = chromadb.PersistentClient(path=chroma_path)
        ef = _get_ef()
        col = client.get_or_create_collection(name=COLLECTION, embedding_function=ef)

        if col.count() > 0 and not force:
            log(f"  ⚡ OLTP schema already seeded ({col.count()} tables)")
            return 0

        if force:
            try:
                client.delete_collection(COLLECTION)
            except Exception:
                pass
            col = client.get_or_create_collection(name=COLLECTION, embedding_function=ef)

        ids, docs, metas = [], [], []
        for t in _TABLE_DEFS:
            ids.append(t["table_name"])
            docs.append(_build_doc(t))
            metas.append({
                "table_name":   t["table_name"],
                "subject_area": t["subject_area"],
                "category":     t["category"],
                "feeds_ldm":    t.get("feeds_ldm", ""),
                "feeds_cdm":    t.get("feeds_cdm", ""),
                "source":       "OLTP_SOURCE_SCHEMA",
            })

        col.add(ids=ids, documents=docs, metadatas=metas)
        log(f"  ✅ Seeded {len(ids)} OLTP source tables into '{COLLECTION}'")
        return len(ids)

    except Exception as e:
        log(f"  OLTP schema seed error: {e}")
        return 0


def query_oltp_schema(
    query: str,
    chroma_path: str,
    n_results: int = 3,
    category_filter: str = "",
) -> list[dict]:
    """
    Query the OLTP source schema collection for tables relevant to the given query.

    Returns list of dicts: [{table_name, subject_area, category, feeds_ldm, text}, ...]
    Empty list if collection not seeded or chromadb unavailable.
    """
    if not _CHROMA_AVAILABLE:
        return []
    try:
        client = chromadb.PersistentClient(path=chroma_path)
        ef = _get_ef()
        col = client.get_collection(name=COLLECTION, embedding_function=ef)

        where = {"category": {"$eq": category_filter}} if category_filter else None

        kwargs = dict(
            query_texts=[query],
            n_results=min(n_results, col.count() or 1),
            include=["documents", "metadatas", "distances"],
        )
        if where:
            kwargs["where"] = where

        res = col.query(**kwargs)
        out = []
        docs  = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        for doc, meta in zip(docs, metas):
            out.append({
                "table_name":   meta.get("table_name", ""),
                "subject_area": meta.get("subject_area", ""),
                "category":     meta.get("category", ""),
                "feeds_ldm":    meta.get("feeds_ldm", ""),
                "feeds_cdm":    meta.get("feeds_cdm", ""),
                "text":         doc,
            })
        return out
    except Exception:
        return []
