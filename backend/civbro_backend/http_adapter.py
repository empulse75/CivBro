from __future__ import annotations

import asyncio
import importlib.util
import logging
from typing import Any

import httpx

from .config import CIVITAI_REST_API, CIVITAI_RED_API, WARMUP_INTERVAL

logger = logging.getLogger("civbro.api")

_HTTP_CLIENT: httpx.AsyncClient | None = None

# httpx raises ImportError from AsyncClient(http2=True) when h2 is missing, and
# it raises at construction time — i.e. on the first request, surfacing as
# "Failed to fetch models from Civitai" for every call. h2 is in
# requirements.txt, but an install that aborted midway (Forge Neo's uv hook
# used to abort it) leaves the venv without it, so HTTP/2 is probed for as an
# accelerator instead of being a hard dependency.
_HTTP2 = importlib.util.find_spec("h2") is not None
if not _HTTP2:
    logger.warning(
        "[CivBro] the 'h2' package is missing, so Civitai traffic falls back to "
        "HTTP/1.1. Reinstall CivBro (Extensions -> Check for updates, then "
        "restart the WebUI) to restore HTTP/2 multiplexing."
    )

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

def http2_enabled() -> bool:
    """Whether Civitai traffic can use HTTP/2. Reported by /civbro/api/health."""
    return _HTTP2


def get_http_client() -> httpx.AsyncClient:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        _HTTP_CLIENT = httpx.AsyncClient(http2=_HTTP2, **_CLIENT_KWARGS)
    return _HTTP_CLIENT


def get_raw_http_client() -> httpx.AsyncClient | None:
    return _HTTP_CLIENT


def _make_fresh_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(http2=_HTTP2, **_CLIENT_KWARGS)


async def http_get_with_retry(url: str, **kw: Any) -> httpx.Response:
    client = get_http_client()
    try:
        return await client.get(url, **kw)
    except (httpx.RemoteProtocolError, httpx.ConnectError) as e:
        msg = str(e)
        if "ConnectionTerminated" in msg or "RemoteProtocolError" in msg:
            logger.debug(f"retrying on a fresh connection: {msg}")
            try:
                async with _make_fresh_client() as c2:
                    return await c2.get(url, **kw)
            except (httpx.RemoteProtocolError, httpx.ConnectError) as e2:
                msg2 = str(e2)
                if "ConnectionTerminated" in msg2 or "RemoteProtocolError" in msg2:
                    logger.debug(f"retry failed, forcing HTTP/1.1: {msg2}")
                    async with httpx.AsyncClient(**_CLIENT_KWARGS) as c1:
                        return await c1.get(url, **kw)
                raise
        raise


_WARMUP_STARTED = False


async def _warm_connections(get_api_key) -> None:
    targets: list[tuple[str, dict]] = [
        (f"{CIVITAI_REST_API}/models", {"limit": 1}),
    ]
    api_key = get_api_key()
    if api_key:
        targets.append((f"{CIVITAI_RED_API}/models", {"limit": 1, "token": api_key}))

    async def _ping(url: str, params: dict) -> None:
        try:
            await http_get_with_retry(
                url,
                params=params,
                timeout=httpx.Timeout(connect=8.0, read=20.0, write=10.0, pool=20.0),
            )
        except Exception as e:
            logger.debug(f"warmup ping failed: {e}")

    await asyncio.gather(*(_ping(u, p) for u, p in targets))


async def _warmup_loop(get_api_key) -> None:
    while True:
        try:
            await _warm_connections(get_api_key)
        except Exception as e:
            logger.warning(f"warmup loop iteration failed: {e}")
        await asyncio.sleep(WARMUP_INTERVAL)


def ensure_warmup_started(get_api_key) -> None:
    global _WARMUP_STARTED
    if _WARMUP_STARTED:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _WARMUP_STARTED = True
    loop.create_task(_warmup_loop(get_api_key))
    logger.info("[CivBro] connection warm-up loop started")
