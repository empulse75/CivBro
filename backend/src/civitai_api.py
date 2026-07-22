from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx
from fastapi import HTTPException

from .client import DB, RUST_AVAILABLE, get_http_client, http_get_with_retry
from .config import (
    CIVITAI_RED_API,
    CIVITAI_REST_API,
    CIVITAI_TRPC_API,
    DEFAULT_CIVITAI_NSFW,
    DEFAULT_LIMIT,
)
from .parsing import parse_model_slim, parse_trpc_model
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
) -> dict:
    client = get_http_client()

    input_data: dict[str, Any] = {
        "limit": limit,
        "nsfw": nsfw,
    }
    if query:
        input_data["query"] = query
    if model_type:
        input_data["types"] = model_type if isinstance(model_type, list) else [model_type]
    if base_model:
        input_data["baseModels"] = [base_model]
    if tag:
        input_data["tag"] = tag
    if cursor is not None:
        try:
            input_data["cursor"] = int(cursor)
        except (ValueError, TypeError):
            input_data["cursor"] = cursor

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

        result_data = data
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "result" in item:
                    inner = item["result"]
                    if isinstance(inner, dict) and "data" in inner:
                        data_str = inner["data"]
                        if isinstance(data_str, str):
                            result_data = json.loads(data_str)
                        elif isinstance(data_str, dict):
                            result_data = data_str
                    break

        items_raw = []
        next_cursor = None
        if isinstance(result_data, dict):
            json_data = result_data.get("json")
            if isinstance(json_data, dict):
                items_raw = json_data.get("items", [])
                next_cursor_val = json_data.get("nextCursor")
                next_cursor = str(next_cursor_val) if next_cursor_val is not None else None
            elif isinstance(result_data.get("result"), dict):
                inner = result_data["result"]
                data_inner = inner.get("data", {})
                if isinstance(data_inner, str):
                    data_inner = json.loads(data_inner)
                json_data = data_inner.get("json", {})
                if isinstance(json_data, str):
                    json_data = json.loads(json_data)
                items_raw = json_data.get("items", [])
                next_cursor_val = json_data.get("nextCursor")
                next_cursor = str(next_cursor_val) if next_cursor_val is not None else None

        items = [parse_trpc_model(item) for item in items_raw]

        if DB is not None:
            try:
                for item in items:
                    DB.upsert_model(json.dumps(item))
            except Exception as e:
                logger.debug(f"Cache upsert error: {e}")

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
    api_key = ""
    if DB is not None:
        api_key = DB.get_setting("civitaiRedApiKey") or ""
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
