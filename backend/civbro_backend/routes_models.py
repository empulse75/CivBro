from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Query

from .cache import search_cache_get, search_cache_key, search_cache_put
from .civitai_api import fetch_from_red, fetch_from_rest, fetch_from_trpc
from .client import DB, RUST_AVAILABLE, ensure_warmup_started, get_civitai_key, http_get_with_retry
from .config import (
    CIVITAI_RED_API,
    CIVITAI_REST_API,
    CIVITAI_TRPC_API,
    DEFAULT_CIVITAI_NSFW,
    DEFAULT_LIMIT,
)
from .rust_facade import parse_rest_model, subdir_for_type
from .trpc_extras import (
    _trpc_client_headers,
    apply_extras_to_slim,
    fetch_extras_by_ids,
    fetch_trpc_extras,
    fetch_trpc_version_detail,
    make_slim_from_trpc,
)


logger = logging.getLogger("civbro.api")

PREFIX = "/civbro/api"


def register_model_routes(app: Any) -> None:
    @app.get(f"{PREFIX}/models")
    async def search_models(
        query: str = Query(default="", description="Search query"),
        modelType: list[str] | None = Query(default=None, alias="type"),
        baseModel: list[str] | None = Query(default=None, alias="baseModel"),
        tag: str | None = Query(default=None),
        nsfw: str = Query(default=DEFAULT_CIVITAI_NSFW),
        sort: str = Query(default="Newest"),
        period: str = Query(default="AllTime"),
        limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=100),
        cursor: str | None = Query(default=None),
        source: str = Query(
            default="trpc", description="API source: trpc, rest, red, or auto"
        ),
    ):
        ensure_warmup_started()

        cache_key = search_cache_key(
            source=source,
            query=query,
            modelType=modelType,
            baseModel=baseModel,
            tag=tag,
            nsfw=nsfw,
            sort=sort,
            period=period,
            limit=limit,
            cursor=cursor,
        )
        cached = search_cache_get(cache_key)
        if cached is not None:
            return cached

        if source == "red":
            try:
                result = await fetch_from_red(
                    query=query,
                    model_type=modelType,
                    base_model=baseModel,
                    tag=tag,
                    nsfw=nsfw,
                    sort=sort,
                    period=period,
                    limit=limit,
                    cursor=cursor,
                )
                api_key = get_civitai_key()
                if api_key:
                    try:
                        trpc_extras = await fetch_trpc_extras(
                            sort, period, modelType, query, nsfw=False
                        )
                        red_ids = {str(m.get("id")) for m in result.get("items", [])}
                        ea_models = []
                        for mid, ex in trpc_extras.items():
                            if mid in red_ids:
                                for m in result["items"]:
                                    if str(m.get("id")) == mid:
                                        apply_extras_to_slim(m, ex)
                                        break
                            elif ex.get("availability") == "EarlyAccess":
                                ea_models.append(make_slim_from_trpc(ex, int(mid)))
                        if ea_models:
                            result["items"] = ea_models + result["items"]
                    except Exception as e:
                        logger.debug(f"[CivBro] tRPC extras enrichment failed: {e}")

                search_cache_put(cache_key, result)
                return result
            except HTTPException:
                raise  # preserve upstream status codes (e.g. 401 key missing)
            except Exception as e:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to fetch models from civitai.red: {str(e)}",
                )

        use_trpc = source in ("trpc", "auto")

        if use_trpc:
            try:
                result = await fetch_from_trpc(
                    query=query,
                    model_type=modelType,
                    base_model=baseModel,
                    tag=tag,
                    nsfw=nsfw,
                    limit=limit,
                    cursor=cursor,
                    sort=sort,
                    period=period,
                    early_access=earlyAccess,
                )
                if DB is not None:
                    try:
                        for item in result.get("items", []):
                            DB.upsert_model(json.dumps(item))
                    except Exception as e:
                        logger.debug(f"Cache upsert error: {e}")
                search_cache_put(cache_key, result)
                return result
            except Exception:
                if source == "trpc":
                    raise HTTPException(
                        status_code=502, detail="tRPC API request failed"
                    )

        try:
            result = await fetch_from_rest(
                query=query,
                model_type=modelType,
                base_model=baseModel,
                tag=tag,
                nsfw=nsfw,
                sort=sort,
                period=period,
                limit=limit,
                cursor=cursor,
            )
            search_cache_put(cache_key, result)
            return result
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch models from Civitai: {str(e)}",
            )

    @app.get(f"{PREFIX}/models/extras")
    async def model_extras(
        model_ids: list[int] | None = Query(default=None, alias="id"),
        query: str = Query(default=""),
        modelType: list[str] | None = Query(default=None, alias="type"),
        sort: str = Query(default="Newest"),
        period: str = Query(default="AllTime"),
        nsfw: bool = Query(default=False),
    ):
        ensure_warmup_started()
        if model_ids:
            return {"extras": await fetch_extras_by_ids(model_ids)}
        mt = modelType[0] if isinstance(modelType, list) and modelType else modelType
        extras = await fetch_trpc_extras(sort, period, mt, query, nsfw=bool(nsfw))
        return {"extras": extras}

    @app.get(f"{PREFIX}/models/{{civitai_id}}")
    async def get_model(civitai_id: int):
        try:
            resp = await http_get_with_retry(f"{CIVITAI_REST_API}/models/{civitai_id}")
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Model not found")
            resp.raise_for_status()
            return parse_rest_model(resp.json())
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"Failed to fetch model: {str(e)}"
            )

    @app.get(f"{PREFIX}/models/{{civitai_id}}/versions")
    async def get_model_versions(civitai_id: int):
        try:
            resp = await http_get_with_retry(f"{CIVITAI_REST_API}/models/{civitai_id}")
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Model not found")
            resp.raise_for_status()
            data = resp.json()
            raw = json.dumps(data)
            if RUST_AVAILABLE:
                from .rust_facade import build_version_list
                return build_version_list(raw)
            raise HTTPException(status_code=500, detail="Rust core not available")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"Failed to fetch model versions: {str(e)}"
            )

    @app.get(f"{PREFIX}/versions/{{version_id}}")
    async def get_version(version_id: int):
        import asyncio

        try:
            rest_resp, trpc = await asyncio.gather(
                http_get_with_retry(f"{CIVITAI_REST_API}/model-versions/{version_id}"),
                fetch_trpc_version_detail(version_id, get_civitai_key()),
            )
            if rest_resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Version not found")
            rest_resp.raise_for_status()
            data = rest_resp.json()
            if RUST_AVAILABLE:
                from .rust_facade import build_version_detail
                return build_version_detail(json.dumps(data), json.dumps(trpc))
            raise HTTPException(status_code=500, detail="Rust core not available")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"Failed to fetch version: {str(e)}"
            )

    @app.get(f"{PREFIX}/tags")
    async def search_tags(
        query: str = Query(default=""), limit: int = Query(default=20, ge=1, le=100)
    ):
        try:
            params: dict[str, Any] = {"limit": limit}
            if query:
                params["query"] = query
            resp = await http_get_with_retry(f"{CIVITAI_REST_API}/tags", params=params)
            resp.raise_for_status()
            return {"items": resp.json().get("items", [])}
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"Failed to fetch tags: {str(e)}"
            )

    @app.get(f"{PREFIX}/search/suggestions")
    async def search_suggestions(query: str = Query(default="")):
        try:
            resp = await http_get_with_retry(
                f"{CIVITAI_REST_API}/models",
                params={"query": query, "limit": 5},
            )
            resp.raise_for_status()
            data = resp.json()
            suggestions = [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "modelType": item.get("type"),
                    "nsfw": item.get("nsfw", False),
                }
                for item in data.get("items", [])
            ]
            return {"items": suggestions}
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"Failed to fetch suggestions: {str(e)}"
            )

    @app.get(f"{PREFIX}/models/{{civitai_id}}/comments")
    async def get_model_comments(civitai_id: int, cursor: str | None = Query(default=None)):
        try:
            inp_dict = {"json": {"modelId": civitai_id, "limit": 8, "sort": "newest", "direction": "forward"}}
            if cursor:
                inp_dict["json"]["cursor"] = cursor
            inp = json.dumps(inp_dict)
            resp = await http_get_with_retry(
                f"{CIVITAI_TRPC_API}/comment.getAll",
                params={"input": inp},
                headers=_trpc_client_headers(),
                timeout=10.0,
            )
            if resp.status_code != 200:
                return {"comments": [], "nextCursor": None}
            data = resp.json()
            result = data.get("result", {}).get("data", {}) if isinstance(data, dict) else {}
            json_data = result.get("json", {}) if isinstance(result, dict) else {}
            items = []
            comments_list = json_data.get("comments", []) if isinstance(json_data, dict) else []
            for j in comments_list:
                if isinstance(j, dict):
                    user = j.get("user", {})
                    items.append({
                        "id": j.get("id"),
                        "content": j.get("content", ""),
                        "createdAt": j.get("createdAt", ""),
                        "user": {"username": user.get("username", ""), "image": user.get("image", "")} if isinstance(user, dict) else None,
                    })
            return {"comments": items[:8], "nextCursor": json_data.get("nextCursor")}
        except Exception:
            return {"comments": [], "nextCursor": None}

    @app.get(f"{PREFIX}/models/{{civitai_id}}/suggested")
    async def get_suggested_resources(civitai_id: int):
        try:
            inp = json.dumps({"json": {"fromId": civitai_id, "type": "Suggested", "browsingLevel": 1}})
            resp = await http_get_with_retry(
                f"{CIVITAI_TRPC_API}/model.getAssociatedResourcesCardData",
                params={"input": inp},
                headers=_trpc_client_headers(),
                timeout=10.0,
            )
            if resp.status_code != 200:
                return {"items": []}
            data = resp.json()
            result = data.get("result", {}).get("data", {}) if isinstance(data, dict) else {}
            json_data = result.get("json", result) if isinstance(result, dict) else {}
            if isinstance(json_data, list):
                res_list = json_data
            else:
                res_list = json_data.get("items", []) if isinstance(json_data, dict) else []
            items = []
            for j in res_list:
                if isinstance(j, dict):
                    imgs = []
                    for raw_img in j.get("images", []) or []:
                        if isinstance(raw_img, dict):
                            img_url = raw_img.get("url", "")
                            if isinstance(img_url, dict):
                                img_url = img_url.get("url", "")
                            if img_url and isinstance(img_url, str) and not img_url.startswith("http"):
                                img_type = raw_img.get("type", "image")
                                vid = raw_img.get("modelVersionId") or j.get("modelVersionId", "")
                                if img_type == "video":
                                    img_url = f"https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/{img_url}/transcode=true,width=450,optimized=true/{vid}.mp4"
                                else:
                                    img_url = f"https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/{img_url}/width=450/{img_url}.jpeg"
                            imgs.append({"url": img_url, "type": raw_img.get("type", "image")})
                    items.append({
                        "id": j.get("id"),
                        "name": j.get("name", ""),
                        "type": j.get("type", ""),
                        "nsfw": j.get("nsfw", False),
                        "stats": j.get("stats", {}),
                        "images": imgs,
                    })
            return {"items": items[:8]}
        except Exception:
            return {"items": []}

    @app.get(f"{PREFIX}/config")
    async def get_frontend_config():
        from .config import DIR_MAP, FRONTEND_DIR_MAP, MODELS_ROOT

        return {
            "modelsRoot": MODELS_ROOT,
            "dirMap": DIR_MAP,
            "frontendDirMap": FRONTEND_DIR_MAP,
        }
