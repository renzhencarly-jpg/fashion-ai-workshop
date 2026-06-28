# config.py
"""
Configuration for Shopping Guide AI (Fashion v2).

Reads from environment variables (.env file or the host environment):
  - Azure OpenAI (GPT-4o chat — search query understanding + preference extraction)
  - MongoDB Atlas (fashion_db)
  - Voyage AI (text embeddings + reranker)

No Mem0 / Azure embeddings: long-term preferences are extracted by the chat LLM
and stored in users.preferences (pure MongoDB). This keeps the Atlas
Search/Vector index count within the M0 free-tier limit (3 search indexes).
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Azure OpenAI (GPT-4o) — query understanding + preference extraction ---
AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2023-05-15")

# --- MongoDB Atlas ---
MONGODB_URI = os.environ.get("MONGODB_URI", "")
DB_NAME = os.environ.get("DB_NAME", "fashion_db")

# --- Voyage AI (text embeddings + reranker) ---
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
VOYAGE_EMBED_MODEL = os.environ.get("VOYAGE_EMBED_MODEL", "voyage-3.5")
VOYAGE_RERANK_MODEL = os.environ.get("VOYAGE_RERANK_MODEL", "rerank-2")

# --- Atlas search index names (must exist on the products collection) ---
VECTOR_INDEX = os.environ.get("VECTOR_INDEX", "vector_index")
TEXT_INDEX = os.environ.get("TEXT_INDEX", "default")

# --- Server ---
PORT = int(os.environ.get("PORT", 7861))
