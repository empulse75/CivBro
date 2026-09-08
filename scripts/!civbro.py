from __future__ import annotations

import sys
import traceback
from pathlib import Path

import gradio as gr
from fastapi import APIRouter, Depends, Request
from fastapi.staticfiles import StaticFiles

EXTENSION_DIR = Path(__file__).resolve().parents[1]
BACKEND_PKG_DIR = EXTENSION_DIR / "backend"
BACKEND_SRC = BACKEND_PKG_DIR / "civbro_backend"
FRONTEND_DIST = EXTENSION_DIR / "frontend" / "dist"


def on_app_started(demo: gr.Blocks, app):
    for path in (BACKEND_SRC, BACKEND_PKG_DIR):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    try:
        from civbro_backend.main import register_routes

        # Reuse Gradio's own login dependency instead of inventing a second
        # cookie format. Otherwise extension API routes bypass --gradio-auth.
        login_check = next((r.endpoint for r in app.routes if getattr(r, "path", "") == "/login_check/"), None)
        protected = getattr(app, "auth", None) is not None or getattr(app, "auth_dependency", None) is not None
        if protected and login_check is None:
            raise RuntimeError("This host enables authentication but exposes no compatible login-check dependency")
        router = APIRouter(dependencies=[Depends(login_check)] if login_check else [])
        register_routes(router)
        static = StaticFiles(directory=str(FRONTEND_DIST), html=True)

        @router.get("/civbro/{path:path}", include_in_schema=False)
        async def frontend(path: str, request: Request):
            return await static.get_response(path, request.scope)

        app.include_router(router)
        print("[CivBro] API and frontend registered with the WebUI authentication policy")
    except Exception:
        print("[CivBro] Extension startup failed; check installation prerequisites and the error below")
        traceback.print_exc()


def on_ui_tabs():
    with gr.Blocks() as block:
        # Scripts embedded in gr.HTML do not execute reliably. The WebUI loads
        # javascript/civbro.js through its native extension lifecycle instead.
        # 150px = measured Forge chrome above the tab panel (~130px) plus
        # panel padding, so the iframe bottom sits just inside the viewport
        # instead of clipping below it and leaving a scrollable dead zone.
        gr.HTML('''<iframe id="civbro-iframe" title="CivBro model browser"
            style="width:100%;height:calc(100vh - 150px);border:0"></iframe>''')
    return [(block, "CivBro", "civbro_tab")]


try:
    from modules import script_callbacks
except ImportError:
    print("[CivBro] Requires an A1111-compatible WebUI with modules.script_callbacks; ComfyUI is not supported")
else:
    script_callbacks.on_app_started(on_app_started)
    script_callbacks.on_ui_tabs(on_ui_tabs)
