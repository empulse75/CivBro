from __future__ import annotations

import json
import logging
import time
from typing import Any

from .client import DB, http_get_with_retry
from .config import CIVITAI_TRPC_API, CIVITAI_REST_API, COSMETIC_CACHE_TTL, EXCLUDED_TAG_IDS, EXTRAS_ID_TTL
from .rust_facade import apply_extras_to_slim, extract_trpc_extras, make_slim_from_trpc, parse_dependencies, parse_trpc_items

logger = logging.getLogger("civbro.api")

_COSMETIC_CACHE: dict[str, tuple[float, dict]] = {}
_EXTRAS_ID_CACHE: dict[int, tuple[float, dict]] = {}


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
    try:
        cursor = None
        for _ in range(20):
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
            items = parse_trpc_items(resp.json())
            if not items:
                break
            for it in items:
                mid = it.get("id")
                if mid is None:
                    continue
                extras = extract_trpc_extras(it)
                if extras:
                    out[str(mid)] = extras
            try:
                raw = json.loads(((resp.json().get("result") or {}).get("data") or ""))
                if isinstance(raw, list) and raw:
                    meta = raw[0] if isinstance(raw[0], dict) else {}
                    nxt = meta.get("nextCursor")
                    cursor = nxt if nxt and nxt != -1 else None
                else:
                    cursor = None
            except Exception:
                cursor = None
            if cursor is None:
                break
    except Exception as e:
        logger.debug(f"trpc extras fetch failed: {e}")

    _COSMETIC_CACHE[key] = (time.time(), out)
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
                    _EXTRAS_ID_CACHE[mid] = (now, extras)
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
