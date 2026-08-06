from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .client import DB, http_get_with_retry
from .config import ALLOWED_SETTING_KEYS, CIVITAI_RED_API, SENSITIVE_SETTING_KEYS
from .cache import clear_caches

logger = logging.getLogger("civbro.api")

PREFIX = "/civbro/api"

# Keys readable via the API: allowed minus write-only secrets.
_READABLE_SETTING_KEYS = sorted(ALLOWED_SETTING_KEYS - SENSITIVE_SETTING_KEYS)


def register_settings_routes(app: Any) -> None:
    @app.get(f"{PREFIX}/settings/_all")
    async def get_all_settings():
        if DB is None:
            return JSONResponse(
                {"settings": {}, "capabilities": {"hasCivitaiRedApiKey": False}},
                headers={"Cache-Control": "no-store"},
            )
        try:
            result: dict[str, Any] = {}
            for key in _READABLE_SETTING_KEYS:
                val = DB.get_setting(key)
                if val is not None:
                    try:
                        result[key] = json.loads(val)
                    except Exception:
                        result[key] = val
            return JSONResponse(
                {
                    "settings": result,
                    "capabilities": {
                        "hasCivitaiRedApiKey": bool(DB.get_setting("civitaiRedApiKey")),
                    },
                },
                headers={"Cache-Control": "no-store"},
            )
        except Exception as e:
            return JSONResponse(
                {"settings": {}, "capabilities": {"hasCivitaiRedApiKey": False}, "error": str(e)},
                headers={"Cache-Control": "no-store"},
            )

    @app.post(f"{PREFIX}/settings/_all")
    async def set_all_settings(request: Request):
        if DB is None:
            raise HTTPException(status_code=500, detail="Rust core not available")
        try:
            body = await request.json()
            value = body.get("value", "{}")
            settings = json.loads(value) if isinstance(value, str) else value
            for key, val in (settings or {}).items():
                if key not in ALLOWED_SETTING_KEYS:
                    logger.debug(f"Ignoring unknown setting key: {key}")
                    continue
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

        try:
            resp = await http_get_with_retry(
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

    @app.post(f"{PREFIX}/license/ingest")
    async def ingest_license(request: Request):
        body = await request.json()
        key = body.get("key", "").strip()
        if not key:
            return {"status": "error", "message": "License key is empty"}

        if DB is None:
            raise HTTPException(status_code=500, detail="Rust core not available")

        try:
            result = DB.ingest_license(key)
            if result == "ok":
                return {"status": "ok", "message": "License key ingested"}
            elif result.startswith("invalid:"):
                return {"status": "invalid", "message": result[len("invalid:"):]}
            else:
                return {"status": "error", "message": result}
        except Exception as e:
            logger.error(f"License ingestion failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get(f"{PREFIX}/license/status")
    async def license_status():
        if DB is None:
            return {"active": False}
        try:
            active = DB.is_license_active()
            return {"active": active}
        except Exception as e:
            logger.error(f"License status check failed: {e}")
            return {"active": False}

    @app.get(f"{PREFIX}/settings/{{key:path}}")
    async def get_setting(key: str):
        if DB is None or key in SENSITIVE_SETTING_KEYS:
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
        if key not in ALLOWED_SETTING_KEYS:
            raise HTTPException(status_code=400, detail=f"Unknown setting key: {key}")
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

        return {"status": "ok", "message": "Cache cleared"}
