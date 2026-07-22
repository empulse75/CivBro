from __future__ import annotations

import logging

from .config import CACHE_DIR

logger = logging.getLogger("civbro.api")

CACHE_DIR.mkdir(parents=True, exist_ok=True)


from .routes import register_routes
