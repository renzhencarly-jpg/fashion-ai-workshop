# clients.py
"""
Singleton clients for the Shopping Guide AI (Fashion v2).

Initializes (once at import time):
  - MongoDB Atlas client + database handle
  - Voyage AI client (embeddings + reranker)
  - Azure OpenAI chat model (LangChain wrapper)
  - Mem0 long-term memory store (backed by MongoDB + Azure embedder/LLM)
"""
import certifi
from pymongo import MongoClient

import voyageai
from langchain_openai import AzureChatOpenAI
from mem0 import Memory

from config import (
    MONGODB_URI, DB_NAME, VOYAGE_API_KEY,
    AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT, AZURE_EM_MODEL, AZURE_EM_KEY, AZURE_EM_ENDPOINT,
    AZURE_EM_DEPLOYMENT, AZURE_EM_VERSION, MEM0_COLLECTION_NAME, MEM0_EMBEDDING_DIMS,
)

print("Initializing clients (v2)...")

# --- MongoDB ---
mongodb_client = MongoClient(MONGODB_URI, tls=True, tlsCAFile=certifi.where())
db = mongodb_client[DB_NAME]

# --- Voyage AI ---
voyageai_client = voyageai.Client(api_key=VOYAGE_API_KEY)

# --- Azure OpenAI chat model ---
llm = AzureChatOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_deployment=AZURE_OPENAI_DEPLOYMENT,
    temperature=0.7,
    max_tokens=2000,
)

# --- Mem0 long-term memory ---
# Build a Mem0-compatible MongoDB URI with TLS CA cert for Atlas.
_mem0_mongo_uri = MONGODB_URI
if "mongodb+srv" in MONGODB_URI or "mongodb.net" in MONGODB_URI:
    _sep = "&" if "?" in MONGODB_URI else "?"
    _mem0_mongo_uri = f"{MONGODB_URI}{_sep}tls=true&tlsCAFile={certifi.where()}"

mem0_config = {
    "vector_store": {
        "provider": "mongodb",
        "config": {
            "collection_name": MEM0_COLLECTION_NAME,
            "db_name": DB_NAME,
            "mongo_uri": _mem0_mongo_uri,
            "embedding_model_dims": MEM0_EMBEDDING_DIMS,
        },
    },
    "embedder": {
        "provider": "azure_openai",
        "config": {
            "model": AZURE_EM_MODEL,
            "embedding_dims": MEM0_EMBEDDING_DIMS,
            "azure_kwargs": {
                "api_key": AZURE_EM_KEY,
                "azure_endpoint": AZURE_EM_ENDPOINT,
                "azure_deployment": AZURE_EM_DEPLOYMENT,
                "api_version": AZURE_EM_VERSION,
            },
        },
    },
    "llm": {
        "provider": "azure_openai",
        "config": {
            "model": AZURE_OPENAI_DEPLOYMENT,
            "temperature": 0.2,
            "max_tokens": 1500,
            "azure_kwargs": {
                "api_key": AZURE_OPENAI_API_KEY,
                "azure_endpoint": AZURE_OPENAI_ENDPOINT,
                "azure_deployment": AZURE_OPENAI_DEPLOYMENT,
                "api_version": AZURE_OPENAI_API_VERSION,
            },
        },
    },
    "version": "v1.1",
}

memory = Memory.from_config(mem0_config)
print("✅ Mem0 memory initialized")
print("✅ All clients initialized (v2)")
