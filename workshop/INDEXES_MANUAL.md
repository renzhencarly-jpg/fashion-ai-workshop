# Creating the Atlas indexes manually (fallback)

`mongorestore` copies **data only** — it does **not** recreate Atlas Search /
Vector Search indexes. The app needs **3 indexes**. The easiest way is to run
`python workshop/create_indexes.py`. If that fails (older driver, permissions,
etc.), create them by hand in the Atlas UI using the steps below.

> All three must exist before the app will work. The two Search indexes take
> 1–3 minutes to build (status goes `PENDING` → `BUILDING` → `READY`).

---

## 1. `vector_index` — Vector Search on `products.embedding`

This powers semantic search (`$vectorSearch`). **Required.**

1. In Atlas, open your cluster → **Atlas Search** tab → **Create Search Index**.
2. Choose **JSON Editor** → **Next**.
3. **Index Name:** `vector_index`
4. **Database / Collection:** `fashion_db` / `products`
5. Index type: **Vector Search**
6. Paste this JSON definition:

```json
{
  "fields": [
    { "type": "vector", "path": "embedding", "numDimensions": 1024, "similarity": "dotProduct" },
    { "type": "filter", "path": "season" },
    { "type": "filter", "path": "articleType" },
    { "type": "filter", "path": "gender" }
  ]
}
```

7. **Create** and wait until status is **READY**.

> ⚠️ `numDimensions` **must be 1024** (Voyage `voyage-3.5`). A wrong value
> returns zero results.

---

## 2. `default` — Atlas Search (full-text) on `products`

This powers the keyword half of hybrid search (`$search`). **Required.**

1. **Atlas Search** → **Create Search Index** → **JSON Editor**.
2. **Index Name:** `default`
3. **Database / Collection:** `fashion_db` / `products`
4. Index type: **Search** (not Vector Search)
5. Paste:

```json
{ "mappings": { "dynamic": true } }
```

6. **Create** and wait until **READY**.

---

## 3. `2dsphere` — geo index on `users.location_geo`

This powers regional trending (`$geoNear`). Without it, normal search still
works but the "nearby shoppers" feature is disabled.

This is a **regular index**, not an Atlas Search index. Easiest via `mongosh`:

```bash
mongosh "<your Atlas connection string>"
use fashion_db
db.users.createIndex({ location_geo: "2dsphere" })
```

(Or let `workshop/create_indexes.py` create it — it does this automatically.)

---

## Verify

After all three are READY, run:

```bash
python workshop/verify_setup.py
```

It checks the collections and that every index exists and is READY.
