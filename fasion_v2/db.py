# db.py
"""
MongoDB data-access helpers: user profiles, geocoding,
orders and session management.
"""
from datetime import datetime
from typing import List, Dict, Optional

import requests

from clients import db


# ---------------------------------------------------------------------------
# Geocoding (OpenStreetMap Nominatim)
# ---------------------------------------------------------------------------

def geocode_location(location_str: str) -> Optional[Dict]:
    """Geocode a location string to a GeoJSON Point {type, coordinates:[lng,lat]}."""
    if not location_str or not location_str.strip():
        return None
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location_str, "format": "json", "limit": 1},
            headers={"User-Agent": "ShoppingGuideAI/2.0"},
            timeout=5,
        )
        data = resp.json()
        if data:
            return {
                "type": "Point",
                "coordinates": [float(data[0]["lon"]), float(data[0]["lat"])],
            }
    except Exception as e:
        print(f"⚠️ Geocoding failed for '{location_str}': {e}")
    return None


def ensure_user_geo(user_id: str, profile: Dict) -> Dict:
    """Ensure the user profile has location_geo; geocode + persist if missing."""
    if profile.get("location_geo"):
        return profile
    geo = geocode_location(profile.get("location", ""))
    if geo:
        db["users"].update_one({"user_id": user_id}, {"$set": {"location_geo": geo}})
        profile["location_geo"] = geo
        print(f"📍 Geocoded '{profile.get('location')}' → {geo['coordinates']}")
    return profile


# ---------------------------------------------------------------------------
# User profiles
# ---------------------------------------------------------------------------

def get_user_profile(user_id: str) -> Optional[Dict]:
    """Get a user profile from MongoDB (auto-geocode if needed)."""
    try:
        profile = db["users"].find_one({"user_id": user_id}, {"_id": 0})
        if profile:
            profile = ensure_user_geo(user_id, profile)
        return profile
    except Exception as e:
        print(f"Error loading profile: {e}")
        return None


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

def save_order_to_db(user_id: str, interaction_id: str, items: List[Dict],
                     total: float) -> Optional[str]:
    """Persist an order."""
    try:
        result = db["orders"].insert_one({
            "user_id": user_id,
            "interaction_id": interaction_id,
            "items": items,
            "total_price": total,
            "currency": "USD",
            "status": "pending",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        order_id = str(result.inserted_id)
        print(f"💳 Order saved — ID: {order_id} | Items: {len(items)} | Total: ${total:.2f}")
        return order_id
    except Exception as e:
        print(f"Error saving order: {e}")
        return None


def get_user_orders(user_id: str) -> List[Dict]:
    """Return all orders for a user, most recent first."""
    try:
        return list(db["orders"].find({"user_id": user_id}).sort("created_at", -1))
    except Exception as e:
        print(f"Error loading orders: {e}")
        return []


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def get_active_session(user_id: str) -> Optional[str]:
    try:
        user = db["users"].find_one({"user_id": user_id})
        return user.get("last_thread_id") if user else None
    except Exception:
        return None


def save_active_session(user_id: str, thread_id: str):
    try:
        db["users"].update_one(
            {"user_id": user_id},
            {"$set": {"last_thread_id": thread_id}},
            upsert=True,
        )
    except Exception:
        pass
