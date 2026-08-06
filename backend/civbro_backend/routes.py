from __future__ import annotations

import logging
from typing import Any

from .client import RUST_AVAILABLE, DB, HTTP_CLIENT
from . import downloads

logger = logging.getLogger("civbro.api")


def _shutdown():
    if HTTP_CLIENT is not None:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.create_task(HTTP_CLIENT.aclose())
        else:
            import httpx
            try:
                asyncio.run(HTTP_CLIENT.aclose())
            except Exception as e:
                logger.warning(f"HTTP client shutdown failed: {e}")


def register_routes(app: Any) -> None:
    from .client import cleanup_orphan_parts, ensure_warmup_started
    from .downloads import recover_stale_downloads
    from .routes_models import register_model_routes
    from .routes_downloads import register_download_routes
    from .routes_local import register_local_routes
    from .routes_settings import register_settings_routes

    app.add_event_handler("shutdown", _shutdown)

    logger.info("[CivBro] Registering routes under /civbro/api")

    recovery_count = recover_stale_downloads()
    cleanup_orphan_parts()

    async def _startup_downloads():
        if recovery_count > 0:
            await downloads.schedule_downloads()

    app.add_event_handler("startup", _startup_downloads)

    PREFIX = "/civbro/api"

    @app.get(f"{PREFIX}/health")
    async def health():
        return {
            "status": "ok",
            "rust_available": RUST_AVAILABLE,
            "version": "1.0.0",
        }

    register_model_routes(app)
    register_download_routes(app)
    register_local_routes(app)
    register_settings_routes(app)

    logger.info("[CivBro] All routes registered")
