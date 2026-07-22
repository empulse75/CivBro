from __future__ import annotations

import traceback
from pathlib import Path

import gradio as gr

EXTENSION_DIR = Path(__file__).parent.parent.resolve()
FRONTEND_DIST = EXTENSION_DIR / "frontend" / "dist"
BACKEND_SRC = EXTENSION_DIR / "backend" / "src"

HAS_BACKEND = (BACKEND_SRC / "main.py").exists()


def on_app_started(demo: gr.Blocks, app):
    if not HAS_BACKEND:
        print("[CivBro] Backend main.py not found - skipping")
        return

    import sys
    backend_pkg = str(BACKEND_SRC.parent)
    backend_src = str(BACKEND_SRC)
    for p in (backend_src, backend_pkg):
        if p not in sys.path:
            sys.path.insert(0, p)

    try:
        from src.main import register_routes
    except ImportError as e:
        print(f"[CivBro] Failed to import backend: {e}")
        traceback.print_exc()
        return

    try:
        register_routes(app)
        print("[CivBro] API routes registered on WebUI FastAPI app")
    except Exception as e:
        print(f"[CivBro] Failed to register routes: {e}")
        traceback.print_exc()
        return

    if FRONTEND_DIST.exists():
        try:
            from fastapi.staticfiles import StaticFiles
            app.mount(
                "/civbro",
                StaticFiles(directory=str(FRONTEND_DIST), html=True),
                name="civbro_static",
            )
            print(f"[CivBro] Mounted frontend from {FRONTEND_DIST}")
        except Exception as e:
            print(f"[CivBro] Failed to mount frontend: {e}")
    else:
        print(f"[CivBro] Frontend dist not found at {FRONTEND_DIST}")


def on_ui_tabs():
    iframe_html = """
<div style="width: 100%; height: calc(100vh - 120px); overflow: hidden; border: none;">
    <iframe
        src="/civbro/"
        style="width: 100%; height: 100%; border: none;"
        frameborder="0"
    ></iframe>
</div>
    """
    with gr.Blocks() as civbro_block:
        gr.HTML(value=iframe_html)

    return [(civbro_block, "CivBro", "civbro_tab")]


try:
    from modules import script_callbacks
    script_callbacks.on_app_started(on_app_started)
    script_callbacks.on_ui_tabs(on_ui_tabs)
    print("[CivBro] Registered WebUI callbacks")
except ImportError as e:
    print(f"[CivBro] Not running inside WebUI, hooks not registered: {e}")
