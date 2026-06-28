# clients.py
"""
Singleton clients for the Shopping Guide AI (Fashion v2).

Initializes (once at import time):
  - MongoDB Atlas client + database handle
  - Voyage AI client (embeddings + reranker)
  - Azure OpenAI chat model (LangChain wrapper)

No Mem0: long-term preferences are extracted by the LLM and stored directly in
the `users.preferences` array (pure MongoDB). This keeps the Atlas Search/Vector
index count low enough for the M0 free tier (max 3 search indexes).
"""
import certifi
from pymongo import MongoClient

import voyageai
from langchain_openai import AzureChatOpenAI

from config import (
    MONGODB_URI, DB_NAME, VOYAGE_API_KEY,
    AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
)

print("Initializing clients (v2)...")

# --- MongoDB ---
mongodb_client = MongoClient(MONGODB_URI, tls=True, tlsCAFile=certifi.where())
db = mongodb_client[DB_NAME]

# --- Voyage AI ---
voyageai_client = voyageai.Client(api_key=VOYAGE_API_KEY)

# --- Azure OpenAI chat model (query understanding + preference extraction) ---
llm = AzureChatOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_deployment=AZURE_OPENAI_DEPLOYMENT,
    temperature=0.7,
    max_tokens=2000,
)

print("✅ All clients initialized (v2)")
