"""
ARTS ODM v7.3 Gap Seeder — seeds ChromaDB with entity definitions for the 7 subject
areas present in the ARTS Retail Operational Data Model v7.3 (OMG) but absent from
the Oracle RDM seed data:

  1. Fresh Item Management
  2. Language / Internationalization
  3. Weather Reference
  4. Consumer-Customer Journey
  5. Currency
  6. Assets and Equipment
  7. Stored Value Instruments

Source: https://www.omg.org/retail-depository/arts-odm-73/hmcontent.htm
Collection: arts_odm_gaps
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

COLLECTION = "arts_odm_gaps"

# ── Entity catalogue ──────────────────────────────────────────────────────────
# Each entry: name, type, subject_area, brd_domain (Y/N), description

ARTS_GAP_ENTITIES = [

    # ── 1. Fresh Item Management (Logical 21000) ─────────────────────────────
    {
        "name": "FreshItem",
        "type": "Base",
        "subject_area": "Fresh Item Management",
        "brd_domain": "Y",
        "description": (
            "Represents a perishable or variable-weight item sold by weight or with "
            "a limited shelf life. Extends the standard Item entity with freshness "
            "lifecycle attributes including pack date, sell-by date, and harvest date. "
            "Supports shrink tracking, tare weight, and catch-weight pricing."
        ),
    },
    {
        "name": "FreshItemLot",
        "type": "Base",
        "subject_area": "Fresh Item Management",
        "brd_domain": "Y",
        "description": (
            "Tracks a production lot or batch of fresh items from receipt through sale. "
            "Records lot number, pack date, expiry date, quantity received, quantity sold, "
            "and quantity shrunk. Links to FreshItem and InventoryLocation for traceability."
        ),
    },
    {
        "name": "FreshItemShrink",
        "type": "Derived",
        "subject_area": "Fresh Item Management",
        "brd_domain": "Y",
        "description": (
            "Captures shrink events for fresh items — spoilage, theft, and trim loss. "
            "Records shrink type, quantity, cost value, and reason code. Used for "
            "gross-margin reporting and fresh department performance analytics."
        ),
    },
    {
        "name": "FreshMarkdown",
        "type": "Base",
        "subject_area": "Fresh Item Management",
        "brd_domain": "Y",
        "description": (
            "Defines time-triggered markdown rules applied to fresh items approaching "
            "their sell-by date. Specifies the markdown percentage or amount, the "
            "hours-before-expiry trigger, and the target selling price. Relates to "
            "PriceDerivationRule for execution at POS."
        ),
    },
    {
        "name": "CatchWeightCapture",
        "type": "Reference",
        "subject_area": "Fresh Item Management",
        "brd_domain": "Y",
        "description": (
            "Records the actual weight captured at point of sale or at the scale for "
            "a catch-weight fresh item. Stores unit-of-measure, tare weight, gross weight, "
            "and net weight. Used to calculate the exact line-item price for variable-weight "
            "products such as deli meats, seafood, and produce."
        ),
    },

    # ── 2. Language / Internationalization (Logical 06600) ───────────────────
    {
        "name": "LanguageCode",
        "type": "Reference",
        "subject_area": "Language",
        "brd_domain": "N",
        "description": (
            "ISO 639-1 / 639-2 language code reference table. Identifies every language "
            "supported by the enterprise for customer communications, receipts, signage, "
            "and reporting. Includes language name, locale code, and character-set encoding."
        ),
    },
    {
        "name": "LocalizedItemDescription",
        "type": "Reference",
        "subject_area": "Language",
        "brd_domain": "N",
        "description": (
            "Stores translated item names and descriptions for each supported language. "
            "One row per item per language. Supports multi-language shelf labels, "
            "receipts, and e-commerce product pages. Foreign key to Item and LanguageCode."
        ),
    },
    {
        "name": "LocalizedOrganizationName",
        "type": "Reference",
        "subject_area": "Language",
        "brd_domain": "N",
        "description": (
            "Provides translated names for business units, banners, and store names "
            "in each supported locale. Used for customer-facing display in multilingual "
            "markets. Foreign key to OrganizationBusinessUnit and LanguageCode."
        ),
    },

    # ── 3. Weather Reference (Logical 10102) ─────────────────────────────────
    {
        "name": "WeatherStation",
        "type": "Reference",
        "subject_area": "Weather Reference",
        "brd_domain": "N",
        "description": (
            "Identifies a weather observation station linked to one or more retail "
            "store locations. Records station ID, provider name, geographic coordinates, "
            "and the nearest trade area. Enables weather-adjusted sales forecasting."
        ),
    },
    {
        "name": "WeatherObservation",
        "type": "Base",
        "subject_area": "Weather Reference",
        "brd_domain": "N",
        "description": (
            "Daily or hourly weather reading from a WeatherStation. Stores temperature "
            "(high/low/mean), precipitation, snowfall, wind speed, and a general "
            "condition code (Sunny, Rainy, Snowy, etc.). Joined to Calendar and "
            "OrganizationLocation for store-level weather analytics."
        ),
    },
    {
        "name": "WeatherImpactFactor",
        "type": "Derived",
        "subject_area": "Weather Reference",
        "brd_domain": "N",
        "description": (
            "Pre-computed coefficient expressing the historical relationship between "
            "a specific weather condition and sales lift or depression for a product "
            "category at a trade area. Used as an input feature in sales forecasting "
            "and promotional planning models."
        ),
    },

    # ── 4. Consumer-Customer Journey (Logical 07017) ──────────────────────────
    {
        "name": "CustomerJourneySession",
        "type": "Base",
        "subject_area": "Consumer-Customer Journey",
        "brd_domain": "Y",
        "description": (
            "Represents a single omnichannel engagement session for a customer — a "
            "contiguous sequence of touchpoint interactions across one or more channels "
            "(web, app, in-store, call centre). Records session start/end timestamps, "
            "channel origin, device type, and whether the session resulted in a purchase."
        ),
    },
    {
        "name": "JourneyTouchpoint",
        "type": "Base",
        "subject_area": "Consumer-Customer Journey",
        "brd_domain": "Y",
        "description": (
            "A single interaction event within a CustomerJourneySession — a page view, "
            "product search, add-to-cart, store visit, or call-centre contact. Stores "
            "touchpoint type, channel, timestamp, item or category browsed, and the "
            "action taken. Links to CustomerJourneySession and ChannelTouchpoint."
        ),
    },
    {
        "name": "JourneyStage",
        "type": "Reference",
        "subject_area": "Consumer-Customer Journey",
        "brd_domain": "Y",
        "description": (
            "Lookup for the stage in the customer decision journey — Awareness, "
            "Consideration, Intent, Purchase, Loyalty. Assigned to JourneyTouchpoint "
            "records by an ML classification model or rule engine. Drives funnel "
            "reporting and marketing attribution."
        ),
    },
    {
        "name": "ChannelTouchpoint",
        "type": "Reference",
        "subject_area": "Consumer-Customer Journey",
        "brd_domain": "Y",
        "description": (
            "Reference table for the specific channel and medium of a customer "
            "interaction — e.g. Mobile App / iOS, Website / Desktop, Physical Store, "
            "Email / Promotional, Social / Paid. Used to classify JourneyTouchpoint "
            "records and build cross-channel attribution reports."
        ),
    },
    {
        "name": "JourneyConversionEvent",
        "type": "Derived",
        "subject_area": "Consumer-Customer Journey",
        "brd_domain": "Y",
        "description": (
            "Records a conversion milestone within a journey — add-to-cart, checkout "
            "start, order placement, or in-store purchase. Links the converting "
            "JourneySession to the resulting RetailTransaction or CustomerOrder, "
            "enabling last-touch and multi-touch attribution analysis."
        ),
    },

    # ── 5. Currency (Logical 10104) ───────────────────────────────────────────
    {
        "name": "CurrencyType",
        "type": "Reference",
        "subject_area": "Currency",
        "brd_domain": "Y",
        "description": (
            "ISO 4217 currency code reference. Stores currency code (e.g. USD, GBP, EUR), "
            "currency name, symbol, and number of decimal places. Used on all monetary "
            "fact columns and exchange-rate lookups across the enterprise data model."
        ),
    },
    {
        "name": "CurrencyExchangeRate",
        "type": "Base",
        "subject_area": "Currency",
        "brd_domain": "Y",
        "description": (
            "Daily exchange rate between a source currency and the enterprise base "
            "currency. Records the effective date, rate type (spot, mid, closing), "
            "bid rate, ask rate, and mid rate. Used to convert foreign-currency "
            "transactions to reporting currency for consolidated financial reporting."
        ),
    },

    # ── 6. Assets and Equipment (Logical 06400) ───────────────────────────────
    {
        "name": "StoreAsset",
        "type": "Base",
        "subject_area": "Assets and Equipment",
        "brd_domain": "N",
        "description": (
            "A capitalised physical asset owned or leased by a retail store — fixtures, "
            "refrigeration units, POS terminals, scales, and self-checkout kiosks. "
            "Records asset ID, description, acquisition date, cost, current book value, "
            "depreciation method, and assigned store location."
        ),
    },
    {
        "name": "AssetType",
        "type": "Reference",
        "subject_area": "Assets and Equipment",
        "brd_domain": "N",
        "description": (
            "Classification lookup for store assets. Defines asset category "
            "(IT Equipment, Refrigeration, Fixture, Vehicle), useful life in years, "
            "default depreciation method (straight-line, reducing-balance), and the "
            "GL account code for asset capitalization."
        ),
    },
    {
        "name": "AssetMaintenanceEvent",
        "type": "Base",
        "subject_area": "Assets and Equipment",
        "brd_domain": "N",
        "description": (
            "Records a planned or unplanned maintenance event against a StoreAsset. "
            "Stores event type (preventive, corrective, inspection), scheduled and "
            "actual date, technician, cost, and outcome. Used for total-cost-of-ownership "
            "reporting and asset replacement planning."
        ),
    },

    # ── 7. Stored Value Instruments (Logical 01420) ───────────────────────────
    {
        "name": "StoredValueInstrument",
        "type": "Base",
        "subject_area": "Stored Value Instruments",
        "brd_domain": "Y",
        "description": (
            "Represents a gift card, store credit voucher, or prepaid payment card "
            "issued by the retailer. Stores instrument ID, type, issue date, initial "
            "value, current balance, expiry date, and status (Active, Redeemed, Expired, "
            "Blocked). The central entity for stored-value liability reporting."
        ),
    },
    {
        "name": "StoredValueInstrumentType",
        "type": "Reference",
        "subject_area": "Stored Value Instruments",
        "brd_domain": "Y",
        "description": (
            "Classifies stored value instruments — Physical Gift Card, eGift Card, "
            "Store Credit, Loyalty Points Wallet, Prepaid Debit. Defines whether the "
            "instrument is reloadable, transferable, and whether balances expire."
        ),
    },
    {
        "name": "StoredValueTransaction",
        "type": "Base",
        "subject_area": "Stored Value Instruments",
        "brd_domain": "Y",
        "description": (
            "Records every debit (redemption) or credit (activation, reload, refund) "
            "against a StoredValueInstrument. Stores transaction type, amount, resulting "
            "balance, retail transaction reference, store, and timestamp. Provides the "
            "full audit trail for stored-value liability reconciliation."
        ),
    },
    {
        "name": "StoredValueLiabilitySnapshot",
        "type": "Aggregate",
        "subject_area": "Stored Value Instruments",
        "brd_domain": "Y",
        "description": (
            "Daily or weekly aggregate of total outstanding stored-value liability — "
            "sum of all active instrument balances by instrument type and issuing store. "
            "Used for financial close, breakage revenue recognition, and regulatory "
            "reporting on unclaimed property / escheatment obligations."
        ),
    },
]


# ── Seeder ────────────────────────────────────────────────────────────────────

def _get_ef():
    from chromadb.utils import embedding_functions
    try:
        return embedding_functions.ONNXMiniLM_L6_V2()
    except Exception:
        return embedding_functions.DefaultEmbeddingFunction()


def _entity_text(e: dict) -> str:
    scope = "In scope" if e["brd_domain"] == "Y" else "Out of scope"
    return (
        f"ARTS ODM v7.3 Entity: {e['name']}\n"
        f"Type: {e['type']}\n"
        f"Subject Area: {e['subject_area']}\n"
        f"BRD Domain: {scope} — Merchandising Sales & Profit\n"
        f"Description: {e['description']}"
    )


def seed_arts_odm_gaps(
    chroma_path: str = "./chroma_db",
    force:       bool = False,
    on_log             = None,
) -> int:
    """
    Seed the ARTS ODM v7.3 gap entities into ChromaDB collection 'arts_odm_gaps'.
    Returns number of new documents seeded (0 if already seeded and force=False).
    """
    def log(msg):
        if on_log: on_log(msg)

    import chromadb

    ef     = _get_ef()
    client = chromadb.PersistentClient(path=chroma_path)
    col    = client.get_or_create_collection(COLLECTION, embedding_function=ef)

    if not force and col.count() >= len(ARTS_GAP_ENTITIES):
        log(f"⚡ arts_odm_gaps already seeded ({col.count()} docs) — skipping")
        return 0

    if force:
        client.delete_collection(COLLECTION)
        col = client.get_or_create_collection(COLLECTION, embedding_function=ef)

    ids, docs, metas = [], [], []
    for i, e in enumerate(ARTS_GAP_ENTITIES):
        ids.append(f"arts_gap_{i:03d}")
        docs.append(_entity_text(e))
        metas.append({
            "name":         e["name"],
            "type":         e["type"],
            "subject_area": e["subject_area"],
            "brd_domain":   e["brd_domain"],
            "source":       "ARTS ODM v7.3",
        })

    col.add(ids=ids, documents=docs, metadatas=metas)
    log(f"Seeded {len(ids)} ARTS ODM v7.3 gap entities into '{COLLECTION}'")
    return len(ids)


def query_arts_odm_gaps(
    query_text:  str,
    chroma_path: str  = "./chroma_db",
    n_results:   int  = 5,
    brd_only:    bool = True,
) -> list[dict]:
    """Query the ARTS ODM gap collection for entities similar to query_text."""
    import chromadb

    ef     = _get_ef()
    client = chromadb.PersistentClient(path=chroma_path)
    col    = client.get_or_create_collection(COLLECTION, embedding_function=ef)

    if col.count() == 0:
        return []

    where = {"brd_domain": "Y"} if brd_only else None
    kwargs = {"query_texts": [query_text], "n_results": min(n_results, col.count())}
    if where:
        kwargs["where"] = where

    res = col.query(**kwargs)
    out = []
    for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
        out.append({"text": doc, **meta})
    return out
