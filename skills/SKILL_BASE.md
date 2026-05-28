---
name: data-modeler-agent
description: >
  Rules, guardrails and ontology constraints for extracting entities from a
  Business Requirements Document and producing a Conceptual Data Model.
  Apply these rules at every stage: extraction, validation, and CDM assembly.
---

# DataModelerAgent — Extraction Rules & Guardrails

## 1. VALID ENTITY TYPES

Only these 4 types are permitted in a Conceptual Data Model:

| Type        | Definition | Examples |
|-------------|-----------|---------|
| `dimension` | A descriptive axis used to slice/filter/group facts. Must represent WHO, WHAT, WHERE, WHEN, or HOW. | Customer, Product, Time, Geography, Channel, Employee, Segment |
| `fact`      | A measurable event or transaction with numeric metrics. Sits at the centre of a star schema. | Sale, Transaction, Payment, Order, Claim, Usage |
| `reference` | A small lookup or classification table with stable values. | Currency, Status, Category, Country, UnitOfMeasure |
| `bridge`    | Resolves a many-to-many relationship between two dimensions. | CustomerProduct, EmployeeRole, OrderPromotion |

## 2. STRICTLY FORBIDDEN ENTITY TYPES

The following are NOT entities — they must NEVER appear in the entity list:

| Forbidden class | Examples | Reason |
|----------------|---------|--------|
| Report names   | SalesReport, CMODashboard, ConsumerSpendingAnalysisReport | Derived outputs, not data entities |
| Dashboard names| ExecutiveDashboard, MarketingPortal, KPIDashboard | UI views, not data entities |
| Filter / prompt names | Top10Filter, DateRangePrompt, RegionFilter | Query parameters, not entities |
| Metric / KPI names | RevenueGrowthRate, NPS, ARPU | These are attributes of a Fact entity |
| Column / field names | CustomerName, OrderDate, ProductID | These are attributes, not entities |
| Verb phrases | DataEntry, Reporting, Processing | Process steps, not entities |
| Abbreviations alone | CMO, BRD, KPI, CRM | Not entities unless qualified |

## 3. ENTITY NAMING RULES (SHACL sh:pattern)

- MUST be PascalCase: `CustomerOrder` not `customer order` or `CUSTOMERORDER`
- MUST be a noun or noun phrase: `Sale` not `Sells`
- MUST be singular: `Product` not `Products`
- MUST NOT contain: spaces, hyphens, slashes, numbers at start, special chars
- MUST NOT end in: `Report`, `Dashboard`, `Summary`, `Analysis`, `View`,
  `Overview`, `Scorecard`, `Monitor`, `Tracker`, `Insight`, `Snapshot`,
  `Filter`, `Prompt`, `Top10`, `KPI`, `Metric`, `Rate`, `Ratio`, `Percentage`
- MAX length: 50 characters

## 4. ENTITY INFERENCE RULES (OWL-style)

When a BRD mentions a report or dashboard, infer the underlying entities:

### Rule R1 — Dimension inference
If a BRD section mentions a report with a subject noun (e.g. "Consumer Spending"),
infer a Dimension entity for the subject: `ConsumerDimension`.

### Rule R2 — Fact inference
If a BRD section mentions metrics, measures, amounts, counts, or rates,
infer a Fact entity: `SpendingFact`, `SaleFact`, `TransactionFact`.

### Rule R3 — Time dimension
Every BRD that mentions dates, periods, months, quarters, or years
MUST include a `TimeDimension` entity.

### Rule R4 — Relationship inference (Property Chain)
If `A hasDimension B` and `A hasDimension C`, infer `B relatesTo C` via the Fact.

### Rule R5 — Bridge inference
If a M:N relationship exists between two Dimensions, infer a Bridge entity.

## 5. RELATIONSHIP RULES

- MUST only exist between entities in the valid entity list
- Dimension → Fact: cardinality 1:N (one dimension member has many facts)
- Fact → Dimension: cardinality N:1
- Reference → Dimension or Fact: cardinality 1:N
- Bridge → Dimension: cardinality N:1 on both sides
- MUST use verb phrases: `has`, `belongs to`, `classifies`, `measures`
- MUST NOT use: report names, filter names, or metric names as relationship endpoints

## 6. VALIDATION CHECKLIST (SHACL shapes)

Before finalising the entity list, check:

- [ ] sh:minCount — at least 1 Fact entity exists
- [ ] sh:minCount — at least 1 Dimension entity exists  
- [ ] sh:pattern — all names are PascalCase
- [ ] sh:in — all types are one of: dimension, fact, reference, bridge
- [ ] sh:not — no entity name ends in a forbidden suffix (see rule 3)
- [ ] sh:uniqueLang — no duplicate entity names
- [ ] sh:minLength — description is not empty
- [ ] owl:FunctionalProperty — each Fact has at least one Dimension relationship

## 7. STAR SCHEMA GUARDRAIL

The CDM must be organisable as a star or snowflake schema:
- Facts sit at the centre
- Dimensions surround the Facts
- References hang off Dimensions or Facts
- Bridges connect two Dimensions through a junction

If the model cannot be drawn as a star/snowflake, flag it for review.

## 8. EXAMPLES

### GOOD entities (from a "Consumer Spending" BRD)
```
ConsumerDimension   (dimension) — who spent
ProductDimension    (dimension) — what was bought
TimeDimension       (dimension) — when it happened
GeographyDimension  (dimension) — where it happened
ChannelDimension    (dimension) — how it was purchased
SpendingFact        (fact)      — the spending transaction
ProductCategory     (reference) — product classification
```

### BAD entities (must be rejected)
```
ConsumerSpendingAnalysisReport  ← report name, FORBIDDEN
Top10Customers                  ← filter/ranking, FORBIDDEN
RevenueGrowthRate               ← metric, FORBIDDEN (attribute of SpendingFact)
CMODashboard                    ← dashboard name, FORBIDDEN
DateRangeFilter                 ← filter, FORBIDDEN
```

## 9. FILTER/PROMPT → DIMENSION INFERENCE RULES (OWL Rule R6)

Filters and Prompts are NOT entities themselves, but they imply Dimension entities.
When a filter or prompt is found, infer the underlying dimension:

| Filter / Prompt pattern | Inferred Dimension |
|------------------------|-------------------|
| Region*, Geography*, Territory*, Area*, Location* | GeographyDimension |
| Date*, DateRange*, Period*, Time*, Month*, Quarter*, Year*, Week* | TimeDimension |
| Product*, Item*, SKU*, Catalogue* | ProductDimension |
| Customer*, Client*, Consumer*, Account* | CustomerDimension |
| Channel*, Store*, Outlet*, Branch* | ChannelDimension |
| Employee*, Agent*, Rep*, Staff* | EmployeeDimension |
| Category*, Segment*, Group*, Class* | CategoryDimension |
| Brand*, Make*, Manufacturer* | BrandDimension |
| Campaign*, Promotion*, Offer* | CampaignDimension |
| Supplier*, Vendor*, Partner* | SupplierDimension |
| Currency*, FX*, Exchange* | CurrencyReference |
| Status*, State*, Flag* | StatusReference |
| Top[N]*, Rank*, Limit* | (no dimension — discard, ranking is not a dimension) |

### Rule R6a — Filter suffix detection
If entity name ends in Filter, Prompt, Selector, Picker, Dropdown, Checkbox, Toggle:
  1. Strip the suffix
  2. Match the remaining word(s) against the table above
  3. Infer the corresponding Dimension or Reference entity
  4. Record the filter as the "source" of the inferred entity
  5. Discard the filter entity itself

### Rule R6b — Prompt prefix/infix detection
If entity name contains Range, Min, Max, From, To, Between:
  Extract the subject noun and infer a Dimension from it.
  Example: DateRangePrompt → subject=Date → TimeDimension

### Rule R6c — Top-N filters
Filters like Top10, TopN, Rank, Limit do NOT imply dimensions.
They are query parameters only. Discard entirely.
