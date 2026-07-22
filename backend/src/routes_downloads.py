from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import HTTPException, Request

from .downloads import (
    create_download_entry,
    find_entry,
    get_queue,
    get_throttle_until,
    invalidate_installed_cache,
    remove_entry,
    reorder_queue,
    schedule_downloads,
    set_throttle,
)
from .client import DB

logger = logging.getLogger("civbro.api")

PREFIX = "/civbro/api"


def register_download_routes(app: Any) -> None:
    @app.post(f"{PREFIX}/download/throttle")
    async def set_download_throttle(request: Request):
        try:
            body = await request.json()
            set_throttle(body.get("enable", True))
        except Exception:
            set_throttle(True)
        return {"throttled": get_throttle_until() > time.time()}

    @app.post(f"{PREFIX}/download")
    async def start_download(request: Request):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        download_url = body.get("downloadUrl")
        if not download_url:
            raise HTTPException(status_code=400, detail="downloadUrl is required")

        entry = create_download_entry(
            model_id=body.get("modelId"),
            version_id=body.get("versionId"),
            file_id=body.get("fileId"),
            file_name=body.get("fileName", "model.safetensors"),
            download_url=download_url,
            download_dir=body.get("downloadDir", ""),
            size_kb=body.get("sizeKB") or 0,
            model_type=body.get("modelType", "Checkpoint"),
        )
        await schedule_downloads()
        return entry

    @app.get(f"{PREFIX}/download/queue")
    async def get_download_queue():
        return {"items": get_queue()}

    @app.post(f"{PREFIX}/download/reorder")
    async def reorder_download_queue(request: Request):
        try:
            body = await request.json()
            order: list[str] = body.get("order", [])
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        reorder_queue(order)
        return {"ok": True}

    @app.delete(f"{PREFIX}/download/{{download_id}}")
    async def cancel_download(download_id: str):
        entry = find_entry(download_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Download not found")

        if entry["status"] in ("pending", "downloading"):
            entry["status"] = "cancelled"
            entry["updatedAt"] = time.time()
            if DB is not None:
                try:
                    DB.update_download_status(download_id, "cancelled")
                except Exception as e:
                    logger.debug(f"Failed to update download status: {e}")

        remove_entry(download_id)
        return {"status": "cancelled"}
