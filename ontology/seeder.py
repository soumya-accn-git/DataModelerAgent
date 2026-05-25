"""
Ontology seeder
Loads a curated subset of schema.org concepts into ChromaDB.
Run once from the sidebar before using the app.
"""

import chromadb
from chromadb.utils import embedding_functions

COLLECTION_NAME = "ontology_concepts"

# ─── Curated schema.org concepts ──────────────────────────────────────────────
# Format: (id, label, description, concept_type)
# concept_type: "class" for entity concepts, "property" for relationship concepts

SCHEMA_ORG_CONCEPTS = [
    # ── Core business entities (classes) ──────────────────────────────────
    ("schema:Person",           "Person",           "A person (alive, dead, undead, or fictional).", "class"),
    ("schema:Organization",     "Organization",     "An organization such as a school, NGO, corporation, club, etc.", "class"),
    ("schema:Employee",         "Employee",         "A person employed by an organization.", "class"),
    ("schema:Customer",         "Customer",         "A person or organization that purchases goods or services.", "class"),
    ("schema:User",             "User",             "A registered user of a system or platform.", "class"),
    ("schema:Product",          "Product",          "Any offered product or service.", "class"),
    ("schema:Service",          "Service",          "A service provided by an organization.", "class"),
    ("schema:Order",            "Order",            "An order is a confirmation of a purchase.", "class"),
    ("schema:Invoice",          "Invoice",          "A statement of the money due for goods or services.", "class"),
    ("schema:Payment",          "Payment",          "A payment or charge for a service or product.", "class"),
    ("schema:Transaction",      "Transaction",      "A financial transaction between parties.", "class"),
    ("schema:Contract",         "Contract",         "A legal agreement between parties.", "class"),
    ("schema:Project",          "Project",          "An enterprise carefully planned to achieve a goal.", "class"),
    ("schema:Task",             "Task",             "A piece of work to be done.", "class"),
    ("schema:Event",            "Event",            "An event happening at a certain time and location.", "class"),
    ("schema:Place",            "Place",            "Entities with a physical location.", "class"),
    ("schema:Address",          "PostalAddress",    "A mailing address.", "class"),
    ("schema:Offer",            "Offer",            "An offer to transfer some rights.", "class"),
    ("schema:Category",         "Category",         "A classification or grouping.", "class"),
    ("schema:Tag",              "Tag",              "A label attached to an entity.", "class"),
    ("schema:Document",         "Document",         "A written or printed paper.", "class"),
    ("schema:Report",           "Report",           "A formal document summarizing results.", "class"),
    ("schema:Message",          "Message",          "A single message object.", "class"),
    ("schema:Notification",     "Notification",     "A notification sent to a user.", "class"),
    ("schema:Role",             "Role",             "The function assumed or part played by a person.", "class"),
    ("schema:Permission",       "Permission",       "An access right or permission.", "class"),
    ("schema:Department",       "Department",       "A division of an organization.", "class"),
    ("schema:Warehouse",        "Warehouse",        "A storage facility for goods.", "class"),
    ("schema:Inventory",        "Inventory",        "The goods in stock at a location.", "class"),
    ("schema:Shipment",         "Shipment",         "A batch of goods sent at one time.", "class"),
    ("schema:Supplier",         "Supplier",         "An entity that provides goods or services.", "class"),
    ("schema:Review",           "Review",           "A review of an item.", "class"),
    ("schema:Rating",           "Rating",           "A rating for a product or service.", "class"),
    ("schema:Account",          "Account",          "A user account or financial account.", "class"),
    ("schema:Subscription",     "Subscription",     "A subscription to a service.", "class"),
    ("schema:Campaign",         "Campaign",         "A marketing or sales campaign.", "class"),
    ("schema:Lead",             "Lead",             "A potential customer.", "class"),
    ("schema:Ticket",           "Ticket",           "A support or issue ticket.", "class"),
    ("schema:Asset",            "Asset",            "A tangible or intangible asset.", "class"),
    ("schema:Budget",           "Budget",           "A financial budget or allocation.", "class"),

    # ── Relationship property types ────────────────────────────────────────
    ("schema:memberOf",         "memberOf",         "An organization (or program membership) to which this person belongs.", "property"),
    ("schema:hasPart",          "hasPart",          "Indicates an item or part that is a constituent of another.", "property"),
    ("schema:isPartOf",         "isPartOf",         "Indicates an item that this item is part of.", "property"),
    ("schema:owns",             "owns",             "Products or services owned by the subject.", "property"),
    ("schema:provider",         "provider",         "The service provider or organization providing a service.", "property"),
    ("schema:customer",         "customer",         "Party placing the order or paying for the service.", "property"),
    ("schema:seller",           "seller",           "An entity which offers a product or service for sale.", "property"),
    ("schema:buyer",            "buyer",            "An entity that buys something.", "property"),
    ("schema:supplier",         "supplier",         "A supplier of the product.", "property"),
    ("schema:author",           "author",           "The author of this content.", "property"),
    ("schema:employee",         "employee",         "Someone working for this organization.", "property"),
    ("schema:worksFor",         "worksFor",         "Organizations that the person works for.", "property"),
    ("schema:subOrganization",  "subOrganization",  "A relationship between two organizations.", "property"),
    ("schema:parentOrganization","parentOrganization","The larger organization that this organization is a subOrganization of.", "property"),
    ("schema:orderItem",        "orderItem",        "The item ordered.", "property"),
    ("schema:orderedItem",      "orderedItem",      "The item(s) within the order.", "property"),
    ("schema:partOfOrder",      "partOfOrder",      "The overall order the items are part of.", "property"),
    ("schema:broker",           "broker",           "An entity that arranges for an exchange.", "property"),
    ("schema:paymentMethod",    "paymentMethod",    "The name of the credit card or other method of payment.", "property"),
    ("schema:containsPlace",    "containsPlace",    "The place that is spatially contained in another.", "property"),
    ("schema:location",         "location",         "The location of, for example, where an event is happening.", "property"),
    ("schema:about",            "about",            "The subject matter of the content.", "property"),
    ("schema:mentions",         "mentions",         "Indicates that the resource is related to a topic.", "property"),
    ("schema:relatedTo",        "relatedTo",        "A generic relationship between two entities.", "property"),
    ("schema:sameAs",           "sameAs",           "Indicates that the resource is the same as another.", "property"),
    ("schema:identifier",       "identifier",       "The identifier property represents any kind of identifier.", "property"),
    ("schema:name",             "name",             "The name of the item.", "property"),
    ("schema:description",      "description",      "A description of the item.", "property"),
]


def seed_ontology(chroma_path: str) -> int:
    """
    Seed ChromaDB with schema.org ontology concepts.
    Idempotent — clears and recreates the collection each time.

    Returns:
        Number of concepts seeded.
    """
    client = chromadb.PersistentClient(path=chroma_path)
    ef = embedding_functions.DefaultEmbeddingFunction()

    # Drop and recreate for idempotency
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    ids = []
    documents = []
    metadatas = []

    for concept_id, label, description, concept_type in SCHEMA_ORG_CONCEPTS:
        ids.append(concept_id)
        # Document text used for embedding
        documents.append(f"{label}: {description}")
        metadatas.append({
            "label": label,
            "description": description,
            "concept_type": concept_type,
            "uri": f"https://schema.org/{label}",
        })

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    return len(ids)
