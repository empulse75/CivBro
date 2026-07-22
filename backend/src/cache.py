from __future__ import annotations

import json
import logging
import time
from typing import Any

from .config import COSMETIC_CACHE_TTL, EXTRAS_ID_TTL, SEARCH_CACHE_MAX, SEARCH_CACHE_TTL

logger = logging.getLogger("civbro.api")

_SEARCH_CACHE: dict[str, tuple[float, dict]] = {}


def search_cache_key(**kw: Any) -> str:
    return json.dumps(kw, sort_keys=True, default=str)


def search_cache_get(key: str) -> dict | None:
    hit = _SEARCH_CACHE.get(key)
    if not hit:
        return None
    ts, data = hit
    if time.time() - ts > SEARCH_CACHE_TTL:
        _SEARCH_CACHE.pop(key, None)
        return None
    items = data.get("items", [])
    if items and any(
        isinstance(it, dict) and not it.get("baseModels") for it in items[:10]
    ):
        _SEARCH_CACHE.pop(key, None)
        return None
    return data


def search_cache_put(key: str, data: dict) -> None:
    if not data or not data.get("items"):
        return
    if len(_SEARCH_CACHE) >= SEARCH_CACHE_MAX:
        oldest = min(_SEARCH_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _SEARCH_CACHE.pop(oldest, None)
    _SEARCH_CACHE[key] = (time.time(), data)


def clear_caches() -> None:
    from .trpc_extras import _COSMETIC_CACHE, _EXTRAS_ID_CACHE

    _SEARCH_CACHE.clear()
    _COSMETIC_CACHE.clear()
    _EXTRAS_ID_CACHE.clear()
