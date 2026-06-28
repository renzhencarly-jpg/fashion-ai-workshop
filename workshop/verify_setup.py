#!/usr/bin/env python3
"""
verify_setup.py — One-shot health check before running the app.

Checks, in order:
  1. .env is filled (MONGODB_URI, VOYAGE_API_KEY, Azure keys)
  2. MongoDB Atlas is reachable
  3. products / users / orders collections have data
  4. vector_index + default search indexes exist and are READY
  5. users.location_geo 2dsphere index exists
  6. Voyage API key works (tiny embed call)
  7. Azure OpenAI key works (tiny chat call)

Usage:
    python workshop/verify_setup.py
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_here, "..", "fasion_v2", ".env")

OK = "✅"
BAD = "❌"
WARN = "⚠️"

results = []


def check(label, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"error: {e}"
    icon = OK if ok else BAD
    print(f"{icon} {label}: {detail}")
    results.append(ok)
    return ok


def main():
    try:
        import certifi
        from pymongo import MongoClient
        from dotenv import load_dotenv
    except ImportError as e:
        sys.exit(f"{BAD} Missing dependency: {e}. Run: pip install -r fasion_v2/requirements.txt")

    load_dotenv(_env_path)
    uri = os.environ.get("MONGODB_URI", "")
    db_name = os.environ.get("DB_NAME", "fashion_db")
    voyage_key = os.environ.get("VOYAGE_API_KEY", "")
    azure_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
    azure_ep = os.environ.get("AZURE_OPENAI_ENDPOINT", "")

    print("=" * 56)
    print("Fashion AI Workshop — setup verification")
    print("=" * 56)

    # 1. env present
    def _env():
        missing = [k for k, v in {
            "MONGODB_URI": uri, "VOYAGE_API_KEY": voyage_key,
            "AZURE_OPENAI_API_KEY": azure_key, "AZURE_OPENAI_ENDPOINT": azure_ep,
        }.items() if not v]
        return (not missing), ("all set" if not missing else f"missing: {', '.join(missing)}")
    if not check("1. .env variables", _env):
        print("\nFix .env first (copy fasion_v2/.env.example), then re-run.")
        return _summary()

    # 2. Atlas reachable
    client = None
    def _connect():
        nonlocal client
        client = MongoClient(uri, tls=True, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
        return True, "connected"
    if not check("2. Atlas connection", _connect):
        return _summary()

    db = client[db_name]

    # 3. collections
    counts = {}
    def _collections():
        for c in ["products", "users", "orders"]:
            counts[c] = db[c].estimated_document_count()
        ok = counts["products"] > 0 and counts["users"] > 0
        return ok, f"products={counts['products']}, users={counts['users']}, orders={counts['orders']}"
    check("3. Collections have data", _collections)

    # 4. search indexes READY
    def _search_indexes():
        idx = {ix["name"]: ix.get("status", "?") for ix in db["products"].list_search_indexes()}
        need = ["vector_index", "default"]
        statuses = {n: idx.get(n, "MISSING") for n in need}
        ok = all(s == "READY" for s in statuses.values())
        return ok, " | ".join(f"{n}={s}" for n, s in statuses.items())
    check("4. products search indexes READY", _search_indexes)

    # 5. 2dsphere
    def _geo():
        info = db["users"].index_information()
        has = any("2dsphere" in str(v.get("key", "")) for v in info.values())
        return has, ("present" if has else "MISSING (regional trending disabled)")
    check("5. users 2dsphere index", _geo)

    # 6. Voyage
    def _voyage():
        import voyageai
        c = voyageai.Client(api_key=voyage_key)
        r = c.embed(["hello"], model=os.environ.get("VOYAGE_EMBED_MODEL", "voyage-3.5"), input_type="document")
        dim = len(r.embeddings[0])
        return dim == 1024, f"embedding works, dim={dim}"
    check("6. Voyage API key", _voyage)

    # 7. Azure
    def _azure():
        from langchain_openai import AzureChatOpenAI
        llm = AzureChatOpenAI(
            api_key=azure_key, azure_endpoint=azure_ep,
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2023-05-15"),
            azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
            temperature=0, max_tokens=5,
        )
        out = llm.invoke("say ok").content
        return bool(out), "chat works"
    check("7. Azure OpenAI key", _azure)

    _summary()


def _summary():
    print("=" * 56)
    if all(results):
        print(f"{OK} All checks passed — run:  cd fasion_v2 && python app.py")
    else:
        print(f"{BAD} Some checks failed. See WORKSHOP_SETUP.md → Troubleshooting.")
    print("=" * 56)


if __name__ == "__main__":
    main()
