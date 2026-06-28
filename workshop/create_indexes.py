#!/usr/bin/env python3
"""
create_indexes.py — Create the Atlas Search / Vector indexes the app needs.

mongorestore copies DATA only; Atlas Search & Vector Search indexes are NOT part
of a dump and must be created separately. This script creates all three:

  1. products.vector_index  (vectorSearch, 1024-dim dotProduct, + filters)
  2. products.default       (Atlas Search, dynamic mapping — full-text)
  3. users.location_geo     (2dsphere — regional trending $geoNear)

Usage:
    # from the repo root, after filling fasion_v2/.env with your MONGODB_URI:
    python workshop/create_indexes.py

Requires: pymongo>=4.7 (ships with the app's requirements.txt).
The script is idempotent — existing indexes are left alone.
"""
import os
import sys
import time

try:
    import certifi
    from pymongo import MongoClient
    from pymongo.operations import SearchIndexModel
    from dotenv import load_dotenv
except ImportError as e:
    sys.exit(f"❌ Missing dependency: {e}. Run: pip install -r fasion_v2/requirements.txt")

# Load .env from fasion_v2 (same file the app uses)
_here = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_here, "..", "fasion_v2", ".env")
load_dotenv(_env_path)

MONGODB_URI = os.environ.get("MONGODB_URI", "")
DB_NAME = os.environ.get("DB_NAME", "fashion_db")

if not MONGODB_URI:
    sys.exit("❌ MONGODB_URI not set. Fill it in fasion_v2/.env first.")

# --- Index definitions ---
VECTOR_INDEX_NAME = "vector_index"
VECTOR_INDEX_DEF = {
    "fields": [
        {"type": "vector", "path": "embedding", "numDimensions": 1024, "similarity": "dotProduct"},
        {"type": "filter", "path": "season"},
        {"type": "filter", "path": "articleType"},
        {"type": "filter", "path": "gender"},
    ]
}

TEXT_INDEX_NAME = "default"
TEXT_INDEX_DEF = {"mappings": {"dynamic": True}}


def existing_search_indexes(coll):
    try:
        return {ix["name"]: ix for ix in coll.list_search_indexes()}
    except Exception:
        return {}


def ensure_search_index(coll, name, definition, index_type):
    existing = existing_search_indexes(coll)
    if name in existing:
        print(f"  ✓ '{name}' already exists on {coll.name} (status: {existing[name].get('status', '?')})")
        return
    print(f"  → Creating '{name}' ({index_type}) on {coll.name} ...")
    model = SearchIndexModel(definition=definition, name=name, type=index_type)
    coll.create_search_index(model=model)
    print(f"  ✓ Submitted '{name}'. Atlas will build it in the background.")


def wait_until_ready(coll, names, timeout_sec=300):
    print("\n⏳ Waiting for search indexes to become READY (this can take 1-3 min)...")
    start = time.time()
    while time.time() - start < timeout_sec:
        idx = existing_search_indexes(coll)
        statuses = {n: idx.get(n, {}).get("status", "MISSING") for n in names}
        ready = all(s == "READY" for s in statuses.values())
        line = " | ".join(f"{n}={s}" for n, s in statuses.items())
        print(f"   {line}")
        if ready:
            print("✅ All search indexes are READY.")
            return True
        time.sleep(8)
    print("⚠️ Timed out waiting. Check the Atlas UI → Atlas Search for status.")
    return False


def main():
    print("Connecting to Atlas...")
    client = MongoClient(MONGODB_URI, tls=True, tlsCAFile=certifi.where())
    db = client[DB_NAME]

    # Sanity: collections present?
    counts = {c: db[c].estimated_document_count() for c in ["products", "users", "orders"]}
    print(f"Collections: products={counts['products']}, users={counts['users']}, orders={counts['orders']}")
    if counts["products"] == 0:
        sys.exit("❌ 'products' is empty. Run mongorestore first (see WORKSHOP_SETUP.md).")

    print("\n=== 1/3 & 2/3: Atlas Search / Vector indexes on 'products' ===")
    ensure_search_index(db["products"], VECTOR_INDEX_NAME, VECTOR_INDEX_DEF, "vectorSearch")
    ensure_search_index(db["products"], TEXT_INDEX_NAME, TEXT_INDEX_DEF, "search")

    print("\n=== 3/3: 2dsphere index on 'users.location_geo' ===")
    try:
        db["users"].create_index([("location_geo", "2dsphere")], name="location_geo_2dsphere")
        print("  ✓ 2dsphere index ready on users.location_geo")
    except Exception as e:
        print(f"  ⚠️ Could not create 2dsphere index: {e}")

    wait_until_ready(db["products"], [VECTOR_INDEX_NAME, TEXT_INDEX_NAME])

    print("\n🎉 Done. You can now run:  cd fasion_v2 && python app.py")


if __name__ == "__main__":
    main()
