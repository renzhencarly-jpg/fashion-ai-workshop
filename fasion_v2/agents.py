# agents.py
"""
LangGraph workflow for the Shopping Guide AI (v2).

Single node:
  discover -> product retrieval (memory + regional trending + hybrid search + rerank)

checkout_agent is invoked directly by a UI button (not a graph node). It places an
order for the products the user selected from the search results.

Removed vs earlier versions: intent routing, outfit generation, outfit images,
try-on.
"""
import uuid
import operator
from typing import TypedDict, Annotated, List, Dict, Optional

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.mongodb import MongoDBSaver

from clients import db, mongodb_client
from config import DB_NAME
from db import save_order_to_db
from memory import (
    get_all_memories, filter_memories_by_type, format_memories_as_context,
    save_order_memory,
)
from search import (
    extract_search_keywords, extract_search_filters, detect_trending_intent,
    get_embedding, rerank_results, hybrid_search_products,
    get_regional_trends, format_trending_context,
)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class ShopAgentState(TypedDict):
    interaction_id: Optional[str]
    user_id: str
    user_profile: Dict
    user_query: str
    search_results: List[Dict]
    checkout_items: List[Dict]
    checkout_total: float
    order_id: Optional[str]
    messages: Annotated[List, operator.add]
    current_step: str
    memory_context: Optional[str]
    trending_context: Optional[str]


# ---------------------------------------------------------------------------
# Discover agent
# ---------------------------------------------------------------------------

def discover_agent(state: ShopAgentState) -> ShopAgentState:
    print("\n--- 🔍 DISCOVER AGENT ---")
    user_query = state["user_query"]
    user_id = state["user_id"]
    print(f'📝 Query: "{user_query}"')

    user_profile_data = state.get("user_profile", {})
    user_preferences = user_profile_data.get("preferences", [])
    preference_context = "\n".join(user_preferences) if user_preferences else ""

    all_memories = get_all_memories(user_id)
    profiles = filter_memories_by_type(all_memories, ["profile"])
    profile_memory_context = format_memories_as_context(profiles)

    # --- Regional trending ---
    use_trending = detect_trending_intent(user_query)
    user_geo = user_profile_data.get("location_geo")
    trending_context = ""
    trends = []
    if use_trending and user_geo and user_geo.get("coordinates"):
        coords = user_geo["coordinates"]
        print(f"🌍 Regional intent → $geoNear within 50km of {user_profile_data.get('location')}")
        trends = get_regional_trends(user_id, coords, radius_km=50)
        trending_context = format_trending_context(trends)
    elif use_trending:
        print("⚠️ Regional trending requested but user has no geo location")

    # --- Build search ---
    state["interaction_id"] = str(uuid.uuid4())
    raw_gender = user_profile_data.get("gender", "")
    fav_styles = user_profile_data.get("favorite_styles", [])
    gender_map = {"m": "Men", "f": "Women", "male": "Men", "female": "Women",
                  "boy": "Boys", "girl": "Girls"}
    gender = gender_map.get(raw_gender.lower(), raw_gender) if raw_gender else ""

    profile_context = ""
    if gender:
        profile_context += f" for {gender}"
    if fav_styles:
        profile_context += f", {' '.join(fav_styles[:2])} style"

    enriched_query = user_query + profile_context
    if profile_memory_context:
        enriched_query += f" {profile_memory_context[:200]}"
    if preference_context:
        enriched_query += f" {preference_context[:200]}"

    query_embedding = get_embedding(enriched_query)
    search_filters = extract_search_filters(user_query)
    if gender:
        search_filters["gender"] = [gender, "Unisex"]
    keywords = extract_search_keywords(user_query)

    results = hybrid_search_products(query_embedding, keywords, limit=100, filters=search_filters)

    if trending_context:
        results = rerank_results(user_query + profile_context, results,
                                 trending_context=trending_context, top_k=100)

    # --- Inject trending products at top ---
    if trending_context and trends:
        existing = {r.get("productDisplayName", "").lower() for r in results}
        inject_filter = {"productDisplayName": {"$in": [t["product_name"] for t in trends]}}
        if gender:
            inject_filter["gender"] = {"$in": [gender, "Unisex"]}
        if search_filters.get("season"):
            inject_filter["season"] = {"$in": search_filters["season"]}
        if search_filters.get("exclude_articleType"):
            inject_filter["articleType"] = {"$nin": search_filters["exclude_articleType"]}
        inject_products = list(db["products"].find(inject_filter, {
            "_id": 0, "id": 1, "productDisplayName": 1, "az_img_url": 1, "price": 1,
            "description": 1, "season": 1, "usage": 1, "articleType": 1, "gender": 1,
        }))
        injected = []
        for p in inject_products:
            if p.get("productDisplayName", "").lower() not in existing:
                p["_trending"] = True
                injected.append(p)
        if injected:
            results = injected + results
            print(f"📌 Injected {len(injected)} trending products at top")

    print(f"✅ Found {len(results)} matching products")
    state["search_results"] = results
    state["trending_context"] = trending_context
    state["current_step"] = "discover_complete"
    return state


# ---------------------------------------------------------------------------
# Checkout agent (called directly by the UI "Place Order" button)
# ---------------------------------------------------------------------------

def checkout_agent(state: ShopAgentState) -> ShopAgentState:
    """Place an order for the products the user selected from the search results.

    Expects state['checkout_items'] to be a list of selected products:
        {product_id, product_name, price, image_url}
    """
    print("\n--- 💳 CHECKOUT AGENT ---")
    user_id = state["user_id"]
    checkout_items = state.get("checkout_items", [])

    if not checkout_items:
        print("⚠️ No items selected to checkout")
        state["current_step"] = "checkout_failed"
        return state

    total_price = 0.0
    for item in checkout_items:
        item.setdefault("quantity", 1)
        total_price += item.get("price", 0)
        print(f"  🛒 {item.get('product_name', '')[:40]} — ${item.get('price', 0):.2f}")
    print(f"💰 Total: ${total_price:.2f}")

    interaction_id = state.get("interaction_id") or str(uuid.uuid4())
    order_id = save_order_to_db(user_id, interaction_id, checkout_items, total_price)
    if order_id:
        state["checkout_total"] = total_price
        state["order_id"] = order_id
        state["current_step"] = "checkout_complete"
        print(f"✅ Order created! ID: {order_id}")
        save_order_memory(user_id, checkout_items, total_price)
    else:
        state["current_step"] = "checkout_failed"
    return state


# ---------------------------------------------------------------------------
# Workflow:  discover -> END
# ---------------------------------------------------------------------------

def create_workflow():
    checkpoint_saver = MongoDBSaver(
        client=mongodb_client, db_name=DB_NAME, collection_name="checkpoints_v2"
    )
    workflow = StateGraph(ShopAgentState)
    workflow.add_node("discover", discover_agent)
    workflow.set_entry_point("discover")
    workflow.add_edge("discover", END)
    return workflow.compile(checkpointer=checkpoint_saver)


print("⚙️ Creating and compiling the LangGraph workflow (v2)...")
graph_app = create_workflow()
print("✅ Workflow compiled and ready (v2).")
