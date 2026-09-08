from __future__ import annotations

import logging
from typing import Any

from .client import RUST_AVAILABLE
from .http_adapter import get_raw_http_client
from . import downloads

logger = logging.getLogger("civbro.api")


async def _shutdown():
    http_client = get_raw_http_client()
    if http_client is not None:
        await http_client.aclose()


def register_routes(app: Any) -> None:
    from .client import cleanup_orphan_parts
    from .downloads import recover_stale_downloads
    from .routes_models import register_model_routes
    from .routes_downloads import register_download_routes
    from .routes_local import register_local_routes
    from .routes_settings import register_settings_routes

    # FastAPI 0.141 removed app.add_event_handler; APIRouter retains the API.
    lifecycle = getattr(app, "router", app)
    lifecycle.add_event_handler("shutdown", _shutdown)

    logger.info("[CivBro] Registering routes under /civbro/api")

    recovery_count = recover_stale_downloads()
    cleanup_orphan_parts()

    async def _startup_downloads():
        if recovery_count > 0:
            await downloads.schedule_downloads()

    lifecycle.add_event_handler("startup", _startup_downloads)

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
