from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx
from fastapi import HTTPException

from .client import get_civitai_key, get_http_client, http_get_with_retry
from .config import (
    CIVITAI_RED_API,
    CIVITAI_REST_API,
    CIVITAI_TRPC_API,
    DEFAULT_CIVITAI_NSFW,
    DEFAULT_LIMIT,
    EXCLUDED_TAG_IDS,
)
from .rust_facade import parse_model_slim, parse_trpc_model, parse_trpc_items
from .trpc_extras import _trpc_client_headers

logger = logging.getLogger("civbro.api")


async def fetch_from_trpc(
    query: str = "",
    model_type: str | list[str] | None = None,
    base_model: str | None = None,
    tag: str | None = None,
    nsfw: str = DEFAULT_CIVITAI_NSFW,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
    sort: str = "Newest",
    period: str = "AllTime",
    early_access: bool = False,
) -> dict:
    client = get_http_client()

    input_data: dict[str, Any] = {
        "json": {
            "browsingLevel": 127 if nsfw in ("true", "True", "Soft", "Mature", "X") else 1,
            "sort": sort,
            "period": period or "AllTime",
            "periodMode": "published",
            "pending": False,
            "disablePoi": True,
            "disableMinor": None,
            "excludedTagIds": EXCLUDED_TAG_IDS,
            "direction": "forward",
            "limit": limit,
        },
        "meta": {"values": {"disableMinor": ["undefined"]}, "v": 1},
    }
    json_data = input_data["json"]
    if query:
        json_data["query"] = query
    if model_type:
        json_data["types"] = model_type if isinstance(model_type, list) else [model_type]
    if base_model:
        json_data["baseModels"] = [base_model]
    if tag:
        json_data["tag"] = tag
    if cursor is not None:
        json_data["cursor"] = cursor
    if early_access:
        json_data["earlyAccess"] = True

    input_json = json.dumps(input_data, separators=(",", ":"))

    t0 = time.time()
    try:
        resp = await http_get_with_retry(
            f"{CIVITAI_TRPC_API}/model.getAll",
            params={"input": input_json},
            headers=_trpc_client_headers(),
        )
        t1 = time.time()
        logger.debug(f"tRPC request took {t1 - t0:.2f}s")

        data = resp.json()

        items_raw = parse_trpc_items(data)
        next_cursor = None
        if isinstance(data, dict):
            inner = (data.get("result") or {})
            if isinstance(inner, dict):
                d = inner.get("data") or {}
                if isinstance(d, dict):
                    j = d.get("json") or {}
                    if isinstance(j, dict):
                        c = j.get("nextCursor")
                        next_cursor = str(c) if c is not None else None

        items = [parse_trpc_model(item) for item in items_raw]

        return {
            "items": items,
            "nextCursor": next_cursor,
            "source": "trpc",
        }
    except Exception as e:
        logger.warning(f"tRPC request failed: {e}")
        raise


async def fetch_from_rest(
    query: str = "",
    model_type: str | list[str] | None = None,
    base_model: str | None = None,
    tag: str | None = None,
    nsfw: str = DEFAULT_CIVITAI_NSFW,
    sort: str = "Newest",
    period: str = "AllTime",
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
    early_access: bool = False,
) -> dict:
    client = get_http_client()

    params: dict[str, Any] = {
        "limit": limit,
        "nsfw": "true" if nsfw in ("true", "True", "Soft", "Mature", "X") else "false",
    }
    if query:
        params["query"] = query
    if tag:
        params["tag"] = tag
    if model_type:
        params["types"] = model_type
    if base_model:
        params["baseModels"] = base_model
    if sort and sort != "Newest":
        params["sort"] = sort
    if period and period != "AllTime":
        params["period"] = period
    if cursor:
        params["cursor"] = cursor
    if early_access:
        params["earlyAccess"] = "true"

    t0 = time.time()
    resp = await http_get_with_retry(f"{CIVITAI_REST_API}/models", params=params)
    t1 = time.time()
    logger.debug(f"REST request took {t1 - t0:.2f}s")

    data = resp.json()
    items_raw = data.get("items", [])
    metadata = data.get("metadata", {})

    items = [parse_model_slim(item) for item in items_raw]

    next_cursor = metadata.get("nextCursor")

    return {
        "items": items,
        "nextCursor": next_cursor,
        "source": "rest",
    }


async def fetch_from_red(
    query: str = "",
    model_type: str | list[str] | None = None,
    base_model: str | None = None,
    tag: str | None = None,
    nsfw: str = DEFAULT_CIVITAI_NSFW,
    sort: str = "Newest",
    period: str = "AllTime",
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> dict:
    api_key = get_civitai_key()
    if not api_key:
        raise HTTPException(status_code=401, detail="civitai.red API key not configured")

    client = get_http_client()

    params: dict[str, Any] = {
        "limit": limit,
        "nsfw": "true" if nsfw in ("true", "True", "Soft", "Mature", "X") else "false",
        "token": api_key,
    }
    if query:
        params["query"] = query
    if tag:
        params["tag"] = tag
    if model_type:
        params["types"] = model_type
    if base_model:
        params["baseModels"] = base_model
    if sort and sort != "Newest":
        params["sort"] = sort
    if period and period != "AllTime":
        params["period"] = period
    if cursor:
        params["cursor"] = cursor

    t0 = time.time()
    resp = await http_get_with_retry(f"{CIVITAI_RED_API}/models", params=params)
    t1 = time.time()
    logger.debug(f"civitai.red request took {t1 - t0:.2f}s")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"civitai.red returned {resp.status_code}: {resp.text[:200]}",
        )

    data = resp.json()
    items_raw = data.get("items", [])
    metadata = data.get("metadata", {})

    items = [parse_model_slim(item) for item in items_raw]

    next_cursor = metadata.get("nextCursor")

    return {
        "items": items,
        "nextCursor": next_cursor,
        "source": "red",
    }
