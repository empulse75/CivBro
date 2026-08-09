from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import Query

from . import config
from .client import DB, RUST_AVAILABLE, get_civitai_key, http_get_with_retry
from .config import CIVITAI_REST_API, EXTENSION_DIR, TYPE_BY_DIR
from .localfiles import (
    build_file_status,
    delete_model_files,
    get_installed_cache,
    invalidate_installed_cache,
    scan_directories,
    scan_installed,
    scan_local_models,
    refresh_database,
)
from .trpc_extras import fetch_trpc_version_detail

logger = logging.getLogger("civbro.api")

PREFIX = "/civbro/api"


def register_local_routes(app: Any) -> None:
    @app.get(f"{PREFIX}/local/scan")
    async def scan_local_directories():
        import os

        sd_paths = [
            os.environ.get("SD_WEBUI_MODELS_DIR", ""),
            str(EXTENSION_DIR.parent.parent / "models"),
        ]
        results: dict[str, Any] = {}
        for sd_path in sd_paths:
            if not sd_path or not os.path.isdir(sd_path):
                continue
            scanned = await asyncio.to_thread(
                scan_directories, sd_path, TYPE_BY_DIR, RUST_AVAILABLE
            )
            for k, v in scanned.items():
                if k == "metadata":
                    results["metadata"] = v
                elif k in results:
                    results[k]["paths"].extend(v["paths"])
                    results[k]["fileCount"] += v["fileCount"]
                else:
                    results[k] = v
        if "metadata" not in results:
            results["metadata"] = {
                "rust_enabled": RUST_AVAILABLE,
                "parallel_workers": 1,
            }
        return results

    @app.get(f"{PREFIX}/local/filestatus")
    async def local_filestatus(version_id: int, verify: int = 0):
        try:
            resp = await http_get_with_retry(
                f"{CIVITAI_REST_API}/model-versions/{version_id}", timeout=20.0
            )
            if resp.status_code != 200:
                return {"files": []}
            data = resp.json()
        except Exception as e:
            logger.debug(f"filestatus fetch failed: {e}")
            return {"files": []}

        trpc = await fetch_trpc_version_detail(version_id, get_civitai_key())
        files = await asyncio.to_thread(
            build_file_status, data, trpc, config.MODELS_ROOT, verify, RUST_AVAILABLE
        )
        return {"files": files}

    @app.get(f"{PREFIX}/local/installed")
    async def local_installed():
        import time as _time

        now = _time.time()
        cache = get_installed_cache()
        if cache["t"] and (now - cache["t"] < 20):
            return {"versionIds": cache["versions"], "modelIds": cache["models"]}

        v_sorted, m_sorted = await asyncio.to_thread(scan_installed, config.MODELS_ROOT)
        cache["t"] = now
        cache["versions"] = v_sorted
        cache["models"] = m_sorted
        return {"versionIds": cache["versions"], "modelIds": cache["models"]}

    @app.get(f"{PREFIX}/local/models")
    async def get_local_models():
        items = await asyncio.to_thread(scan_local_models, config.MODELS_ROOT, TYPE_BY_DIR)
        return {"items": items}

    @app.delete(f"{PREFIX}/local/delete")
    async def delete_local_model_files(model_id: int):
        try:
            removed = await asyncio.to_thread(
                delete_model_files, config.MODELS_ROOT, model_id
            )
        except Exception as e:
            logger.debug(f"delete local model {model_id} failed: {e}")
            removed = 0
        invalidate_installed_cache()
        return {"removed": removed, "modelId": model_id}

    @app.post(f"{PREFIX}/local/refresh")
    async def refresh_local_database():
        import os

        if DB is None and not RUST_AVAILABLE:
            return {
                "status": "error",
                "message": "Rust core not available - cannot refresh database",
            }

        sd_path = os.environ.get(
            "SD_WEBUI_MODELS_DIR",
            str(EXTENSION_DIR.parent.parent / "models"),
        )

        try:
            scanned_files = await asyncio.to_thread(refresh_database, sd_path, RUST_AVAILABLE)
            return {
                "status": "ok",
                "filesFound": len(scanned_files),
                "files": scanned_files[:1000],
            }
        except Exception as e:
            logger.error(f"Refresh failed: {e}")
            return {"status": "error", "message": str(e)}
