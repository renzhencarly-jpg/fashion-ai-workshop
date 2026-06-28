# ui.py
"""
Gradio interface + streaming handlers for the Shopping Guide AI (v2).

Workflow:
  🔍 Search Products -> stage_search (LangGraph: discover -> END)
  Tick the box on each product card you want
  🛒 Add to Cart -> jump to the Cart tab
  💳 Place Order -> order-summary confirmation popup
  ✅ Confirm Order -> run_checkout_action (saves the order)
"""
import io
from datetime import datetime
from contextlib import redirect_stdout

import gradio as gr

from agents import graph_app, checkout_agent
from db import get_user_profile, get_active_session, save_active_session, get_user_orders
from memory import get_all_memories, save_user_profile_memory
from formatters import format_profile_html, format_orders_history_html


# Pagination for the Search Results grid
PAGE_SIZE = 20      # products per page
MAX_PAGES = 5       # show at most 5 pages (=> up to 100 products)

custom_css = """
    .gradio-container { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    .output-html { border-radius: 15px; overflow: hidden; }
    .stage-btn { min-height: 42px !important; font-size: 15px !important; }
    #user-id-input { padding: 4px 0 !important; }
    #user-id-input .wrap { display: flex !important; flex-direction: row !important; align-items: center !important; gap: 8px !important; }
    #user-id-input > label { margin-bottom: 0 !important; white-space: nowrap; min-width: fit-content; }
    #user-id-input input { flex: 1; }
    /* --- Search results: product card (image + caption + corner tick box) --- */
    .product-card { position: relative !important; border: 1px solid #e0e0e0; border-radius: 12px;
        padding: 12px; text-align: center; background: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
    .product-card img { width: 100%; height: 320px; object-fit: contain; border-radius: 10px;
        background: #f7f7f9; image-rendering: -webkit-optimize-contrast; }
    .product-name { font-size: 13px; color: #333; margin-top: 10px; min-height: 36px; line-height: 1.3; }
    .product-price { font-size: 24px; font-weight: 800; color: #4CAF50; margin-top: 4px; }
    .product-id { font-size: 10px; color: #aaa; }
    /* tick box pinned to the TOP-RIGHT corner of each card, with visible label */
    .pick-box { position: absolute !important; top: 10px; right: 10px; z-index: 5;
        background: rgba(255,255,255,0.95); border-radius: 8px; padding: 4px 8px;
        min-width: 0 !important; width: auto !important; flex: 0 0 auto !important;
        box-shadow: 0 1px 5px rgba(0,0,0,0.20); }
    .pick-box label { gap: 6px !important; margin: 0 !important; align-items: center !important;
        font-size: 12px !important; font-weight: 600 !important; color: #333 !important; }
    .pick-box input[type="checkbox"] { width: 18px !important; height: 18px !important; cursor: pointer; }
    .trending-badge { position: absolute; top: 10px; left: 10px; background: #ff5722; color: white;
        font-size: 10px; padding: 1px 6px; border-radius: 8px; z-index: 5; }
    /* Order-summary confirmation popup (modal overlay) */
    #order-modal {
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(0,0,0,0.45); z-index: 1000;
        display: flex; align-items: center; justify-content: center;
    }
    #order-modal > .form, #order-modal > div {
        background: transparent;
    }
    #order-modal-inner {
        background: white; border-radius: 16px; padding: 24px;
        max-width: 560px; width: 90%; max-height: 80vh; overflow-y: auto;
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    }
    #log-container { position: sticky; bottom: 0; z-index: 100; background: var(--background-fill-primary); border-top: 2px solid var(--border-color-primary); box-shadow: 0 -4px 12px rgba(0,0,0,0.08); margin: 0 -16px; padding: 0 16px 8px 16px; }
    #log-container textarea { resize: vertical !important; min-height: 60px; max-height: 300px; overflow-y: auto !important; }
"""


def _cart_item(product: dict) -> dict:
    """Normalize a search-result product into a checkout/cart item."""
    return {
        "product_id": product.get("id"),
        "product_name": product.get("productDisplayName", "Unknown"),
        "price": product.get("price", 0),
        "image_url": product.get("az_img_url", ""),
    }


def _num_pages(results: list) -> int:
    """Number of pages we will show (capped at MAX_PAGES)."""
    if not results:
        return 0
    total = min(len(results), PAGE_SIZE * MAX_PAGES)
    return (total + PAGE_SIZE - 1) // PAGE_SIZE


def page_slice(results: list, page: int) -> list:
    """Return the products belonging to `page` (1-indexed), capped to MAX_PAGES."""
    pages = _num_pages(results)
    if pages == 0:
        return []
    page = max(1, min(page, pages))
    start = (page - 1) * PAGE_SIZE
    return (results or [])[start:start + PAGE_SIZE]


def page_label_text(results: list, page: int) -> str:
    pages = _num_pages(results)
    if pages == 0:
        return ""
    page = max(1, min(page, pages))
    total_shown = min(len(results), PAGE_SIZE * MAX_PAGES)
    return f"Page {page} / {pages} · {total_shown} products"


# Card style snippets used inside @gr.render
# Source product images are only 60x80 px, so we display them at a modest size
# (less upscaling = sharper) and let the browser keep aspect ratio.
_CARD_IMG_STYLE = ("width:auto;max-width:100%;height:200px;object-fit:contain;border-radius:10px;"
                   "background:#f7f7f9;image-rendering:-webkit-optimize-contrast;margin:0 auto;display:block;")
_CARD_NAME_STYLE = "font-size:13px;color:#333;margin-top:10px;min-height:36px;line-height:1.3;"
_CARD_PRICE_STYLE = "font-size:24px;font-weight:800;color:#4CAF50;margin-top:4px;"
_CARD_ID_STYLE = "font-size:10px;color:#aaa;"


def product_card_html(item: dict) -> str:
    """Inner HTML (image + caption) for one product card."""
    name = item.get("productDisplayName", "Unknown")[:40]
    price = item.get("price", 0)
    img = item.get("az_img_url", "")
    pid = item.get("id", "")
    badge = '<span class="trending-badge">🔥 trending</span>' if item.get("_trending") else ""
    return (
        f'{badge}'
        f'<img src="{img}" style="{_CARD_IMG_STYLE}" onerror="this.src=\'https://via.placeholder.com/320?text=No+Image\'">'
        f'<div style="{_CARD_NAME_STYLE}">{name}</div>'
        f'<div style="{_CARD_PRICE_STYLE}">${price:.2f}</div>'
        f'<div style="{_CARD_ID_STYLE}">#{pid}</div>'
    )


def _order_summary_html(cart: dict) -> str:
    """Render the order-summary table shown in the confirmation popup."""
    items = list(cart.values())
    if not items:
        return "<p style='color:#999;'>Your cart is empty. Tick some products first.</p>"
    total = sum(i.get("price", 0) for i in items)
    rows = ""
    for idx, item in enumerate(items, 1):
        rows += f"""
        <div style="display:flex; align-items:center; padding:10px; border-bottom:1px solid #eee;">
            <div style="width:28px; color:#999;">{idx}</div>
            <img src="{item['image_url']}" style="width:54px; height:54px; object-fit:cover; border-radius:8px; margin:0 12px;"
                 onerror="this.src='https://via.placeholder.com/54?text=No+Img'">
            <div style="flex:1; font-size:14px; color:#333;">{item['product_name'][:48]}
                <div style="font-size:11px; color:#aaa;">#{item['product_id']}</div>
            </div>
            <div style="font-weight:bold; color:#4CAF50;">${item['price']:.2f}</div>
        </div>
        """
    return f"""
    <h2 style="margin:0 0 6px 0; color:#1a1a2e;">🧾 Order Summary</h2>
    <p style="margin:0 0 14px 0; color:#777; font-size:13px;">Please review your order before placing it.</p>
    <div style="border:1px solid #eee; border-radius:10px;">{rows}</div>
    <div style="display:flex; justify-content:space-between; align-items:center;
                margin-top:16px; padding:14px 10px; background:#e8f5e9; border-radius:10px;">
        <span style="font-size:16px; color:#2e7d32;">Total ({len(items)} item{'s' if len(items)!=1 else ''})</span>
        <span style="font-size:24px; font-weight:bold; color:#2e7d32;">${total:.2f}</span>
    </div>
    """


# ---------------------------------------------------------------------------
# Stage 1: Search products
# ---------------------------------------------------------------------------

def stage_search(state_dict, user_id: str, query: str, new_session: bool, existing_log: str):
    import time

    # out() slots: status, profile_html, results_state, page_state, page_products(@render), page_label, agent_state
    def out(status, profile, results, page, page_products, label, sd):
        return status, profile, results, page, page_products, label, sd

    if not user_id or not user_id.strip():
        yield out((existing_log or "") + "\n⚠️ Please enter a User ID.", "", [], 1, [], "", state_dict or {})
        return
    if not query or not query.strip():
        yield out((existing_log or "") + "\n⚠️ Please enter a fashion request.", "", [], 1, [], "", state_dict or {})
        return

    status = (existing_log or "").rstrip() + "\n"
    state_dict = state_dict or {}
    profile_html = ""

    # Auto-load profile if missing or user changed
    if not state_dict.get("user_profile") or state_dict.get("user_id") != user_id.strip():
        status += "👤 Loading user profile...\n"
        yield out(status, profile_html, [], 1, [], "", state_dict)

        user_profile = get_user_profile(user_id)
        if not user_profile:
            status += f"❌ User '{user_id}' not found in database.\n"
            yield out(status, "", [], 1, [], "", {})
            return

        save_user_profile_memory(user_id, user_profile)
        profile_html = format_profile_html(user_profile)
        user_memories = get_all_memories(user_id)
        status += (
            f"✅ Profile loaded: {user_profile.get('username')}\n"
            f"🧠 {len(user_memories)} memories, "
            f"{len(user_profile.get('preferences', []))} preferences\n"
        )
        state_dict.update({
            "user_id": user_id.strip(),
            "user_profile": user_profile,
        })
    else:
        user_profile = get_user_profile(state_dict["user_id"])
        if user_profile:
            state_dict["user_profile"] = user_profile
        profile_html = format_profile_html(state_dict["user_profile"])

    user_id = state_dict["user_id"]
    user_profile = state_dict["user_profile"]

    status += "🔍 Searching...\n"
    yield out(status, profile_html, [], 1, [], "", state_dict)

    # Session management
    thread_id = None if new_session else get_active_session(user_id)
    if not thread_id:
        thread_id = f"thread_{user_id}_{int(datetime.utcnow().timestamp())}"
        save_active_session(user_id, thread_id)
    config = {"configurable": {"thread_id": thread_id}}

    input_state = {
        "user_id": user_id,
        "user_profile": user_profile,
        "user_query": query,
        "messages": [],
        "current_step": "start",
        "trending_context": state_dict.get("trending_context", ""),
    }

    log_stream = io.StringIO()
    try:
        with redirect_stdout(log_stream):
            final_state = input_state
            for step in graph_app.stream(input_state, config):
                node_name = list(step.keys())[0]
                if node_name == "__end__":
                    break
                final_state = {**final_state, **list(step.values())[0]}
                captured = log_stream.getvalue()
                if captured:
                    status += captured
                    log_stream.seek(0); log_stream.truncate(0)
                    yield out(status, profile_html, [], 1, [], "", state_dict)

        status += log_stream.getvalue()

        results = final_state.get("search_results", [])[:PAGE_SIZE * MAX_PAGES]
        state_dict.update({
            "user_query": query,
            "search_results": results,
            "interaction_id": final_state.get("interaction_id"),
            "current_step": "searched",
            "thread_id": thread_id,
            "trending_context": final_state.get("trending_context", ""),
        })

        if not results:
            status += "\n⚠️ No products found. Try a different query."
            yield out(status, profile_html, [], 1, [], "", state_dict)
            return

        pages = _num_pages(results)
        # Show the FIRST page immediately, then "load" the remaining pages in the background.
        status += f"\n🛍️ {len(results)} products found across {pages} page(s). Loading page 1..."
        yield out(status, profile_html, results, 1,
                  page_slice(results, 1), page_label_text(results, 1), state_dict)

        for p in range(2, pages + 1):
            time.sleep(0.4)  # simulate background loading of subsequent pages
            status += f"\n   ✅ Page {p} ready."
            yield out(status, profile_html, results, 1,
                      page_slice(results, 1), page_label_text(results, 1), state_dict)

        status += "\n   ✨ All pages loaded. Use ◀ Prev / Next ▶ to browse."
        yield out(status, profile_html, results, 1,
                  page_slice(results, 1), page_label_text(results, 1), state_dict)

    except Exception as e:
        status += log_stream.getvalue() + f"\n❌ ERROR: {e}"
        yield out(status, profile_html, [], 1, [], "", state_dict)


# ---------------------------------------------------------------------------
# Search-results pagination
# ---------------------------------------------------------------------------

def change_page(results: list, page: int, delta: int):
    """Move to the previous/next page of search results."""
    pages = _num_pages(results or [])
    if pages == 0:
        return 1, [], ""
    new_page = max(1, min((page or 1) + delta, pages))
    return new_page, page_slice(results, new_page), page_label_text(results, new_page)


# ---------------------------------------------------------------------------
# Stage 2: Open the order-summary confirmation popup
# ---------------------------------------------------------------------------

def open_order_popup(cart: dict, existing_log: str):
    """Validate the cart and show the confirmation popup."""
    if not cart:
        return (
            (existing_log or "").rstrip() + "\n⚠️ Tick at least one product before ordering.",
            gr.update(visible=False),
            "",
        )
    return (
        existing_log or "",
        gr.update(visible=True),
        _order_summary_html(cart),
    )


def close_order_popup():
    # Hide the popup and jump back to the Search Results tab.
    return gr.update(visible=False), gr.Tabs(selected="tab_search")


# ---------------------------------------------------------------------------
# Stage 3: Confirm -> place the order
# ---------------------------------------------------------------------------

def run_checkout_action(state_dict, cart: dict, existing_log: str):
    # Always hide the popup when we finish; keep the cart/tab unchanged on early exits.
    hide = gr.update(visible=False)
    keep_cart = gr.update()
    keep_tab = gr.update()

    if not state_dict or not state_dict.get("search_results"):
        yield (existing_log or "") + "\n⚠️ Search for products first.", gr.update(), state_dict, hide, keep_cart, keep_tab
        return
    if not cart:
        yield (existing_log or "") + "\n⚠️ Your cart is empty.", gr.update(), state_dict, hide, keep_cart, keep_tab
        return

    checkout_items = list(cart.values())
    agent_state = {
        "user_id": state_dict["user_id"],
        "interaction_id": state_dict.get("interaction_id"),
        "checkout_items": checkout_items,
        "messages": [],
    }

    status = (existing_log or "").rstrip() + f"\n💳 Placing order for {len(checkout_items)} item(s)...\n"
    yield status, gr.update(), state_dict, hide, keep_cart, keep_tab

    log_stream = io.StringIO()
    try:
        with redirect_stdout(log_stream):
            result = checkout_agent(agent_state)
        status += log_stream.getvalue()

        if result.get("order_id"):
            state_dict["order_id"] = result["order_id"]
            status += f"\n✅ Order placed! ID: {result['order_id']}"
            # Reload full order history, clear the cart, jump to the Order tab.
            orders = get_user_orders(state_dict["user_id"])
            orders_html = format_orders_history_html(orders)
            yield status, orders_html, state_dict, hide, {}, gr.Tabs(selected="tab_order")
        else:
            status += "\n⚠️ Checkout failed."
            yield status, gr.update(), state_dict, hide, keep_cart, keep_tab
    except Exception as e:
        status += log_stream.getvalue() + f"\n❌ Error: {e}"
        yield status, gr.update(), state_dict, hide, keep_cart, keep_tab


def load_order_history(state_dict):
    """Load the user's order history for the Order tab."""
    if not state_dict or not state_dict.get("user_id"):
        return "<p style='color:#999;'>Search as a user first to see order history.</p>"
    orders = get_user_orders(state_dict["user_id"])
    return format_orders_history_html(orders)


def go_to_cart():
    """Jump to the Cart tab. The cart summary is shown on the Cart tab itself,
    so this is a pure navigation action and does not touch the processing log."""
    return gr.Tabs(selected="tab_cart")


# ---------------------------------------------------------------------------
# Build Gradio app
# ---------------------------------------------------------------------------

def create_gradio_app():
    with gr.Blocks(
        title="Shopping Guide AI (v2)",
        theme=gr.themes.Soft(primary_hue="indigo"),
        css=custom_css,
    ) as demo:
        agent_state = gr.State(value={})
        cart_state = gr.State(value={})            # product_id -> cart item
        results_state = gr.State(value=[])         # all search-result products
        page_state = gr.State(value=1)             # current search-results page
        page_products = gr.State(value=[])         # products of the current page (drives @render)

        gr.Markdown(
            """<div style="display:flex; justify-content:space-between; align-items:center;">
<span style="font-size:18px;font-weight:bold;">🛍️ Shopping Guide AI <span style='font-weight:normal;color:#666;font-size:14px'>· v2 · LangGraph + MongoDB + Mem0</span></span>
</div>"""
        )

        with gr.Row():
            with gr.Column(scale=1):
                user_id_input = gr.Textbox(
                    label="User ID", value="user_101", placeholder="user_101",
                    lines=1, elem_id="user-id-input",
                )
                query_input = gr.Textbox(
                    label="Fashion Request",
                    placeholder="e.g., 'I need summer outfits for a beach vacation'",
                    lines=2,
                )
                new_session_check = gr.Checkbox(label="Start new conversation", value=False)

                gr.Markdown("#### 🚀 Workflow")
                btn_search = gr.Button("🔍 Search Products", elem_classes=["stage-btn"])
                btn_add_cart = gr.Button("🛒 Add to Cart", elem_classes=["stage-btn"])
                btn_order = gr.Button("💳 Place Order", variant="stop", elem_classes=["stage-btn"])

            with gr.Column(scale=2):
                gr.Markdown("#### 📋 Results")
                with gr.Tabs() as result_tabs:
                    with gr.Tab("👤 Profile", id="tab_profile"):
                        profile_output = gr.HTML()
                    with gr.Tab("🔍 Search Results", id="tab_search"):
                        # Paginated 4-per-row grid; each card has a tick box (top-right) to add to cart.
                        page_label = gr.Markdown("")

                        @gr.render(inputs=[page_products])
                        def render_products(products):
                            if not products:
                                gr.Markdown("*No products yet. Run a search.*")
                                return
                            for row_start in range(0, len(products), 4):
                                with gr.Row():
                                    for product in products[row_start:row_start + 4]:
                                        with gr.Column(min_width=180):
                                            with gr.Group(elem_classes=["product-card"]):
                                                gr.HTML(product_card_html(product))
                                                cb = gr.Checkbox(
                                                    label="Add to cart", value=False,
                                                    container=False, elem_classes=["pick-box"],
                                                )

                                                def _toggle(checked, cart, p=product):
                                                    cart = dict(cart or {})
                                                    pid = p.get("id")
                                                    if checked:
                                                        cart[pid] = _cart_item(p)
                                                    else:
                                                        cart.pop(pid, None)
                                                    return cart

                                                cb.change(
                                                    _toggle,
                                                    inputs=[cb, cart_state],
                                                    outputs=[cart_state],
                                                )
                        with gr.Row():
                            btn_prev = gr.Button("◀ Prev", size="sm")
                            btn_next = gr.Button("Next ▶", size="sm")
                    with gr.Tab("🛒 Cart", id="tab_cart"):
                        # Dynamically rendered cart contents, each item removable.
                        @gr.render(inputs=cart_state)
                        def render_cart(cart):
                            items = list((cart or {}).values())
                            if not items:
                                gr.Markdown("*Your cart is empty. Tick 'Add to cart' on the Search Results tab.*")
                                return
                            total = sum(i.get("price", 0) for i in items)
                            gr.Markdown(f"### 🛒 {len(items)} item(s) · **${total:.2f}**")
                            for item in items:
                                with gr.Row(equal_height=True):
                                    gr.HTML(
                                        f'<div style="display:flex;align-items:center;gap:12px;">'
                                        f'<img src="{item["image_url"]}" style="width:64px;height:64px;object-fit:cover;border-radius:8px;" '
                                        f'onerror="this.src=\'https://via.placeholder.com/64?text=No+Img\'">'
                                        f'<div><div style="font-weight:600;color:#222;">{item["product_name"][:50]}</div>'
                                        f'<div style="color:#4CAF50;font-weight:700;">${item["price"]:.2f}</div></div></div>'
                                    )
                                    remove_btn = gr.Button("🗑️ Remove", scale=0, min_width=110)

                                    def _remove(cart, it=item):
                                        cart = dict(cart or {})
                                        cart.pop(it.get("product_id"), None)
                                        return cart

                                    remove_btn.click(
                                        _remove,
                                        inputs=[cart_state],
                                        outputs=[cart_state],
                                    )
                    with gr.Tab("💳 Order", id="tab_order") as order_tab:
                        gr.Markdown("##### 📦 Your order history")
                        order_output = gr.HTML("<p style='color:#999;'>No orders yet.</p>")

        # --- Order-summary confirmation popup (hidden by default) ---
        with gr.Group(visible=False, elem_id="order-modal") as order_modal:
            with gr.Group(elem_id="order-modal-inner"):
                order_summary_html = gr.HTML()
                with gr.Row():
                    btn_cancel = gr.Button("Cancel")
                    btn_confirm = gr.Button("✅ Confirm Order", variant="primary")

        with gr.Accordion("📝 Processing Log", open=True, elem_id="log-container"):
            status_output = gr.Textbox(lines=12, max_lines=100, interactive=False, show_label=False)

        gr.Markdown(
            """
            ---
            **Flow:** Search → tick products → Add to Cart → Place Order → review summary → ✅ Confirm &nbsp;|&nbsp;
            LangGraph · MongoDB · Azure OpenAI · Voyage AI · Mem0
            """
        )

        # --- Wiring ---
        btn_search.click(
            fn=stage_search,
            inputs=[agent_state, user_id_input, query_input, new_session_check, status_output],
            outputs=[status_output, profile_output, results_state, page_state,
                     page_products, page_label, agent_state],
        )

        # Search-results pagination
        btn_prev.click(
            fn=lambda r, p: change_page(r, p, -1),
            inputs=[results_state, page_state],
            outputs=[page_state, page_products, page_label],
        )
        btn_next.click(
            fn=lambda r, p: change_page(r, p, +1),
            inputs=[results_state, page_state],
            outputs=[page_state, page_products, page_label],
        )

        # Add to Cart -> jump to the Cart tab (pure navigation, no log refresh)
        btn_add_cart.click(
            fn=go_to_cart,
            inputs=None,
            outputs=[result_tabs],
        )

        # Place Order -> open confirmation popup
        btn_order.click(
            fn=open_order_popup,
            inputs=[cart_state, status_output],
            outputs=[status_output, order_modal, order_summary_html],
        )
        # Cancel -> close popup and jump back to Search Results
        btn_cancel.click(fn=close_order_popup, outputs=[order_modal, result_tabs])
        # Confirm -> place the order, refresh order history, clear cart, jump to Order tab
        btn_confirm.click(
            fn=run_checkout_action,
            inputs=[agent_state, cart_state, status_output],
            outputs=[status_output, order_output, agent_state, order_modal, cart_state, result_tabs],
        )
        # Refresh order history whenever the Order tab is opened
        order_tab.select(
            fn=load_order_history,
            inputs=[agent_state],
            outputs=[order_output],
        )

    return demo
