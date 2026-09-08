from __future__ import annotations

import json
import logging
import time
from typing import Any

from .client import DB, http_get_with_retry
from .config import (
    CIVITAI_TRPC_API,
    CIVITAI_REST_API,
    COSMETIC_CACHE_MAX,
    COSMETIC_CACHE_TTL,
    EXCLUDED_TAG_IDS,
    EXTRAS_ID_CACHE_MAX,
    EXTRAS_ID_TTL,
    TRPC_EXTRAS_MAX_PAGES,
)
from .rust_facade import apply_extras_to_slim, extract_trpc_extras, make_slim_from_trpc, parse_dependencies, parse_trpc_items

logger = logging.getLogger("civbro.api")

_COSMETIC_CACHE: dict[str, tuple[float, dict]] = {}
_EXTRAS_ID_CACHE: dict[int, tuple[float, dict]] = {}


def _cache_put(cache: dict, key: Any, value: tuple[float, dict], limit: int) -> None:
    """Insert with oldest-first eviction once the cache is full."""
    if key not in cache and len(cache) >= limit:
        oldest = min(cache.items(), key=lambda kv: kv[1][0])[0]
        cache.pop(oldest, None)
    cache[key] = value


def _trpc_client_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "x-client": "web",
        "x-client-version": "5.0.2014",
        "x-client-date": str(int(time.time() * 1000)),
        "Referer": "https://civitai.com/models",
    }


def _next_cursor(payload: Any) -> Any:
    """Pull nextCursor out of a tRPC model.getAll envelope.

    Shape is result.data.json.nextCursor — the same path fetch_from_trpc reads.
    A cursor of -1 means "no more pages".
    """
    if not isinstance(payload, dict):
        return None
    data = (payload.get("result") or {}).get("data")
    if not isinstance(data, dict):
        return None
    inner = data.get("json")
    if not isinstance(inner, dict):
        return None
    nxt = inner.get("nextCursor")
    return nxt if nxt not in (None, "", -1) else None


async def fetch_trpc_extras(
    sort: str, period: str, model_type: Any, query: str, nsfw: bool = False
) -> dict:
    key = json.dumps([sort, period, model_type, query, nsfw], sort_keys=True, default=str)
    hit = _COSMETIC_CACHE.get(key)
    if hit and time.time() - hit[0] < COSMETIC_CACHE_TTL:
        return hit[1]

    inp: dict[str, Any] = {
        "json": {
            "browsingLevel": 127 if nsfw else 1,
            "sort": sort or "Most Downloaded",
            "period": period or "AllTime",
            "periodMode": "published",
            "pending": False,
            "disablePoi": True,
            "disableMinor": None,
            "excludedTagIds": EXCLUDED_TAG_IDS,
            "direction": "forward",
            "limit": 100,
        },
        "meta": {"values": {"disableMinor": ["undefined"]}, "v": 1},
    }
    if model_type:
        inp["json"]["types"] = [model_type] if isinstance(model_type, str) else list(model_type)
    if query:
        inp["json"]["query"] = query

    headers = _trpc_client_headers()
    if DB is not None:
        try:
            api_key = DB.get_setting("civitaiRedApiKey") or ""
            if api_key:
                headers["Authorization"] = "Bearer " + api_key
        except Exception:
            pass

    out: dict = {}
    complete = False
    try:
        cursor = None
        for _ in range(TRPC_EXTRAS_MAX_PAGES):
            req_inp = {k: dict(v) if isinstance(v, dict) else v for k, v in inp.items()}
            if cursor is not None:
                req_inp["json"]["cursor"] = cursor
            resp = await http_get_with_retry(
                f"{CIVITAI_TRPC_API}/model.getAll",
                params={"input": json.dumps(req_inp, separators=(",", ":"))},
                headers=headers,
                timeout=15.0,
            )
            if resp.status_code != 200:
                break
            payload = resp.json()
            items = parse_trpc_items(payload)
            if not items:
                complete = True
                break
            for it in items:
                mid = it.get("id")
                if mid is None:
                    continue
                extras = extract_trpc_extras(it)
                if extras:
                    out[str(mid)] = extras
            cursor = _next_cursor(payload)
            if cursor is None:
                complete = True
                break
        else:
            # Page budget exhausted: partial by policy, not by failure.
            complete = True
    except Exception as e:
        logger.debug(f"trpc extras fetch failed: {e}")

    # Only cache a result we actually finished collecting. Caching a partial or
    # failed sweep would pin those models as "no cosmetics" for the whole TTL.
    if complete:
        _cache_put(_COSMETIC_CACHE, key, (time.time(), out), COSMETIC_CACHE_MAX)
    return out


async def fetch_extras_by_ids(ids: list[int]) -> dict:
    now = time.time()
    out: dict = {}
    misses: list[int] = []
    for i in ids:
        hit = _EXTRAS_ID_CACHE.get(i)
        if hit and now - hit[0] < EXTRAS_ID_TTL:
            if hit[1]:
                out[str(i)] = hit[1]
        else:
            misses.append(i)
    if not misses:
        return out

    headers = _trpc_client_headers()

    for b_idx in range(0, len(misses), 10):
        chunk = misses[b_idx : b_idx + 10]
        endpoint_str = ",".join(["model.getById"] * len(chunk))
        url = f"{CIVITAI_TRPC_API}/{endpoint_str}"
        inp = {
            str(idx): {"json": {"id": mid, "browsingLevel": 127}}
            for idx, mid in enumerate(chunk)
        }
        try:
            resp = await http_get_with_retry(
                url,
                params={"batch": "1", "input": json.dumps(inp, separators=(",", ":"))},
                headers=headers,
                timeout=15.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                if not isinstance(data, list):
                    data = [data]
                for item in data:
                    res = item.get("result", {}).get("data", {})
                    json_data = res.get("json") if isinstance(res, dict) else {}
                    if not isinstance(json_data, dict):
                        continue
                    mid = json_data.get("id")
                    if not mid:
                        continue
                    extras = extract_trpc_extras(json_data)
                    _cache_put(
                        _EXTRAS_ID_CACHE, mid, (now, extras), EXTRAS_ID_CACHE_MAX
                    )
                    if extras:
                        out[str(mid)] = extras
            else:
                logger.debug(f"batch tRPC extras returned HTTP {resp.status_code}")
        except Exception as e:
            logger.debug(f"batch tRPC extras fetch failed: {e}")

    return out


async def fetch_trpc_version_detail(version_id: int, api_key: str = "") -> dict:
    params: dict[str, Any] = {"input": json.dumps({"json": {"id": version_id}})}
    if api_key:
        params["token"] = api_key
    try:
        resp = await http_get_with_retry(
            f"{CIVITAI_TRPC_API}/modelVersion.getById",
            params=params,
            timeout=20.0,
        )
        if resp.status_code == 200:
            return (
                ((resp.json().get("result", {}) or {}).get("data", {}) or {})
                .get("json", {})
                or {}
            )
        logger.debug(f"tRPC version {version_id} returned HTTP {resp.status_code}")
    except Exception as e:
        logger.debug(f"tRPC version detail failed for {version_id}: {e}")
    return {}
