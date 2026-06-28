# memory.py
"""
Long-term memory layer (Mem0) + preference extraction.

Two storage layers, just like v1:
  - Mem0 (fashion_memories collection): freeform facts/profile/feedback memories
  - users.preferences array: distilled first-person preference statements
"""
import json
from typing import List, Dict, Optional

from langchain_core.messages import HumanMessage

import clients
from clients import db, mem0_config, llm


def _get_memory():
    """Get or reinitialize the Mem0 memory instance (with a health check)."""
    try:
        clients.memory.vector_store.collection.database.client.admin.command("ping")
        return clients.memory
    except Exception:
        print("🔄 Reinitializing Mem0 memory connection...")
        from mem0 import Memory
        clients.memory = Memory.from_config(mem0_config)
        return clients.memory


def add_memory(text: str, user_id: str, metadata: Optional[Dict] = None):
    """Add a memory entry for a user."""
    try:
        _get_memory().add(text, user_id=user_id, metadata=metadata or {})
        print(f"🧠 Memory added for {user_id}: {text[:80]}...")
    except Exception as e:
        print(f"⚠️ Failed to add memory: {e}")


def _mem0_search(query: str, user_id: str, limit: int) -> list:
    m = _get_memory()
    try:
        return m.search(query, user_id=user_id, limit=limit)
    except Exception:
        return m.search(query, filters={"user_id": user_id}, limit=limit)


def _mem0_get_all(user_id: str) -> list:
    m = _get_memory()
    try:
        return m.get_all(user_id=user_id)
    except Exception:
        return m.get_all(filters={"user_id": user_id})


def search_memories(query: str, user_id: str, limit: int = 5) -> List[Dict]:
    """Search memories relevant to a query for a specific user."""
    try:
        results = _mem0_search(query, user_id, limit)
        memories = results.get("results", []) if isinstance(results, dict) else results
        print(f"🧠 Memory search: {len(memories)} memories loaded for '{query[:50]}'")
        return memories
    except Exception as e:
        print(f"⚠️ Memory search failed: {e}")
        return []


def get_all_memories(user_id: str) -> List[Dict]:
    """Get all stored memories for a user."""
    try:
        results = _mem0_get_all(user_id)
        memories = results.get("results", []) if isinstance(results, dict) else results
        return memories
    except Exception as e:
        print(f"⚠️ Failed to get memories: {e}")
        return []


def format_memories_as_context(memories: List[Dict]) -> str:
    """Format Mem0 entries into a text block for LLM context."""
    if not memories:
        return ""
    lines = []
    for m in memories:
        text = m.get("memory", "") or m.get("text", "") or m.get("payload", {}).get("data", "")
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines)


def filter_memories_by_type(memories: List[Dict], types: List[str]) -> List[Dict]:
    """Filter memories to only include specific types (profile, fact, feedback)."""
    filtered = []
    for m in memories:
        mtype = m.get("metadata", {}).get("type", "") or m.get("payload", {}).get("type", "")
        if mtype in types:
            filtered.append(m)
    return filtered


# ---------------------------------------------------------------------------
# Preference extraction (writes to users.preferences)
# ---------------------------------------------------------------------------

def extract_preference_facts(user_id: str, context: str, event_type: str):
    """Use the LLM to distill lasting preference statements from an event."""
    existing_prefs = []
    try:
        user_doc = db["users"].find_one({"user_id": user_id}, {"preferences": 1})
        if user_doc:
            existing_prefs = user_doc.get("preferences", [])
    except Exception:
        pass

    existing_section = ""
    if existing_prefs:
        existing_section = (
            "\nEXISTING preferences (DO NOT repeat or rephrase these):\n"
            + "\n".join(f"- {p}" for p in existing_prefs)
            + "\n"
        )

    prompt = f"""Based on the {event_type} below, extract 1-3 concise preference facts about this user.
Each fact should be a first-person statement that captures a LASTING preference, NOT a one-time event.

Rules:
- Use the item ATTRIBUTES (colour, type, category, usage, season, price) as your signal.
- Focus on PATTERNS: colour preferences, preferred product types/categories, usage/occasion
  (casual, formal, sports), seasonal leanings, and price range / budget.
- Write as first-person statements, e.g.:
  "I like black footwear.", "I prefer casual wear.", "I often buy sports clothing.",
  "My typical price per item is around $X."
- Generalise from attributes (e.g. colour=Black, type=Casual Shoes -> "I like black casual shoes").
- Do NOT mention specific product/brand names, order IDs, or dates.
- A purchase is strong evidence. If an attribute (a colour, a product type/category, or a
  usage/occasion) is NOT already covered by the existing preferences, add a NEW preference for it.
- Only skip an attribute if the SAME attribute is already in the existing list (e.g. existing
  says "blue" and the item is blue). Different colours/types/usages are always NEW.
- Return an empty array ONLY if EVERY attribute of EVERY purchased item is already covered.
- Return ONLY a JSON array of strings, no explanation.
{existing_section}
Event context:
{context}

JSON array:"""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        facts = json.loads(raw)
        if isinstance(facts, list):
            new_prefs = [f.strip() for f in facts if isinstance(f, str) and f.strip()]
            if new_prefs:
                db["users"].update_one(
                    {"user_id": user_id},
                    {"$addToSet": {"preferences": {"$each": new_prefs}}},
                )
                print(f"🧠 Saved {len(new_prefs)} preferences to profile: {new_prefs}")
            else:
                print(f"🧠 No preferences extracted from {event_type} (empty list)")
    except Exception as e:
        print(f"⚠️ Preference extraction failed: {e}")


def _enrich_items_with_attributes(items: List[Dict]) -> List[Dict]:
    """Look up product attributes (colour, type, usage, season) by product_id so the
    preference extractor has real signal beyond price."""
    ids = [i.get("product_id") for i in items if i.get("product_id") is not None]
    attr_by_id = {}
    if ids:
        try:
            cursor = db["products"].find(
                {"id": {"$in": ids}},
                {"_id": 0, "id": 1, "articleType": 1, "baseColour": 1,
                 "usage": 1, "season": 1, "masterCategory": 1},
            )
            attr_by_id = {doc["id"]: doc for doc in cursor}
        except Exception as e:
            print(f"⚠️ Could not load product attributes: {e}")

    enriched = []
    for it in items:
        attrs = attr_by_id.get(it.get("product_id"), {})
        enriched.append({**it, **attrs})
    return enriched


def save_order_memory(user_id: str, items: List[Dict], total: float):
    """Save a purchase event as a fact + extract durable preferences.

    Item attributes (colour / category / usage / season) are looked up from the
    products collection so the LLM can learn colour/style/category preferences,
    not just budget.
    """
    enriched = _enrich_items_with_attributes(items)

    items_desc = ", ".join(
        [f"{i.get('product_name','')}: ${i.get('price',0):.2f}" for i in items]
    )
    # Attribute-rich description for the preference extractor
    attr_lines = []
    for i in enriched:
        parts = []
        if i.get("baseColour"):
            parts.append(f"colour={i['baseColour']}")
        if i.get("articleType"):
            parts.append(f"type={i['articleType']}")
        if i.get("masterCategory"):
            parts.append(f"category={i['masterCategory']}")
        if i.get("usage"):
            parts.append(f"usage={i['usage']}")
        if i.get("season"):
            parts.append(f"season={i['season']}")
        parts.append(f"price=${i.get('price', 0):.2f}")
        attr_lines.append("  - " + ", ".join(parts))
    attr_block = "\n".join(attr_lines)

    avg_price = total / len(items) if items else 0
    add_memory(
        f"I purchased {items_desc} for ${total:.2f} total.",
        user_id,
        metadata={"type": "fact", "source": "order"},
    )
    context = (
        f"User PURCHASED {len(items)} item(s) for ${total:.2f} total "
        f"(average ${avg_price:.2f} per item). This is a confirmed purchase, "
        f"which is a strong signal of preference.\n"
        f"Purchased item attributes:\n{attr_block}"
    )
    print(f"🧠 Order context: {context[:160]}")
    extract_preference_facts(user_id, context, "order")


def save_user_profile_memory(user_id: str, profile: Dict):
    """Save the user profile to Mem0 (idempotent-ish; Mem0 dedupes)."""
    gender = profile.get("gender", "unknown")
    age = profile.get("age", "unknown")
    location = profile.get("location", "unknown")
    colors = ", ".join(profile.get("favorite_colors", []) or ["not specified"])
    styles = ", ".join(profile.get("favorite_styles", []) or ["not specified"])
    text = (
        f"I am {gender}, {age} years old, living in {location}. "
        f"My favorite colors are {colors}. "
        f"I prefer {styles} style clothing."
    )
    add_memory(text, user_id, metadata={"type": "profile"})
