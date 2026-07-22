from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Query

from .cache import search_cache_get, search_cache_key, search_cache_put
from .civitai_api import fetch_from_red, fetch_from_rest, fetch_from_trpc
from .client import DB, ensure_warmup_started, get_civitai_key, get_http_client
from .config import (
    CIVITAI_REST_API,
    DEFAULT_CIVITAI_NSFW,
    DEFAULT_LIMIT,
    MODELS_ROOT,
)
from .parsing import parse_rest_model
from .trpc_extras import (
    apply_extras_to_slim,
    fetch_extras_by_ids,
    fetch_trpc_extras,
    fetch_trpc_version_detail,
    make_slim_from_trpc,
    parse_dependencies,
)
from .utils import optimize_image_url, subdir_for_type

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
                    except Exception:
                        pass

                search_cache_put(cache_key, result)
                return result
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
                )
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
        id: list[int] | None = Query(default=None),
        query: str = Query(default=""),
        modelType: list[str] | None = Query(default=None, alias="type"),
        sort: str = Query(default="Newest"),
        period: str = Query(default="AllTime"),
        nsfw: bool = Query(default=False),
    ):
        ensure_warmup_started()
        if id:
            return {"extras": await fetch_extras_by_ids(id)}
        mt = modelType[0] if isinstance(modelType, list) and modelType else modelType
        extras = await fetch_trpc_extras(sort, period, mt, query, nsfw=bool(nsfw))
        return {"extras": extras}

    @app.get(f"{PREFIX}/models/{{civitai_id}}")
    async def get_model(civitai_id: int):
        client = get_http_client()
        try:
            resp = await client.get(f"{CIVITAI_REST_API}/models/{civitai_id}")
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
        client = get_http_client()
        try:
            resp = await client.get(f"{CIVITAI_REST_API}/models/{civitai_id}")
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Model not found")
            resp.raise_for_status()
            data = resp.json()

            versions = []
            for mv in data.get("modelVersions", []):
                version_images = []
                for img in mv.get("images", []):
                    img_url = img.get("url", "")
                    img["url"] = optimize_image_url(img_url, 450, img.get("type", "image"))
                    version_images.append(img)

                versions.append({
                    "id": mv.get("id"),
                    "name": mv.get("name"),
                    "baseModel": mv.get("baseModel"),
                    "trainedWords": mv.get("trainedWords", []),
                    "images": version_images,
                    "downloadUrl": mv.get("downloadUrl", ""),
                    "files": [
                        {
                            "id": f.get("id"),
                            "name": f.get("name"),
                            "sizeKB": f.get("sizeKB", 0),
                            "type": f.get("type", ""),
                            "primary": f.get("primary", False),
                            "format": f.get("metadata", {}).get("format", ""),
                            "fp": f.get("metadata", {}).get("fp", ""),
                            "sizeType": f.get("metadata", {}).get("size", ""),
                            "hashes": f.get("hashes", {}),
                            "downloadUrl": f.get("downloadUrl", ""),
                            "scannedAt": f.get("scannedAt"),
                            "pickleScanResult": f.get("pickleScanResult"),
                            "virusScanResult": f.get("virusScanResult"),
                        }
                        for f in mv.get("files", [])
                    ],
                    "createdAt": mv.get("createdAt"),
                    "availability": mv.get("availability") or "Public",
                    "buzzCost": mv.get("buzz"),
                    "stats": mv.get("stats", {}),
                    "description": mv.get("description", ""),
                    "earlyAccessEndsAt": mv.get("earlyAccessEndsAt")
                    or (mv.get("earlyAccessConfig") or {}).get("timeframe"),
                })

            return {"modelId": civitai_id, "versions": versions}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"Failed to fetch model versions: {str(e)}"
            )

    @app.get(f"{PREFIX}/versions/{{version_id}}")
    async def get_version(version_id: int):
        import asyncio
        from datetime import datetime, timezone

        client = get_http_client()
        try:
            rest_resp, trpc = await asyncio.gather(
                client.get(f"{CIVITAI_REST_API}/model-versions/{version_id}"),
                fetch_trpc_version_detail(version_id, get_civitai_key()),
            )
            resp = rest_resp
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Version not found")
            resp.raise_for_status()
            data = resp.json()

            images = []
            for img in data.get("images", []):
                img_url = img.get("url", "")
                img["url"] = optimize_image_url(img_url, 450, img.get("type", "image"))
                images.append(img)

            dependencies = parse_dependencies(trpc)

            model_obj = (
                (data.get("model") or {})
                if isinstance(data.get("model"), dict)
                else {}
            )
            creator_obj = (
                model_obj.get("creator")
                if isinstance(model_obj.get("creator"), dict)
                else {}
            )
            availability = data.get("availability") or "Public"
            if availability == "Public":
                ea_ends = data.get("earlyAccessEndsAt")
                if ea_ends:
                    try:
                        t = datetime.fromisoformat(ea_ends.replace("Z", "+00:00"))
                        if t > datetime.now(timezone.utc):
                            availability = "EarlyAccess"
                    except Exception:
                        pass
            early_access_ends = (
                data.get("earlyAccessEndsAt")
                or (data.get("earlyAccessConfig") or {}).get("timeframe")
            )
            buzz_cost = data.get("buzz") or data.get("buzzCost") or 0

            return {
                "id": data.get("id"),
                "modelId": data.get("modelId"),
                "name": data.get("name"),
                "baseModel": data.get("baseModel"),
                "trainedWords": data.get("trainedWords", []),
                "images": images,
                "downloadUrl": data.get("downloadUrl", ""),
                "dependencies": dependencies,
                "air": trpc.get("air", ""),
                "clipSkip": trpc.get("clipSkip"),
                "epochs": trpc.get("epochs"),
                "steps": trpc.get("steps"),
                "tensorType": trpc.get("tensorType") or model_obj.get("tensorType"),
                "modelSize": trpc.get("modelSize") or model_obj.get("modelSize"),
                "availability": availability,
                "earlyAccessEndsAt": early_access_ends,
                "buzzCost": int(buzz_cost) if buzz_cost else 0,
                "allowCommercialUse": model_obj.get("allowCommercialUse"),
                "allowDerivatives": model_obj.get("allowDerivatives"),
                "allowNoCredit": model_obj.get("allowNoCredit"),
                "allowDifferentLicense": model_obj.get("allowDifferentLicense"),
                "baseModels": model_obj.get("baseModels") or [],
                "creator": {
                    "username": creator_obj.get("username", ""),
                    "image": creator_obj.get("image", ""),
                    "createdAt": creator_obj.get("createdAt"),
                },
                "updatedAt": data.get("updatedAt"),
                "files": [
                    {
                        "id": f.get("id"),
                        "name": f.get("name"),
                        "sizeKB": f.get("sizeKB", 0),
                        "type": f.get("type", ""),
                        "primary": f.get("primary", False),
                        "format": f.get("metadata", {}).get("format", ""),
                        "fp": f.get("metadata", {}).get("fp", ""),
                        "sizeType": f.get("metadata", {}).get("size", ""),
                        "hashes": f.get("hashes", {}),
                        "downloadUrl": f.get("downloadUrl", ""),
                        "scannedAt": f.get("scannedAt"),
                        "pickleScanResult": f.get("pickleScanResult"),
                        "virusScanResult": f.get("virusScanResult"),
                    }
                    for f in data.get("files", [])
                ],
                "createdAt": data.get("createdAt"),
                "stats": data.get("stats", {}),
                "description": data.get("description", ""),
                "model": parse_rest_model(data.get("model", {})),
            }
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
        client = get_http_client()
        try:
            params: dict[str, Any] = {"limit": limit}
            if query:
                params["query"] = query
            resp = await client.get(f"{CIVITAI_REST_API}/tags", params=params)
            resp.raise_for_status()
            return {"items": resp.json().get("items", [])}
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"Failed to fetch tags: {str(e)}"
            )

    @app.get(f"{PREFIX}/search/suggestions")
    async def search_suggestions(query: str = Query(default="")):
        client = get_http_client()
        try:
            resp = await client.get(
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

    @app.get(f"{PREFIX}/config")
    async def get_frontend_config():
        from .config import DIR_MAP, FRONTEND_DIR_MAP, MODELS_ROOT

        return {
            "modelsRoot": MODELS_ROOT,
            "dirMap": DIR_MAP,
            "frontendDirMap": FRONTEND_DIR_MAP,
        }
