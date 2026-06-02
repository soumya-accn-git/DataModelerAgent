import os
from langchain_community.graphs import Neo4jGraph
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document

# 1. Configure your API keys and Neo4j connection details
os.environ["OPENAI_API_KEY"] = "your-openai-api-key"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "afwFN2cmb4iUaefJsS23C2yJsh6-tvrXid75FkGQx1s"

# 2. Connect to the Neo4j Database instance
graph = Neo4jGraph(
    url=NEO4J_URI, 
    username=NEO4J_USERNAME, 
    password=NEO4J_PASSWORD
)

# 3. Define the LLM used for extraction (GPT-4o is highly recommended for structured Extraction)
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# 4. Strict configuration defining your BRD Domain Schema
allowed_nodes = ["Actor", "SystemModule", "BusinessRule", "DataField", "Requirement"]
allowed_rels = ["TRIGGERS", "DEPENDS_ON", "VALIDATES", "ACCESSES", "FULFILLS"]

# Custom prompt overlay to guide the LLM to map business requirements accurately
brd_prompt = """
You are an expert Business Analyst and Knowledge Graph engineer. 
Your task is to extract clear business entities and relationships from the provided Business Requirement Document (BRD) text.
Map users/roles to 'Actor', software components to 'SystemModule', validations/constraints to 'BusinessRule', and variables to 'DataField'.
"""

# Initialize the automated Graph Transformer
transformer = LLMGraphTransformer(
    llm=llm,
    allowed_nodes=allowed_nodes,
    allowed_relationships=allowed_rels,
    node_properties=True # Captures descriptions or attributes if found
)

# 5. Sample BRD Text Input (Use clean Markdown formatting)
brd_text = """
The Customer Actor triggers the Payment Process in the Billing Module. 
The Billing Module accesses the User Profile DataField to verify the user account status.
The System must validate that the account balance is greater than zero before processing transactions, which fulfills Requirement BR-101.
The Invoice Generation SystemModule depends on the successful completion of the Billing Module transaction.
"""

# Wrap text into a LangChain Document format
documents = [Document(page_content=brd_text)]

print("Starting BRD extraction via LLM...")
# Convert unstructured text documents into Graph Documents (Nodes and Edges)
graph_documents = transformer.convert_to_graph_documents(documents)

print(f"Extracted {len(graph_documents[0].nodes)} nodes and {len(graph_documents[0].relationships)} relationships.")

# 6. Write the extracted elements directly into your Neo4j Database
graph.add_graph_documents(
    graph_documents, 
    baseEntityLabel=True, 
    include_source=True # Links the nodes back to the source text chunk
)

print("✅ Successfully built and loaded your BRD Knowledge Graph into Neo4j!")
