# app.py
"""
Shopping Guide AI (Fashion v2) — entry point.

A fashion shopping-guide built on LangGraph + MongoDB Atlas + Mem0.
Workflow: Search Products -> select products -> Place Order.

Removed vs the original Fashion AI:
  - Outfit generation + AI outfit images (no Gemini / no OpenAI image calls)
  - Virtual try-on

Run:
    python app.py
Then open http://localhost:7861/
"""
import os

import gradio as gr

from config import PORT
from ui import create_gradio_app


if __name__ == "__main__":
    print("=" * 40)
    print("SHOPPING GUIDE AI — v2 (LangGraph + MongoDB + Mem0)")
    print("=" * 40)
    print("\n🚀 Starting server...\n")

    demo = create_gradio_app()

    import fastapi
    import uvicorn

    app_fastapi = fastapi.FastAPI()
    app_fastapi = gr.mount_gradio_app(app_fastapi, demo, path="/")

    print(f"🏠 Main app: http://localhost:{PORT}/")
    uvicorn.run(app_fastapi, host="0.0.0.0", port=int(os.environ.get("PORT", PORT)))
