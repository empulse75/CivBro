from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .config import CIVITAI_REST_API, CIVITAI_RED_API, WARMUP_INTERVAL

logger = logging.getLogger("civbro.api")

_HTTP_CLIENT: httpx.AsyncClient | None = None

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
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        if _h2_available():
            _HTTP_CLIENT = httpx.AsyncClient(http2=True, **_CLIENT_KWARGS)
        else:
            logger.warning("[CivBro] h2 not installed — using HTTP/1.1")
            _HTTP_CLIENT = httpx.AsyncClient(**_CLIENT_KWARGS)
    return _HTTP_CLIENT


def get_raw_http_client() -> httpx.AsyncClient | None:
    return _HTTP_CLIENT


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
