# Shopping Guide AI — v2

A fashion **shopping-guide AI** built on **LangGraph + MongoDB Atlas + Mem0**.
You describe what you want, it searches the product catalog, you tick the products
you like, and you place an order.

## What it does

- ✅ Natural-language product search (hybrid `$rankFusion`: vector 0.7 + text 0.3)
- ✅ Voyage AI embeddings (`voyage-3.5`) + reranking (`rerank-2`)
- ✅ Long-term memory (Mem0) + learned preferences
- ✅ Regional trending (`$geoNear` + `$lookup` on orders)
- ✅ Select products from the results and check out (orders saved to MongoDB)

## What it does NOT do (removed)

- ❌ Outfit generation + AI outfit images (no Gemini, no OpenAI image/vision calls)
- ❌ Virtual try-on
- ❌ Video upload & video search

> Because outfit/image generation is gone, this app no longer calls Gemini or
> Azure Blob Storage. Azure OpenAI (GPT-4o) is still used, but only for light
> search query understanding (keywords / filters / trending intent) and by Mem0.

## Architecture (modular)

| File            | Responsibility |
|-----------------|----------------|
| `config.py`     | Env-var configuration |
| `clients.py`    | Singleton clients: Mongo, Voyage, Azure LLM, Mem0 |
| `db.py`         | Profiles, geocoding, orders, sessions |
| `memory.py`     | Mem0 helpers + preference extraction |
| `search.py`     | LLM extractors, embeddings, hybrid search, rerank, geo trending |
| `agents.py`     | LangGraph `discover` node + `checkout_agent` + workflow |
| `formatters.py` | HTML formatters for the Gradio UI |
| `ui.py`         | Gradio Blocks UI + streaming handlers |
| `app.py`        | Entry point (FastAPI + uvicorn) |

## LangGraph workflow

```
[ENTRY] → discover → END
checkout_agent is invoked directly by the "Place Order" button.
```

## Data / MongoDB

v2 **reuses the existing `cluster1` / `fashion_db`**:
- 44k products (with `embedding` + Atlas `vector_index` / `default` text index)
- `users`, `orders`, `fashion_memories`
- LangGraph state uses a separate `checkpoints_v2` collection.

## Run

```bash
# from the fasion_v2 directory, using the parent project's venv
../venv/bin/python app.py
# open http://localhost:7861/
```

Or with Docker:

```bash
docker build -t shopping-guide-v2 .
docker run -p 8080:8080 --env-file .env shopping-guide-v2
```

## Usage

1. Enter a **User ID** (e.g. `user_101`).
2. Type a request (e.g. *"I need formal business attire for office meetings"*).
3. Click **① Search Products**.
4. In **🛒 Select products to buy**, tick the items you want.
5. Click **② Place Order**.

Try regional trends: *"What are people near me buying?"* (requires the user to have
`location_geo`, which is auto-geocoded on first load).
