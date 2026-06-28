# Creating the Atlas indexes in the UI (step by step)

`mongorestore` copies **data only** — it does **NOT** recreate Atlas Search /
Vector Search indexes. After restoring the data you must create the indexes
yourself.

The app needs:

| # | Index | Collection | Type | Required? |
|---|-------|-----------|------|-----------|
| 1 | `vector_index` | `products` | Vector Search | ✅ Yes (semantic search) |
| 2 | `default` | `products` | Search (full-text) | ✅ Yes (hybrid search) |
| 3 | `2dsphere` on `location_geo` | `users` | Regular index | Optional (regional trending) |

> 💡 Easiest: run `python workshop/create_indexes.py` (does all 3 for you).
> The steps below are the **manual UI fallback**.

> ⏱️ The two Search indexes take **1–3 minutes** to build
> (status: `PENDING` → `BUILDING` → `READY`). The app only works once
> `vector_index` is **READY**.

---

## ⚠️ M0 free tier: max 3 search indexes — delete leftovers first

On the **M0 free cluster you can have at most 3 Atlas Search / Vector indexes.**
If you previously ran a version with Mem0, you may have leftover indexes
(`fashion_memories_*`, `mem0migrations_*`) eating those slots, which **blocks**
creating the `products` indexes.

**Before creating the new ones, delete any non-`products` search indexes:**

1. Atlas → your cluster → **Atlas Search** (left sidebar, under "Services", may
   also appear as the **Search** tab on the cluster page).
2. You'll see a list of search indexes. For anything **not** on the `products`
   collection (e.g. `fashion_memories_vector_index`,
   `fashion_memories_text_search_index`, `mem0migrations_vector_index`):
   click the **⋯ / trash icon** → **Delete** → confirm.
3. After deleting them you should have **0–1** search indexes left, leaving room
   for the 2 `products` indexes below.

---

## 1. Create `vector_index` (Vector Search on `products.embedding`)

This powers semantic search (`$vectorSearch`). **Required.**

1. Atlas → your cluster → open the **Atlas Search** tab.
2. Click **Create Search Index** (green button, top right).
3. Choose **Atlas Vector Search → JSON Editor**, then **Next**.
   *(Not "Atlas Search" — pick the **Vector Search** option.)*
4. **Database and Collection:** expand `fashion_db` and tick **`products`**.
5. **Index Name:** type exactly `vector_index`
6. In the JSON box, replace everything with:

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

7. Click **Next** → **Create Search Index**.
8. Wait until **Status = Active / READY**.

> ⚠️ Two things that cause "0 results":
> - `numDimensions` **must be `1024`** (Voyage `voyage-3.5`).
> - The 3 `filter` fields (`season`, `articleType`, `gender`) **must be present** —
>   the app filters on them, and a vector index without them returns nothing
>   when a filter is applied.

---

## 2. Create `default` (full-text Search on `products`)

This powers the keyword half of hybrid search (`$search`). **Required.**

1. **Atlas Search** tab → **Create Search Index** again.
2. Choose **Atlas Search → JSON Editor**, then **Next**.
   *(This time pick **Atlas Search**, not Vector Search.)*
3. **Database and Collection:** `fashion_db` → **`products`**.
4. **Index Name:** type exactly `default`
5. JSON definition:

   ```json
   { "mappings": { "dynamic": true } }
   ```

6. **Next** → **Create Search Index**.
7. Wait until **Status = Active / READY**.

---

## 3. (Optional) `2dsphere` on `users.location_geo`

Powers regional trending (`$geoNear`). Without it, normal search still works;
only the "nearby shoppers" feature is disabled. This is a **regular index**, not
an Atlas Search index, so it's not created from the Atlas Search tab.

Easiest with `mongosh`:

```bash
mongosh "<your Atlas connection string>"
use fashion_db
db.users.createIndex({ location_geo: "2dsphere" })
```

(Or just let `python workshop/create_indexes.py` create it automatically.)

---

## Verify everything is ready

```bash
python workshop/verify_setup.py
```

Look for:

```
✅ 4. products search indexes READY: vector_index=READY | default=READY
```

Once `vector_index` is READY, run the app:

```bash
cd fasion_v2 && python app.py
```

---

## Quick troubleshooting

| Symptom | Cause / Fix |
|--------|-------------|
| Can't create index — "max 3 search indexes" | M0 limit. Delete leftover `fashion_memories_*` / `mem0migrations_*` indexes (top of this page). |
| Search returns 0 results, index is READY | Vector index missing the 3 `filter` fields, or wrong `numDimensions`. Recreate `vector_index` exactly as above. |
| `$vectorSearch` error on run | `vector_index` not READY yet, or wrong name. Wait, or check the name is exactly `vector_index`. |
| Created on the wrong collection | Indexes must be on `fashion_db.products`. Delete and recreate on the right collection. |
