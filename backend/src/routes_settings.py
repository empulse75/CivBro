from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from fastapi import HTTPException, Request

from .client import DB, get_http_client
from .config import CIVITAI_RED_API
from .cache import clear_caches

logger = logging.getLogger("civbro.api")

PREFIX = "/civbro/api"


def register_settings_routes(app: Any) -> None:
    @app.get(f"{PREFIX}/settings/_all")
    async def get_all_settings():
        if DB is None:
            return {"settings": {}}
        try:
            keys = [
                "showNsfw",
                "defaultModelTypes",
                "defaultBaseModels",
                "defaultModelType",
                "defaultBaseModel",
                "defaultSort",
                "defaultPeriod",
                "nsfwBlur",
                "civitaiRedApiKey",
                "useCivitaiRed",
            ]
            result: dict[str, Any] = {}
            for key in keys:
                val = DB.get_setting(key)
                if val is not None:
                    try:
                        result[key] = json.loads(val)
                    except Exception:
                        result[key] = val
            return {"settings": result}
        except Exception as e:
            return {"settings": {}, "error": str(e)}

    @app.post(f"{PREFIX}/settings/_all")
    async def set_all_settings(request: Request):
        if DB is None:
            raise HTTPException(status_code=500, detail="Rust core not available")
        try:
            body = await request.json()
            value = body.get("value", "{}")
            if isinstance(value, str):
                settings = json.loads(value)
            else:
                settings = value
            for key, val in (settings or {}).items():
                if not isinstance(val, str):
                    val = json.dumps(val)
                DB.set_setting(key, val)
            return {"status": "ok"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post(f"{PREFIX}/settings/validate-key")
    async def validate_api_key(request: Request):
        body = await request.json()
        key = body.get("key", "").strip()
        if not key:
            return {"valid": False, "message": "Key is empty"}

        client = get_http_client()
        try:
            resp = await client.get(
                f"{CIVITAI_RED_API}/models",
                params={"limit": 1, "favorites": "true", "token": key},
                timeout=15.0,
            )
            if resp.status_code == 200:
                if DB is not None:
                    DB.set_setting("civitaiRedApiKey", key)
                return {"valid": True, "message": "Key is valid"}
            elif resp.status_code in (401, 403):
                return {"valid": False, "message": "Invalid or unauthorized key"}
            else:
                return {"valid": False, "message": f"Server returned {resp.status_code}"}
        except httpx.TimeoutException:
            return {"valid": False, "message": "Connection timed out"}
        except Exception as e:
            return {"valid": False, "message": str(e)}

    @app.get(f"{PREFIX}/settings/{{key:path}}")
    async def get_setting(key: str):
        if DB is None:
            return {"key": key, "value": None}
        try:
            value = DB.get_setting(key)
            return {"key": key, "value": value}
        except Exception as e:
            logger.error(f"Failed to get setting {key}: {e}")
            return {"key": key, "value": None}

    @app.post(f"{PREFIX}/settings/{{key:path}}")
    async def set_setting(key: str, request: Request):
        if DB is None:
            raise HTTPException(status_code=500, detail="Rust core not available")
        try:
            body = await request.json()
            value = body.get("value")
            if value is None:
                raise HTTPException(status_code=400, detail="value is required")
            if not isinstance(value, str):
                value = json.dumps(value)
            DB.set_setting(key, value)
            return {"key": key, "value": value}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to set setting {key}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save setting: {str(e)}")

    @app.delete(f"{PREFIX}/cache")
    async def clear_cache():
        clear_caches()
        if DB is not None:
            try:
                DB.clear_cache()
            except Exception as e:
                logger.error(f"Failed to clear cache: {e}")

        import shutil

        from .config import CACHE_DIR

        try:
            if CACHE_DIR.exists():
                shutil.rmtree(CACHE_DIR)
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to clear file cache: {e}")

        return {"status": "ok", "message": "Cache cleared"}
