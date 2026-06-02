# LDM Naming Conventions
# DataModelerAgent — Logical Data Model
# This file is the single authoritative source for all LDM naming rules.
# Referenced by: step_ldm_promote.py, step_ldm_ddl.py, step_ldm_scd.py, step_ldm_ddl.py
# Update this file to change naming conventions project-wide.

---

## 1. TABLE PREFIX CONVENTIONS

| Entity Type   | Prefix     | Example                    | Notes                              |
|---------------|------------|----------------------------|------------------------------------|
| Dimension     | `DIM_`     | `DIM_PRODUCT`              | SCD1 or SCD2 descriptive tables    |
| Fact          | `FACT_`    | `FACT_SALES`               | Measurable event/transaction tables|
| Bridge        | `BRIDGE_`  | `BRIDGE_ITEM_SEASON`       | Resolves M:N between dimensions    |
| Reference     | `REF_`     | `REF_CURRENCY`             | Small static lookup tables         |
| Aggregate     | `AGG_`     | `AGG_SALES_WEEKLY`         | Pre-aggregated performance tables  |
| View (As-Is)  | `V_`       | `V_SALES_AS_IS`            | Subject area database views        |
| View (As-Was) | `V_`       | `V_SALES_AS_WAS`           | SCD2 historical view               |
| View (PIT)    | `V_`       | `V_SALES_POINT_IN_TIME`    | Point-in-time bind variable view   |
| Staging       | `STG_`     | `STG_SALES`                | ETL staging tables (pre-load)      |
| ETL Control   | `ETL_`     | `ETL_BATCH_STATUS`         | Pipeline control and audit tables  |

### Rules
- ALL prefixes MUST be UPPER_SNAKE_CASE
- NEVER omit the prefix — `PRODUCT` alone is INVALID, `DIM_PRODUCT` is VALID
- NEVER use: `T_`, `TB_`, `TBL_`, `FCT_`, `FT_`, `D_`, `F_` — these are FORBIDDEN abbreviations
- Table name after prefix must also be UPPER_SNAKE_CASE nouns (no verbs)

---

## 2. COLUMN NAMING CONVENTIONS

### Primary keys
- Format:   `<TABLE_SHORT_NAME>_KEY`
- Type:     Surrogate integer (NUMBER(18) or BIGINT)
- Examples: `PRODUCT_KEY`, `ORG_KEY`, `DATE_KEY`, `PRICE_TYPE_KEY`
- Rules:    NEVER use natural key as PK in dimension tables (use surrogate)

### Natural / business keys
- Format:   `<ENTITY>_ID` or `<ENTITY>_CODE`
- Type:     VARCHAR2 or NUMBER matching source system
- Examples: `ITEM_ID`, `STORE_ID`, `SEASON_ID`, `CURRENCY_CODE`
- Rules:    Always include alongside surrogate key for traceability

### Foreign keys
- Format:   MUST match the PK column name exactly in the referenced table
- Examples: `PRODUCT_KEY` in FACT_SALES references `PRODUCT_KEY` in DIM_PRODUCT
- Rules:    FK column name = PK column name of referenced table (no aliases)

### SCD2 columns (all SCD2 dimension tables MUST include)
- `EFFECTIVE_DATE`   DATE        NOT NULL   — when this version became active
- `EXPIRY_DATE`      DATE        NOT NULL   — when this version was superseded (9999-12-31 for current)
- `CURRENT_FLAG`     CHAR(1)     NOT NULL   — 'Y' for current record, 'N' for historical
- `LOAD_DATE`        DATE        DEFAULT SYSDATE — when row was loaded

### Metric / measure columns (fact tables)
- Amounts:      `NUMBER(18,4)` — e.g. `NET_SALES_AMT`, `GROSS_PROFIT_AMT`
- Quantities:   `NUMBER(12,2)` — e.g. `NET_SALES_QTY`, `RETURN_QTY`
- Ratios/Pct:   `NUMBER(10,6)` — e.g. `GROSS_MARGIN_PCT`, `SALES_CONTRIB_DIV`
- Counts:       `NUMBER(10)`   — e.g. `TRANSACTION_COUNT`
- LY variants:  suffix `_LY`   — e.g. `NET_SALES_AMT_LY`
- Variance:     suffix `_VAR_LY` — e.g. `NET_SALES_AMT_VAR_LY`
- WTD/MTD/YTD:  suffix `_WTD`, `_MTD`, `_YTD` — pre-aggregated time series

### Standard metadata columns (all tables)
- `SOURCE_SYSTEM_CODE`   VARCHAR2(10)   — source system identifier (ReSA/RMS/MFP/ReIM/RPM)
- `LOAD_DATE`            DATE           — ETL load timestamp

### Analysis mode (fact tables with As-Is/As-Was/PIT support)
- `ANALYSIS_MODE_CODE`   VARCHAR2(15)   — values: 'AS_IS' / 'AS_WAS' / 'POINT_IN_TIME'

---

## 3. STANDARD COLUMN NAME ALIASES

Use these canonical names — do NOT invent alternatives.

| Concept                  | Canonical column name      | FORBIDDEN alternatives              |
|--------------------------|----------------------------|-------------------------------------|
| Product surrogate key    | `PRODUCT_KEY`              | `PROD_KEY`, `ITEM_KEY`, `P_KEY`     |
| Organisation surrogate   | `ORG_KEY`                  | `STORE_KEY`, `LOC_KEY`, `O_KEY`     |
| Date surrogate key       | `DATE_KEY`                 | `TIME_KEY`, `CAL_KEY`, `D_KEY`      |
| Price type surrogate     | `PRICE_TYPE_KEY`           | `PT_KEY`, `PTYPE_KEY`               |
| Item natural key         | `ITEM_ID`                  | `ITEM_CODE`, `SKU`, `SKU_ID`        |
| Store natural key        | `STORE_ID`                 | `LOCATION_ID`, `LOC_ID`             |
| Current record flag      | `CURRENT_FLAG`             | `IS_CURRENT`, `CURR_FLG`, `ACTIVE`  |
| SCD2 start date          | `EFFECTIVE_DATE`           | `START_DATE`, `FROM_DATE`           |
| SCD2 end date            | `EXPIRY_DATE`              | `END_DATE`, `TO_DATE`, `UNTIL_DATE` |
| Comp store indicator     | `COMP_STORE_FLAG`          | `IS_COMP`, `COMP_FLAG`              |
| Analysis mode            | `ANALYSIS_MODE_CODE`       | `SUBJECT_AREA`, `VIEW_TYPE`         |

---

## 4. SCHEMA CONVENTION

- Schema name:  `MERCH_DW`
- All tables:   `MERCH_DW.<TABLE_NAME>`
- All views:    `MERCH_DW.<VIEW_NAME>`
- Constraint prefix PK:   `PK_<TABLE_NAME>`
- Constraint prefix FK:   `FK_<TABLE_NAME>_<COL_NAME>`
- Constraint prefix UK:   `UK_<TABLE_NAME>_<COL_NAME>`
- Constraint prefix CK:   `CK_<TABLE_NAME>_<COL_NAME>`
- Index prefix:           `IDX_<TABLE_NAME>_<COL_NAME>`

---

## 5. ALIAS MAP — TABLE NAME CORRECTIONS

LLM-generated names must be corrected to these canonical names:

### Dimension aliases
| LLM may return              | Correct canonical name      |
|-----------------------------|------------------------------|
| `PRODUCT`                   | `DIM_PRODUCT`                |
| `PRODUCTS`                  | `DIM_PRODUCT`                |
| `PRODUCT_DIMENSION`         | `DIM_PRODUCT`                |
| `ORGANISATION`              | `DIM_ORGANISATION`           |
| `ORGANIZATION`              | `DIM_ORGANISATION`           |
| `STORE`                     | `DIM_ORGANISATION`           |
| `LOCATION`                  | `DIM_ORGANISATION`           |
| `CALENDAR`                  | `DIM_BUSINESS_CALENDAR`      |
| `TIME`                      | `DIM_BUSINESS_CALENDAR`      |
| `DATE`                      | `DIM_BUSINESS_CALENDAR`      |
| `BUSINESS_CALENDAR`         | `DIM_BUSINESS_CALENDAR`      |
| `FISCAL_CALENDAR`           | `DIM_BUSINESS_CALENDAR`      |
| `SEASON`                    | `DIM_PRODUCT_SEASON`         |
| `PRODUCT_SEASON`            | `DIM_PRODUCT_SEASON`         |
| `RETAIL_TYPE`               | `DIM_RETAIL_PRICE_TYPE`      |
| `PRICE_TYPE`                | `DIM_RETAIL_PRICE_TYPE`      |

### Fact aliases
| LLM may return              | Correct canonical name       |
|-----------------------------|-------------------------------|
| `SALES`                     | `FACT_SALES`                  |
| `SALE`                      | `FACT_SALES`                  |
| `SALES_FACT`                | `FACT_SALES`                  |
| `MARKDOWN`                  | `FACT_MARKDOWN`               |
| `MARKDOWNS`                 | `FACT_MARKDOWN`               |
| `MARKDOWN_FACT`             | `FACT_MARKDOWN`               |
| `FORECAST`                  | `FACT_SALES_FORECAST`         |
| `SALES_FORECAST`            | `FACT_SALES_FORECAST`         |
| `SUPPLIER_COST`             | `FACT_SUPPLIER_COST`          |
| `SUPPLIER`                  | `FACT_SUPPLIER_COST`          |
| `COST`                      | `FACT_SUPPLIER_COST`          |
| `CURRENCY_CONVERSION`       | `FACT_CURRENCY_CONVERSION`    |
| `CURRENCY`                  | `FACT_CURRENCY_CONVERSION`    |

---

## 6. SCD TYPE ASSIGNMENTS

| Dimension table             | SCD Type | Reason                                     |
|-----------------------------|----------|--------------------------------------------|
| `DIM_PRODUCT`               | SCD2     | Product reclassification tracked (FR-018)  |
| `DIM_ORGANISATION`          | SCD2     | Store reclassification tracked (FR-018)    |
| `DIM_BUSINESS_CALENDAR`     | SCD1     | Calendar never changes historically        |
| `DIM_PRODUCT_SEASON`        | SCD1     | Season dates are fixed once defined        |
| `DIM_RETAIL_PRICE_TYPE`     | SCD1     | Static lookup — only 3 values              |

---

## 7. GRAIN DECLARATIONS

| Fact table                  | Grain                                      | Additive |
|-----------------------------|---------------------------------------------|----------|
| `FACT_SALES`                | Item × Location × Day × Price Type         | Additive |
| `FACT_MARKDOWN`             | Item × Location × Week × Price Type        | Additive |
| `FACT_SALES_FORECAST`       | Item × Location × Week                     | Additive |
| `FACT_SUPPLIER_COST`        | Item × Supplier × Period                   | Additive |
| `FACT_CURRENCY_CONVERSION`  | From-Currency × Currency Type × Date       | —        |
| `AGG_SALES_WEEKLY`          | Subclass × Location × Week × Price Type    | Additive |

---

## 8. FORBIDDEN ENTITY PATTERNS

The following patterns must NEVER become CDM/LDM entities:

| Pattern               | Reason                                      |
|-----------------------|---------------------------------------------|
| `*Report`             | Derived output — not a data entity          |
| `*Dashboard`          | Derived output — not a data entity          |
| `*Scorecard`          | Derived output — not a data entity          |
| `*Analysis`           | Process — not a data entity                 |
| `*Summary`            | Derived output — not a data entity          |
| `*View`               | Database object — not a logical entity      |
| `*Analytics`          | Derived output — not a data entity          |
| `Top10*`              | Ranking — not a data entity                 |
| `*KPI`                | Metric name — attribute of fact, not entity |
| `*Metric`             | Metric name — attribute of fact, not entity |
| `*Rate`               | Ratio — attribute of fact, not entity       |
| `*Ratio`              | Ratio — attribute of fact, not entity       |
| `*Percentage`         | Ratio — attribute of fact, not entity       |

### Filter / Prompt rule
Filters and Prompts are NOT forbidden — they imply Dimension entities:
- `RegionFilter`      → `DIM_ORGANISATION`
- `DateRangePrompt`   → `DIM_BUSINESS_CALENDAR`
- `ProductFilter`     → `DIM_PRODUCT`
- `Top10Filter`       → DISCARD (Top-N rankings have no implied dimension)

---

## 9. MANDATORY CONFORMED DIMENSIONS

Every fact table MUST be connected to these conformed dimensions.
This is enforced by the pipeline — missing connections are auto-repaired.

| Dimension                  | FK Column          | Applies to                    |
|----------------------------|--------------------|-------------------------------|
| `DIM_BUSINESS_CALENDAR`    | `DATE_KEY`         | ALL fact tables               |
| `DIM_ORGANISATION`         | `ORG_KEY`          | ALL fact tables               |
| `DIM_PRODUCT`              | `PRODUCT_KEY`      | ALL fact tables except currency|

### Mandatory FK columns on ALL fact tables
Every FACT_ table MUST include these columns:
- `DATE_KEY        NUMBER(8)     NOT NULL`  FK to DIM_BUSINESS_CALENDAR
- `ORG_KEY         NUMBER(18)    NOT NULL`  FK to DIM_ORGANISATION
- `PRODUCT_KEY     NUMBER(18)    NOT NULL`  FK to DIM_PRODUCT (except FACT_CURRENCY_CONVERSION)

### Mandatory relationships
Every FACT_ table MUST have relationships declared:
- DIM_BUSINESS_CALENDAR  ||--}o  FACT_*  : "dates"
- DIM_ORGANISATION       ||--}o  FACT_*  : "locates"
- DIM_PRODUCT            ||--}o  FACT_*  : "classifies"  (except FACT_CURRENCY_CONVERSION)

### Department connection
Department is part of DIM_PRODUCT hierarchy (DEPT_ID column).
When reports reference "Department dimension", they use DIM_PRODUCT filtered at dept level.
There is NO separate DIM_DEPARTMENT table — department is an attribute of DIM_PRODUCT.

