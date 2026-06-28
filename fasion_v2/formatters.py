# formatters.py
"""
HTML formatters for the Gradio UI (profile, order history).
"""
from typing import List, Dict


def format_profile_html(profile: Dict) -> str:
    if not profile:
        return "<p>No profile found</p>"
    avatar_url = profile.get("avatar_url", "")
    avatar_html = (
        f'<img src="{avatar_url}" style="width: 200px; height: 200px; border-radius: 12px; object-fit: cover;">'
        if avatar_url else ""
    )
    pref_html = ""
    prefs = profile.get("preferences", [])
    if prefs:
        pref_html = (
            '<div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.2);">'
            '<strong style="font-size: 13px;">🧠 Learned preferences:</strong>'
            '<ul style="margin: 5px 0 0 0; padding-left: 18px; font-size: 13px; opacity: 0.9;">'
        )
        for text in prefs[:10]:
            pref_html += f"<li>{text[:120]}</li>"
        pref_html += "</ul></div>"

    return f"""
    <div style="background: linear-gradient(135deg, #7ba7d9 0%, #6b9fd4 50%, #5a8bbf 100%); padding: 25px; border-radius: 15px; color: white; box-shadow: 0 10px 25px rgba(0,0,0,0.1);">
        <div style="display: flex; align-items: center; gap: 25px;">
            <div style="flex-shrink: 0;">{avatar_html}</div>
            <div style="flex: 1; min-width: 0;">
                <h2 style="margin: 0 0 4px 0;">👤 {profile.get('username', 'Unknown')}</h2>
                <p style="margin: 0 0 10px 0; opacity: 0.9; font-size: 16px;">{profile.get('full_name', 'N/A')}</p>
                <div style="font-size: 14px; line-height: 1.8;">
                    <strong>Gender:</strong> {profile.get('gender', 'N/A')} · <strong>Age:</strong> {profile.get('age', 'N/A')} · <strong>Location:</strong> {profile.get('location', 'N/A')}<br>
                    <strong>Colors:</strong> {', '.join(profile.get('favorite_colors', [])[:3])} · <strong>Styles:</strong> {', '.join(profile.get('favorite_styles', [])[:3])}
                </div>
                <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.2);">
                    <em style="font-size: 13px;">"{profile.get('bio', 'No bio available')}"</em>
                </div>
                {pref_html}
            </div>
        </div>
    </div>
    """


def _format_order_card(order: Dict, index: int) -> str:
    """Render a single order as a compact card."""
    order_id = str(order.get("_id", order.get("order_id", "")))
    items = order.get("items", [])
    total = order.get("total_price", 0)
    status = order.get("status", "pending")
    created = order.get("created_at")
    when = created.strftime("%Y-%m-%d %H:%M") if hasattr(created, "strftime") else ""

    status_colors = {"pending": "#ff9800", "completed": "#4CAF50", "cancelled": "#f44336"}
    status_color = status_colors.get(status, "#999")

    items_html = ""
    for item in items:
        items_html += f"""
        <div style="display:flex; align-items:center; padding:8px 4px; border-top:1px solid #f0f0f0;">
            <img src="{item.get('image_url','')}" style="width:48px; height:48px; object-fit:cover; border-radius:6px; margin-right:12px;"
                 onerror="this.src='https://via.placeholder.com/48?text=No+Img'">
            <div style="flex:1; font-size:13px; color:#333;">{item.get('product_name','')[:48]}
                <span style="color:#aaa; font-size:11px;"> · ×{item.get('quantity',1)}</span>
            </div>
            <div style="font-weight:600; color:#4CAF50;">${item.get('price',0):.2f}</div>
        </div>
        """

    return f"""
    <div style="background:white; border:1px solid #e6e6ee; border-radius:14px; padding:18px;
                margin-bottom:16px; box-shadow:0 2px 10px rgba(0,0,0,0.06);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <div>
                <span style="font-weight:700; color:#1a1a2e;">Order #{index}</span>
                <span style="font-family:monospace; font-size:11px; color:#aaa; margin-left:8px;">{order_id}</span>
            </div>
            <span style="background:{status_color}; color:white; font-size:11px; font-weight:700;
                         padding:3px 10px; border-radius:10px; text-transform:uppercase;">{status}</span>
        </div>
        <div style="font-size:12px; color:#999; margin-bottom:6px;">🕒 {when} · {len(items)} item(s)</div>
        {items_html}
        <div style="display:flex; justify-content:flex-end; align-items:center; margin-top:10px;
                    padding-top:10px; border-top:2px solid #f0f0f0;">
            <span style="font-size:14px; color:#777; margin-right:10px;">Total</span>
            <span style="font-size:20px; font-weight:700; color:#2e7d32;">${total:.2f}</span>
        </div>
    </div>
    """


def format_orders_history_html(orders: List[Dict]) -> str:
    """Render a user's full order history (most recent first)."""
    if not orders:
        return "<p style='text-align:center; color:#999;'>No orders yet.</p>"
    grand_total = sum(o.get("total_price", 0) for o in orders)
    header = f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;
                padding:14px 18px; background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
                color:white; border-radius:12px;">
        <span style="font-size:16px; font-weight:600;">📦 {len(orders)} order(s)</span>
        <span style="font-size:15px;">Lifetime spend: <b>${grand_total:.2f}</b></span>
    </div>
    """
    cards = "".join(_format_order_card(o, i) for i, o in enumerate(orders, 1))
    return f'<div style="max-width:640px; margin:0 auto;">{header}{cards}</div>'
