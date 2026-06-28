# search.py
"""
Product retrieval: query understanding (LLM extractors), Voyage embeddings,
MongoDB hybrid search ($rankFusion of $vectorSearch + $search), Voyage rerank,
and regional trending ($geoNear + $lookup on orders).
"""
import json
from typing import List, Dict, Optional

from langchain_core.messages import HumanMessage

from clients import db, voyageai_client, llm
from config import VECTOR_INDEX, TEXT_INDEX, VOYAGE_EMBED_MODEL, VOYAGE_RERANK_MODEL


# ---------------------------------------------------------------------------
# LLM query understanding
# ---------------------------------------------------------------------------

def _strip_code_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    return raw


def extract_search_keywords(user_query: str) -> List[str]:
    """Extract product-catalog keywords from a natural-language query."""
    prompt = f"""Extract the most important search keywords from the user query below.
These keywords will be matched against product descriptions that contain fields like:
Product name, Category, Subcategory, Type, Color, Gender, Usage, Season, Price.

Rules:
- Return ONLY a JSON array of keyword strings, no explanation.
- Include specific attributes: color names, gender (Men/Women/Boys/Girls/Unisex),
  product types (Shoes, Shirts, Jeans, T-Shirts, Shorts, etc.),
  usage (Casual, Formal, Sports, Trekking, etc.),
  season (Summer, Winter, etc.),
  category (Footwear, Apparel, Accessories, etc.).
- Translate user intent into product catalog terms. Examples:
  - "climb mountain" -> "Trekking", "Sports", "Outdoor"
  - "hot weather" / "summer" -> "Summer", "Lightweight", "Shorts", "T-Shirts"
  - "office meeting" -> "Formal", "Blazer", "Trousers"
- Keep keywords short (1-2 words each).
- Do NOT include vague words like "good", "nice", "best", "recommend", "clothes", "outfits".

User query: "{user_query}"

JSON array:"""
    try:
        raw = _strip_code_fence(llm.invoke([HumanMessage(content=prompt)]).content)
        keywords = json.loads(raw)
        if isinstance(keywords, list):
            keywords = [k for k in keywords if isinstance(k, str) and k.strip()]
            print(f"🔑 Extracted keywords: {keywords}")
            return keywords
    except Exception as e:
        print(f"⚠️ Keyword extraction failed: {e}")
    return []


def extract_search_filters(user_query: str) -> Dict[str, List[str]]:
    """Extract structured pre-filters (season, exclude_articleType)."""
    prompt = f"""Analyze the user query below and extract structured filters for a fashion product search.

Available filter values:
- season: Fall, Spring, Summer, Winter
- articleType examples: Tshirts, Shirts, Casual Shoes, Sports Shoes, Shorts, Trousers,
  Jeans, Jackets, Sweaters, Sweatshirts, Caps, Backpacks, Sandals, Flip Flops,
  Track Pants, Dresses, Tops, Skirts, Kurtas, Heels, Flats, etc.

Rules:
- Return ONLY a JSON object, no explanation.
- Only include filters the query clearly implies.
- For "season": list seasons that ARE appropriate. "hot weather" -> ["Summer"]; "cold" -> ["Winter","Fall"].
- For "exclude_articleType": list article types clearly INAPPROPRIATE.
  "summer and hot" -> exclude ["Jackets","Sweaters","Sweatshirts"].
- If nothing applies, return {{}}.

User query: "{user_query}"

JSON object:"""
    try:
        raw = _strip_code_fence(llm.invoke([HumanMessage(content=prompt)]).content)
        filters = json.loads(raw)
        if isinstance(filters, dict):
            valid_seasons = {"Fall", "Spring", "Summer", "Winter"}
            if "season" in filters:
                filters["season"] = [s for s in filters["season"] if s in valid_seasons]
                if not filters["season"]:
                    del filters["season"]
            if "exclude_articleType" in filters:
                filters["exclude_articleType"] = [
                    t for t in filters["exclude_articleType"] if isinstance(t, str)
                ]
                if not filters["exclude_articleType"]:
                    del filters["exclude_articleType"]
            filters.pop("usage", None)
            return filters
    except Exception as e:
        print(f"⚠️ Filter extraction failed: {e}")
    return {}


def detect_trending_intent(user_query: str) -> bool:
    """Detect whether the user wants regional / nearby-user trend influence."""
    prompt = f"""Does the following user query ask for fashion recommendations based on what nearby users,
local community, regional trends, or popular items in the user's area are buying or wearing?

Rules:
- Return ONLY "yes" or "no".
- "yes" if the user mentions nearby users, local trends, popular around me, what others are buying, community picks, neighborhood style, regional recommendations.
- "no" for normal product searches even if they mention "trending" generically.
- When in doubt, return "no".

User query: "{user_query}"

Answer:"""
    try:
        answer = llm.invoke([HumanMessage(content=prompt)]).content.strip().lower().rstrip(".")
        return answer == "yes"
    except Exception as e:
        print(f"⚠️ Trending intent detection failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Embeddings + reranking (Voyage AI)
# ---------------------------------------------------------------------------

def get_embedding(text: str) -> List[float]:
    """Generate a text embedding with Voyage AI."""
    if not text.strip():
        return []
    result = voyageai_client.embed([text], model=VOYAGE_EMBED_MODEL, input_type="document")
    return result.embeddings[0]


def rerank_results(query: str, results: List[Dict], trending_context: str = "",
                   top_k: int = 100) -> List[Dict]:
    """Rerank search results with Voyage rerank-2 (trending-aware)."""
    if not results:
        return results
    rerank_query = query
    if trending_context:
        rerank_query += f"\n\nConsider that nearby shoppers also bought:\n{trending_context}"

    docs = []
    for r in results:
        doc = r.get("productDisplayName", "")
        if r.get("description"):
            doc += f" — {r['description'][:150]}"
        if r.get("articleType"):
            doc += f" [{r['articleType']}]"
        if r.get("price"):
            doc += f" ${r['price']:.2f}"
        docs.append(doc)

    try:
        rr = voyageai_client.rerank(
            rerank_query, docs, model=VOYAGE_RERANK_MODEL, top_k=min(top_k, len(docs))
        )
        reranked = []
        for item in rr.results:
            product = results[item.index].copy()
            product["rerank_score"] = item.relevance_score
            reranked.append(product)
        print("🔄 Reranked results with Voyage rerank-2")
        return reranked
    except Exception as e:
        print(f"⚠️ Reranking failed, using original order: {e}")
        return results


# ---------------------------------------------------------------------------
# MongoDB hybrid search
# ---------------------------------------------------------------------------

def _build_vector_filter(filters: Optional[Dict[str, List[str]]]):
    parts = []
    if filters:
        if "season" in filters:
            parts.append({"season": {"$in": filters["season"]}})
        if "exclude_articleType" in filters:
            parts.append({"articleType": {"$nin": filters["exclude_articleType"]}})
        if "gender" in filters:
            parts.append({"gender": {"$in": filters["gender"]}})
    if len(parts) == 1:
        return parts[0]
    if len(parts) > 1:
        return {"$and": parts}
    return None


def hybrid_search_products(query_embedding: List[float], keywords: List[str],
                           limit: int = 100,
                           filters: Optional[Dict[str, List[str]]] = None) -> List[Dict]:
    """Hybrid search: $rankFusion of $vectorSearch (0.7) and $search (0.3)."""
    collection = db["products"]
    vector_filter = _build_vector_filter(filters)

    vector_search_stage = {
        "index": VECTOR_INDEX,
        "path": "embedding",
        "queryVector": query_embedding,
        "numCandidates": 150,
        "limit": limit,
    }
    if vector_filter:
        vector_search_stage["filter"] = vector_filter

    project_fields = {
        "_id": 0, "id": 1, "productDisplayName": 1, "az_img_url": 1,
        "price": 1, "description": 1, "season": 1, "usage": 1, "articleType": 1,
    }

    search_query = " ".join(keywords) if keywords else ""
    if search_query:
        pipeline = [
            {"$rankFusion": {
                "input": {"pipelines": {
                    "vectorPipeline": [{"$vectorSearch": vector_search_stage}],
                    "textPipeline": [
                        {"$search": {
                            "index": TEXT_INDEX,
                            "text": {
                                "query": search_query,
                                "path": "description",
                                "fuzzy": {"maxEdits": 1},
                            },
                        }},
                        {"$limit": limit},
                    ],
                }},
                "combination": {"weights": {"vectorPipeline": 0.7, "textPipeline": 0.3}},
            }},
            {"$limit": limit},
            {"$project": project_fields},
        ]
        mode = "hybrid (vector 0.7 + text 0.3)"
    else:
        pipeline = [
            {"$vectorSearch": vector_search_stage},
            {"$project": {**project_fields, "score": {"$meta": "vectorSearchScore"}}},
        ]
        mode = "vector-only"

    results = list(collection.aggregate(pipeline))
    print(f"🔬 {mode}: {len(results)} results | keywords={keywords} | filter={vector_filter}")
    return results


# ---------------------------------------------------------------------------
# Regional trending ($geoNear + $lookup orders)
# ---------------------------------------------------------------------------

def get_regional_trends(user_id: str, coordinates: List[float],
                        radius_km: float = 50, limit: int = 10) -> List[Dict]:
    """Find products purchased by nearby users via $geoNear on the users collection."""
    radius_meters = radius_km * 1000
    pipeline = [
        {"$geoNear": {
            "near": {"type": "Point", "coordinates": coordinates},
            "distanceField": "distance",
            "maxDistance": radius_meters,
            "spherical": True,
            "query": {"user_id": {"$ne": user_id}},
        }},
        {"$project": {"user_id": 1, "distance": 1}},
        {"$lookup": {
            "from": "orders", "localField": "user_id",
            "foreignField": "user_id", "as": "orders",
        }},
        {"$unwind": "$orders"},
        {"$unwind": "$orders.items"},
        {"$group": {
            "_id": "$orders.items.product_name",
            "count": {"$sum": 1},
            "avg_price": {"$avg": "$orders.items.price"},
            "buyers": {"$addToSet": "$user_id"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": limit},
        {"$project": {
            "_id": 0,
            "product_name": "$_id",
            "purchase_count": "$count",
            "avg_price": {"$round": ["$avg_price", 2]},
            "unique_buyers": {"$size": "$buyers"},
        }},
    ]
    try:
        results = list(db["users"].aggregate(pipeline))
        if results:
            print(f"📍 Regional trends ({radius_km}km): {len(results)} popular items nearby")
        return results
    except Exception as e:
        print(f"⚠️ Regional trending failed: {e}")
        return []


def format_trending_context(trends: List[Dict]) -> str:
    if not trends:
        return ""
    lines = ["Popular items purchased by nearby shoppers:"]
    for t in trends:
        lines.append(
            f"  • {t['product_name']} (bought {t['purchase_count']}x, "
            f"~${t['avg_price']:.0f}, {t['unique_buyers']} buyers)"
        )
    return "\n".join(lines)
