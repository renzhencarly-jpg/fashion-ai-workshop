# Fashion AI — Workshop Setup Guide

Run the **Fashion AI shopping-guide agent** on your own machine, backed by your
own free MongoDB Atlas cluster.

**Stack:** LangGraph · MongoDB Atlas (Vector + full-text search) · Voyage AI
(embeddings + rerank) · Azure OpenAI (GPT-4o). The app lives in `fasion_v2/`.
Preferences are learned by the LLM and stored in `users.preferences` (no Mem0),
so the app only needs **2 Atlas Search indexes** — fits the M0 free tier.

You will:
1. Create a free MongoDB Atlas cluster
2. Get a Voyage AI key (Azure keys are provided by the instructor)
3. Clone this repo & install dependencies
4. Download the demo data & restore it into your cluster
5. Create the search indexes
6. Configure `.env` and run the app

> ⏱️ Budget ~20–30 minutes. The data download (~400 MB) and the index build
> (1–3 min) are the slowest parts.

---

## Step 0 — Prerequisites

Install these first:

- **Python 3.11**  → https://www.python.org/downloads/
- **git**
- **MongoDB Database Tools** (`mongorestore`):

  | OS | Command |
  |----|---------|
  | macOS | `brew install mongodb-database-tools` |
  | Windows | `winget install MongoDB.DatabaseTools` |
  | Linux | Download `.deb`/`.tgz` from https://www.mongodb.com/try/download/database-tools |

  Verify: `mongorestore --version`

---

## Step 1 — Create a free Atlas cluster

1. Register: https://www.mongodb.com/cloud/atlas/register
2. Create a **M0 (Free)** cluster — pick a region near you.
3. **Database Access** → *Add New Database User* → set a username + password (remember them).
4. **Network Access** → *Add IP Address* → **Allow Access from Anywhere** (`0.0.0.0/0`).
   *(Convenient for the workshop; restrict it in production.)*
5. **Connect** → **Drivers** → copy the connection string. It looks like:
   ```
   mongodb+srv://<user>:<password>@<cluster>.xxxxx.mongodb.net/
   ```
   Replace `<user>`/`<password>` with the ones from step 3.

---

## Step 2 — Get a Voyage AI key

1. Register: https://www.voyageai.com
2. Create an API key (free tier is plenty for the workshop).
3. **Azure OpenAI keys** are handed out by the instructor — you'll paste those in Step 6.

---

## Step 3 — Clone the repo & install dependencies

```bash
git clone https://github.com/renzhencarly-jpg/fashion-ai-workshop.git
cd fashion-ai-workshop/fasion_v2

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

---

## Step 4 — Download the demo data & restore it

1. **Download** the data bundle from Google Drive:

   **Data download:** <link>

   You'll get `fashion_demo_data.tar.gz` (~400 MB).

2. **Unpack** it (from the repo root):

   ```bash
   cd ..                          # back to repo root
   tar -xzf fashion_demo_data.tar.gz   # creates ./demo_dump/
   ```

3. **Restore** into YOUR Atlas cluster (use your own connection string):

   ```bash
   mongorestore \
     --uri="mongodb+srv://<user>:<password>@<cluster>.xxxxx.mongodb.net/" \
     --gzip \
     --nsInclude="fashion_db.*" \
     ./demo_dump
   ```

   This loads 3 collections: `products` (~30k items), `users`, `orders`.

> ℹ️ `checkpoints_v2` is **not** in the bundle — the app (LangGraph) creates it
> automatically on first use. There is no `fashion_memories` collection (no Mem0).

---

## Step 5 — Create the search indexes

`mongorestore` restores **data only** — Atlas Search / Vector indexes must be
created separately. From the repo root:

```bash
# fill MONGODB_URI in fasion_v2/.env first (Step 6 shows how), OR set it inline:
python workshop/create_indexes.py
```

This creates and waits for:
- `vector_index` (Vector Search, 1024-dim) on `products.embedding`
- `default` (full-text) on `products`
- `2dsphere` on `users.location_geo`

> If the script fails, create them by hand: see
> [`workshop/INDEXES_MANUAL.md`](workshop/INDEXES_MANUAL.md).

Indexes take **1–3 minutes** to reach `READY`.

---

## Step 6 — Configure `.env`

```bash
cd fasion_v2
cp .env.example .env
```

Open `.env` and fill in:
- `MONGODB_URI` — your Atlas string (Step 1)
- `VOYAGE_API_KEY` — your Voyage key (Step 2)
- `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` — provided by the instructor

---

## Step 7 — Verify & run

```bash
# from the repo root
python workshop/verify_setup.py
```

It checks connectivity, collections, indexes, and your API keys. When everything
is ✅:

```bash
cd fasion_v2
python app.py
```

Open **http://localhost:7861/** and try a search like
*"I need summer outfits for a beach vacation"* (User ID: `user_101`).

---

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| `MONGODB_URI not set` | Fill `fasion_v2/.env` (Step 6). |
| Search returns nothing / `$vectorSearch` error | Indexes not READY. Re-run `create_indexes.py`, wait for READY, or build manually. |
| `numDimensions` / dimension mismatch | `vector_index` must be **1024** dims. Recreate it. |
| Auth / connection timeout | Check Atlas **Network Access** allows your IP (`0.0.0.0/0`) and the user/password in the URI. |
| Azure check fails | Re-paste the instructor's keys; confirm endpoint URL has trailing `/`. |
| Voyage check fails | Re-check your Voyage key / free-tier quota. |
| `mongorestore: command not found` | Install MongoDB Database Tools (Step 0). |
| Over 512 MB on M0 | You imported too much. Use the provided bundle only (don't import the full catalog). |

---

## For the instructor (one-time data prep)

> Participants don't need this — it documents how the data bundle was produced.

1. Dump a slim `products` (~400 MB) plus full `users`/`orders` from the source DB
   (does **not** modify the source):

   ```bash
   # products: id <= 39783 (30k) + the 28 order-referenced items above that id
   mongodump --uri="<source-uri>" --db=fashion_db --collection=products \
     --query='{"$or":[{"id":{"$lte":39783}},{"id":{"$in":[39988,42256,42258,42265,42270,44584,44725,44921,46623,47392,49070,49486,49716,51379,51380,51499,51658,54543,54588,54924,56844,56850,56855,57138,58148,58183,58513,59263]}}]}' \
     --out=./demo_dump --gzip
   mongodump --uri="<source-uri>" --db=fashion_db --collection=users  --out=./demo_dump --gzip
   mongodump --uri="<source-uri>" --db=fashion_db --collection=orders --out=./demo_dump --gzip
   ```

2. Package & upload:

   ```bash
   tar -czf fashion_demo_data.tar.gz demo_dump/
   ```
   Upload to Google Drive, set link sharing to **Anyone with the link → Viewer**,
   and paste the link into the `<link>` placeholder in Step 4.

3. Push code + workshop materials to `renzhencarly-jpg/fashion-ai-workshop`
   (the real `.env` and `demo_dump/` are gitignored — never commit them).

4. Share the 2 Azure OpenAI values (key + endpoint) with participants privately
   at the workshop.
