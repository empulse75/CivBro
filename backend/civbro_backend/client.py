from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from .config import CIVITAI_REST_API, CIVITAI_RED_API, DB_PATH, WARMUP_INTERVAL

logger = logging.getLogger("civbro.api")

HTTP_CLIENT: httpx.AsyncClient | None = None
RUST_AVAILABLE = False
DB = None


def _resolve_db_path(candidates: list[Path] | None = None) -> str:
    if candidates is None:
        env_path = os.environ.get("CIVBRO_DB_PATH")
        if env_path:
            return env_path
        candidates = [DB_PATH]
    target = candidates[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    return str(target)


try:
    import civbro_core

    RUST_AVAILABLE = True
    DB = civbro_core.Database(_resolve_db_path())
    logger.info("[CivBro] Rust core loaded successfully")
except ImportError:
    logger.warning("[CivBro] Rust core not available, using pure Python fallbacks")
    RUST_AVAILABLE = False

_WARMUP_STARTED = False


_CLIENT_KWARGS = dict(
    timeout=httpx.Timeout(connect=8.0, read=45.0, write=15.0, pool=45.0),
    limits=httpx.Limits(
        max_connections=40,
        max_keepalive_connections=20,
        keepalive_expiry=60.0,
    ),
    headers={
        "User-Agent": "CivBro/1.0",
        "Accept": "application/json",
    },
)

_H2_AVAILABLE = None


def _h2_available() -> bool:
    global _H2_AVAILABLE
    if _H2_AVAILABLE is None:
        try:
            import h2
            _H2_AVAILABLE = True
        except ImportError:
            _H2_AVAILABLE = False
    return _H2_AVAILABLE


def get_http_client() -> httpx.AsyncClient:
    global HTTP_CLIENT
    if HTTP_CLIENT is None:
        if _h2_available():
            HTTP_CLIENT = httpx.AsyncClient(http2=True, **_CLIENT_KWARGS)
        else:
            logger.warning("[CivBro] h2 not installed — using HTTP/1.1")
            HTTP_CLIENT = httpx.AsyncClient(**_CLIENT_KWARGS)
    return HTTP_CLIENT


def _make_h2_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(http2=True, **_CLIENT_KWARGS)


async def http_get_with_retry(url: str, **kw: Any) -> httpx.Response:
    client = get_http_client()
    try:
        return await client.get(url, **kw)
    except (httpx.RemoteProtocolError, httpx.ConnectError) as e:
        msg = str(e)
        if "ConnectionTerminated" in msg or "RemoteProtocolError" in msg:
            logger.debug(f"retrying with fresh HTTP/2 connection: {msg}")
            try:
                async with _make_h2_client() as c2:
                    return await c2.get(url, **kw)
            except (httpx.RemoteProtocolError, httpx.ConnectError) as e2:
                msg2 = str(e2)
                if "ConnectionTerminated" in msg2 or "RemoteProtocolError" in msg2:
                    logger.debug(f"HTTP/2 retry failed, falling back to HTTP/1.1: {msg2}")
                    async with httpx.AsyncClient(**_CLIENT_KWARGS) as c1:
                        return await c1.get(url, **kw)
                raise
        raise


async def _warm_connections() -> None:
    client = get_http_client()

    async def _ping(url: str, params: dict) -> None:
        try:
            await http_get_with_retry(
                url,
                params=params,
                timeout=httpx.Timeout(connect=8.0, read=20.0, write=10.0, pool=20.0),
            )
        except Exception:
            pass

    targets: list[tuple[str, dict]] = [
        (f"{CIVITAI_REST_API}/models", {"limit": 1}),
    ]
    api_key = ""
    if DB is not None:
        try:
            api_key = DB.get_setting("civitaiRedApiKey") or ""
        except Exception:
            api_key = ""
    if api_key:
        targets.append((f"{CIVITAI_RED_API}/models", {"limit": 1, "token": api_key}))

    await asyncio.gather(*(_ping(u, p) for u, p in targets))


async def _warmup_loop() -> None:
    while True:
        await _warm_connections()
        await asyncio.sleep(WARMUP_INTERVAL)


def ensure_warmup_started() -> None:
    global _WARMUP_STARTED
    if _WARMUP_STARTED:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _WARMUP_STARTED = True
    loop.create_task(_warmup_loop())
    logger.info("[CivBro] connection warm-up loop started")


def get_civitai_key() -> str:
    if DB is not None:
        try:
            return DB.get_setting("civitaiRedApiKey") or ""
        except Exception:
            return ""
    return ""


def cleanup_orphan_parts() -> int:
    from pathlib import Path

    from .config import MODELS_ROOT

    removed = 0
    if not RUST_AVAILABLE or not hasattr(civbro_core, "clean_orphan_parts"):
        return 0
    try:
        removed = civbro_core.clean_orphan_parts(MODELS_ROOT)
    except Exception as e:
        logger.debug(f"orphan .part cleanup failed: {e}", exc_info=True)
    if removed:
        logger.info(f"[CivBro] cleaned {removed} orphan .part file(s)")
    return removed
