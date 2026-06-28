# config.py
"""
Configuration for Shopping Guide AI (Fashion v2).

Reads from environment variables (.env file or the host environment).
Reuses credentials from the original Fashion AI project:
  - Azure OpenAI (chat + embeddings, used for search query understanding + Mem0)
  - MongoDB Atlas (cluster1 / fashion_db)
  - Voyage AI (text embeddings + reranker)

This is a search-and-checkout shopping guide. It does NOT generate outfits,
images or try-ons, so Gemini / Azure Blob are not configured.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Azure OpenAI (GPT-4o, chat / routing / styling / vision) ---
AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2023-05-15")

# --- Azure OpenAI Embeddings (used by Mem0) ---
AZURE_EM_ENDPOINT = os.environ.get("AZURE_EM_ENDPOINT", "")
AZURE_EM_MODEL = os.environ.get("AZURE_EM_MODEL", "text-embedding-3-small")
AZURE_EM_DEPLOYMENT = os.environ.get("AZURE_EM_DEPLOYMENT", "text-embedding-3-small")
AZURE_EM_KEY = os.environ.get("AZURE_EM_KEY", "")
AZURE_EM_VERSION = os.environ.get("AZURE_EM_VERSION", "2024-12-01-preview")

# --- MongoDB Atlas ---
# Reuses the existing cluster1 / fashion_db (44k products + Atlas indexes already built).
MONGODB_URI = os.environ.get("MONGODB_URI", "")
DB_NAME = os.environ.get("DB_NAME", "fashion_db")

# --- Voyage AI (text embeddings + reranker) ---
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
VOYAGE_EMBED_MODEL = os.environ.get("VOYAGE_EMBED_MODEL", "voyage-3.5")
VOYAGE_RERANK_MODEL = os.environ.get("VOYAGE_RERANK_MODEL", "rerank-2")

# --- Mem0 (long-term memory) ---
MEM0_COLLECTION_NAME = os.environ.get("MEM0_COLLECTION_NAME", "fashion_memories")
MEM0_EMBEDDING_DIMS = 1536  # text-embedding-3-small dimensions

# --- Atlas search index names (must exist on the products collection) ---
VECTOR_INDEX = os.environ.get("VECTOR_INDEX", "vector_index")
TEXT_INDEX = os.environ.get("TEXT_INDEX", "default")

# --- Server ---
PORT = int(os.environ.get("PORT", 7861))  # 7861 so it can run alongside v1 (7860)
