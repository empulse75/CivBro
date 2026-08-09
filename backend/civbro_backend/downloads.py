from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from . import config
from .client import DB, get_http_client, get_civitai_key, http_get_with_retry
from .config import (
    CIVITAI_REST_API,
    LARGE_THRESHOLD_KB,
    MAX_LARGE_CONCURRENT,
    MAX_SMALL_CONCURRENT,
    THROTTLE_DURATION,
)
from .trpc_extras import fetch_trpc_version_detail
from .rust_facade import optimize_image_url, subdir_for_type
from .localfiles import invalidate_installed_cache

logger = logging.getLogger("civbro.api")

_download_queue: list[dict] = []
_schedule_lock = asyncio.Lock()
_download_throttle_until: float = 0.0


def resolve_download_path(download_dir: str, file_name: str) -> str:
    """Jail a download target inside MODELS_ROOT.

    Raises ValueError on any attempt to escape the models root or to smuggle
    path separators through the file name (review finding 1.1).
    """
    if not file_name or file_name != os.path.basename(file_name) or "\\" in file_name:
        raise ValueError(f"Illegal file name: {file_name!r}")
    root = Path(config.MODELS_ROOT).resolve()
    target_dir = Path(download_dir).resolve() if download_dir else root
    if not target_dir.is_relative_to(root):
        raise ValueError(f"Download dir escapes models root: {download_dir!r}")
    return str(target_dir / file_name)


def is_large(entry: dict) -> bool:
    kb = entry.get("sizeKB") or 0
    if not kb and entry.get("bytesTotal"):
        kb = entry["bytesTotal"] / 1024
    if not kb:
        return True
    return kb > LARGE_THRESHOLD_KB


async def schedule_downloads() -> None:
    async with _schedule_lock:
        active_large = sum(
            1 for d in _download_queue if d["status"] == "downloading" and is_large(d)
        )
        active_small = sum(
            1 for d in _download_queue if d["status"] == "downloading" and not is_large(d)
        )
        for d in _download_queue:
            if d["status"] != "pending":
                continue
            large = is_large(d)
            if large and active_large < MAX_LARGE_CONCURRENT:
                active_large += 1
                d["status"] = "downloading"
                d["updatedAt"] = time.time()
                asyncio.create_task(_process_download(d["id"]))
            elif not large and active_small < MAX_SMALL_CONCURRENT:
                active_small += 1
                d["status"] = "downloading"
                d["updatedAt"] = time.time()
                asyncio.create_task(_process_download(d["id"]))


async def _save_download_sidecar(
    entry: dict, download_path: str, api_key: str
) -> None:
    version_id = entry.get("versionId")
    if not version_id:
        return
    base = str(Path(download_path).with_suffix(""))

    params = {"token": api_key} if api_key else None
    resp = await http_get_with_retry(
        f"{CIVITAI_REST_API}/model-versions/{version_id}",
        params=params,
        timeout=30.0,
    )
    if resp.status_code != 200:
        logger.debug(f"sidecar: version {version_id} metadata HTTP {resp.status_code}")
        return
    data = resp.json()

    try:
        with open(base + ".civitai.info", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"sidecar .civitai.info write failed: {e}")

    try:
        model_info = data.get("model") or {}
        meta = {
            "description": model_info.get("description") or data.get("description") or "",
            "sd version": data.get("baseModel", ""),
            "activation text": ", ".join(data.get("trainedWords", []) or []),
            "preferred weight": 0,
            "modelId": data.get("modelId"),
            "modelVersionId": data.get("id"),
            "notes": "",
        }
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"sidecar .json write failed: {e}")

    images = data.get("images") or []
    preview_url = None
    for img in images:
        if isinstance(img, dict) and img.get("url") and img.get("type") != "video":
            preview_url = img["url"]
            break
    if not preview_url:
        return
    preview_url = optimize_image_url(preview_url, 512, "image")
    try:
        img_resp = await http_get_with_retry(
            preview_url,
            follow_redirects=True,
            headers={"Accept": "image/*,*/*"},
            timeout=60.0,
        )
        if img_resp.status_code == 200:
            ct = img_resp.headers.get("content-type", "").lower()
            ext = (
                "png"
                if "png" in ct
                else ("webp" if "webp" in ct else ("gif" if "gif" in ct else "jpeg"))
            )
            with open(base + f".preview.{ext}", "wb") as f:
                f.write(img_resp.content)
    except Exception as e:
        logger.debug(f"sidecar preview image failed: {e}")


async def _process_download(download_id: str) -> None:
    entry = next((d for d in _download_queue if d["id"] == download_id), None)
    if entry is None:
        logger.warning(f"Download {download_id}: entry vanished from queue before processing — skipping")
        await schedule_downloads()
        return

    entry["status"] = "downloading"
    entry["updatedAt"] = time.time()

    client = get_http_client()
    download_path = Path(entry["downloadPath"])
    download_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = download_path.with_name(download_path.name + ".part")

    req_url = entry["url"]
    api_key = get_civitai_key()
    download_headers: dict[str, str] = {"Accept": "*/*"}

    if "civitai.red" in req_url and not api_key:
        raise RuntimeError(
            "Download requires an API key — add one in the CivBro sidebar"
        )

    if api_key:
        if "civitai.red" in req_url:
            if "token=" not in req_url:
                sep = "&" if "?" in req_url else "?"
                req_url = f"{req_url}{sep}token={api_key}"
        elif "civitai.com" in req_url:
            download_headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with client.stream(
            "GET", req_url, follow_redirects=True, headers=download_headers
        ) as response:
            if response.status_code == 401:
                raise RuntimeError(
                    "Download requires an API key — add one in the CivBro sidebar"
                )
            if response.status_code == 403:
                raise RuntimeError(
                    "This model requires Buzz to download — unlock it on civitai.com first, then retry"
                )
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length:
                entry["bytesTotal"] = int(content_length)

            with open(part_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if entry.get("status") == "cancelled":
                        break
                    f.write(chunk)
                    entry["bytesDownloaded"] += len(chunk)
                    if time.time() < _download_throttle_until:
                        await asyncio.sleep(0.05)
                    if entry["bytesTotal"] > 0:
                        entry["progress"] = min(
                            100,
                            int(entry["bytesDownloaded"] / entry["bytesTotal"] * 100),
                        )

        if entry.get("status") == "cancelled":
            try:
                if part_path.exists():
                    part_path.unlink()
            except Exception as ce:
                logger.debug(f"Failed to remove cancelled partial {part_path}: {ce}")
            entry["updatedAt"] = time.time()
            if DB is not None:
                try:
                    DB.update_download_status(download_id, "cancelled")
                except Exception:
                    pass
            async with _schedule_lock:
                _download_queue[:] = [d for d in _download_queue if d.get("id") != download_id]
            await schedule_downloads()
            return

        expected = entry.get("bytesTotal") or 0
        got = part_path.stat().st_size if part_path.exists() else 0
        if expected > 0 and got < expected:
            raise ValueError(f"Incomplete download: {got}/{expected} bytes")
        if got == 0:
            raise ValueError("Downloaded 0 bytes")

        os.replace(str(part_path), str(download_path))

        entry["status"] = "completed"
        entry["progress"] = 100

        try:
            await _save_download_sidecar(entry, download_path, api_key)
        except Exception as se:
            logger.warning(f"Sidecar (preview/metadata) save failed for {download_id}: {se}")
        invalidate_installed_cache()
    except Exception as e:
        entry["status"] = "failed"
        entry["errorMessage"] = str(e)
        logger.error(f"Download {download_id} failed: {e}")
        try:
            if part_path.exists():
                part_path.unlink()
        except Exception as ce:
            logger.debug(f"Failed to remove partial file {part_path}: {ce}")

    entry["updatedAt"] = time.time()

    if DB is not None:
        try:
            DB.update_download_status(download_id, entry["status"])
        except Exception as e:
            logger.debug(f"Failed to update download status: {e}")

    await schedule_downloads()


def get_queue() -> list[dict]:
    return _download_queue


def create_download_entry(
    model_id: Any,
    version_id: Any,
    file_id: Any,
    file_name: str,
    download_url: str,
    download_dir: str,
    size_kb: Any,
    model_type: str = "Checkpoint",
) -> dict:
    download_path = resolve_download_path(download_dir, file_name)
    download_id = uuid.uuid4().hex[:12]
    entry = {
        "id": download_id,
        "modelId": model_id,
        "versionId": version_id,
        "fileId": file_id,
        "fileName": file_name,
        "url": download_url,
        "downloadPath": download_path,
        "modelType": model_type,
        "sizeKB": size_kb,
        "status": "pending",
        "progress": 0,
        "bytesTotal": int(size_kb * 1024) if size_kb else 0,
        "bytesDownloaded": 0,
        "errorMessage": None,
        "createdAt": time.time(),
        "updatedAt": time.time(),
    }
    _download_queue.append(entry)

    if DB is not None:
        try:
            DB.add_download(json.dumps(entry))
        except Exception as e:
            logger.debug(f"Failed to add download to DB: {e}")

    return entry


def find_entry(download_id: str) -> dict | None:
    return next((d for d in _download_queue if d["id"] == download_id), None)


async def remove_entry(download_id: str) -> None:
    async with _schedule_lock:
        _download_queue[:] = [d for d in _download_queue if d["id"] != download_id]


async def reorder_queue(order: list[str]) -> None:
    async with _schedule_lock:
        by_id = {d["id"]: d for d in _download_queue}
        seen: set[str] = set()
        new_queue: list[dict] = []
        for did in order:
            d = by_id.get(did)
            if d and d["status"] in ("pending", "queued"):
                new_queue.append(d)
                seen.add(did)
        for d in _download_queue:
            if d["id"] not in seen and d["status"] in ("pending", "queued"):
                new_queue.append(d)
                seen.add(d["id"])
        for d in _download_queue:
            if d["id"] not in seen:
                new_queue.append(d)
                seen.add(d["id"])
        _download_queue[:] = new_queue


def get_throttle_until() -> float:
    return _download_throttle_until


def set_throttle(enabled: bool) -> None:
    global _download_throttle_until
    if enabled:
        _download_throttle_until = time.time() + THROTTLE_DURATION
    else:
        _download_throttle_until = 0.0





def recover_stale_downloads() -> int:
    if DB is None:
        return 0
    try:
        prior = DB.get_pending_downloads()
        data = json.loads(prior) if isinstance(prior, str) else prior
        rows = data if isinstance(data, list) else []
    except Exception:
        return 0
    requeue_count = 0
    for r in rows:
        status = r.get("status", "")
        if status not in ("pending", "queued", "downloading"):
            continue
        r["status"] = "pending"
        r["progress"] = 0
        r["bytesDownloaded"] = 0
        r["errorMessage"] = None
        r["updatedAt"] = time.time()
        requeue_count += 1
        try:
            DB.update_download_status(r.get("id", ""), "pending")
            part_path = Path(r.get("downloadPath", "")).with_name(
                (r.get("fileName") or "") + ".part"
            )
            if part_path.exists():
                part_path.unlink()
        except Exception as e:
            logger.warning(f"failed to clean up stale download {r.get('id', '?')}: {e}")
        entry = {
            "id": r.get("id", ""),
            "modelId": r.get("modelId"),
            "versionId": r.get("versionId"),
            "fileId": r.get("fileId"),
            "fileName": r.get("fileName", ""),
            "url": r.get("downloadUrl", ""),
            "downloadPath": r.get("downloadPath", ""),
            "modelType": r.get("modelType", ""),
            "sizeKB": 0,
            "status": "pending",
            "progress": 0,
            "bytesTotal": r.get("bytesTotal", 0),
            "bytesDownloaded": 0,
            "errorMessage": None,
            "createdAt": r.get("createdAt", time.time()),
            "updatedAt": time.time(),
        }
        if not any(d["id"] == entry["id"] for d in _download_queue):
            _download_queue.append(entry)
    if requeue_count:
        logger.info(
            f"[CivBro] Re-queued {requeue_count} download(s) from previous session"
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(schedule_downloads())
        except RuntimeError:
            pass
    return requeue_count
