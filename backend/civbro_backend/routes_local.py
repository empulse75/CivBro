from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from fastapi import Query

from . import config
from .client import DB, RUST_AVAILABLE, get_civitai_key, http_get_with_retry
from .config import (
    CIVITAI_REST_API,
    EXTENSION_DIR,
    MODEL_EXTENSIONS,
    TYPE_BY_DIR,
)
from .downloads import get_installed_cache, invalidate_installed_cache
from .localfiles import build_file_status, delete_model_files
from .trpc_extras import fetch_trpc_version_detail

logger = logging.getLogger("civbro.api")

PREFIX = "/civbro/api"


def register_local_routes(app: Any) -> None:
    @app.get(f"{PREFIX}/local/scan")
    async def scan_local_directories():
        sd_paths = [
            os.environ.get("SD_WEBUI_MODELS_DIR", ""),
            str(EXTENSION_DIR.parent.parent / "models"),
        ]

        results: dict[str, Any] = {}
        for sd_path in sd_paths:
            if not sd_path or not os.path.isdir(sd_path):
                continue
            base = Path(sd_path)
            model_types: dict[str, list[str]] = {
                "Checkpoint": ["Stable-diffusion"],
                "LORA": ["Lora"],
                "TextualInversion": ["embeddings"],
                "VAE": ["VAE"],
                "Controlnet": ["ControlNet"],
                "Upscaler": ["ESRGAN", "SwinIR", "RealESRGAN"],
            }

            for model_type, dir_names in model_types.items():
                for dir_name in dir_names:
                    dir_path = base / dir_name
                    if dir_path.is_dir():
                        count = 0
                        for ext in ["*.safetensors", "*.ckpt", "*.pt", "*.bin"]:
                            count += len(list(dir_path.glob(ext)))
                        if model_type not in results:
                            results[model_type] = {"paths": [], "fileCount": 0}
                        results[model_type]["paths"].append(str(dir_path))
                        results[model_type]["fileCount"] += count

        results["metadata"] = {
            "rust_enabled": RUST_AVAILABLE,
            "parallel_workers": min(os.cpu_count() or 4, 8) if RUST_AVAILABLE else 1,
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
        now = time.time()
        cache = get_installed_cache()
        if cache["t"] and (now - cache["t"] < 20):
            return {"versionIds": cache["versions"], "modelIds": cache["models"]}

        def _scan_installed():
            versions: set[int] = set()
            models: set[int] = set()
            root = Path(config.MODELS_ROOT)
            try:
                for info in root.rglob("*.civitai.info"):
                    try:
                        data = json.loads(info.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    vid = data.get("id")
                    mid = data.get("modelId")
                    if isinstance(vid, int):
                        versions.add(vid)
                    if isinstance(mid, int):
                        models.add(mid)
            except Exception as e:
                logger.debug(f"local_installed scan failed: {e}")
            return sorted(versions), sorted(models)

        v_sorted, m_sorted = await asyncio.to_thread(_scan_installed)
        cache["t"] = now
        cache["versions"] = v_sorted
        cache["models"] = m_sorted
        return {"versionIds": cache["versions"], "modelIds": cache["models"]}

    @app.get(f"{PREFIX}/local/models")
    async def get_local_models():
        def _scan() -> list[dict]:
            root = Path(config.MODELS_ROOT)
            items: list[dict] = []
            idc = 0
            try:
                for p in root.rglob("*"):
                    if not p.is_file() or p.suffix.lower() not in MODEL_EXTENSIONS:
                        continue
                    try:
                        rel = p.relative_to(root)
                        top = rel.parts[0] if rel.parts else ""
                    except Exception:
                        top = ""
                    mtype = TYPE_BY_DIR.get(top, top or "Other")
                    name = p.stem
                    model_id = None
                    version_id = None
                    sidecar = p.with_name(p.stem + ".civitai.info")
                    if sidecar.exists():
                        try:
                            info = json.loads(sidecar.read_text(encoding="utf-8"))
                            version_id = (
                                info.get("id")
                                if isinstance(info.get("id"), int)
                                else version_id
                            )
                            model_id = (
                                info.get("modelId")
                                if isinstance(info.get("modelId"), int)
                                else model_id
                            )
                            mname = (info.get("model") or {}).get("name")
                            if mname:
                                name = mname
                        except Exception:
                            pass
                    try:
                        size = p.stat().st_size
                    except Exception:
                        size = 0
                    idc += 1
                    items.append({
                        "id": idc,
                        "name": name,
                        "path": str(p),
                        "size": size,
                        "modelId": model_id,
                        "versionId": version_id,
                        "type": mtype,
                        "installed": True,
                    })
            except Exception as e:
                logger.error(f"Failed to list local models: {e}")
            items.sort(key=lambda m: m["name"].lower())
            return items

        return {"items": await asyncio.to_thread(_scan)}

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
        if DB is None and not RUST_AVAILABLE:
            return {
                "status": "error",
                "message": "Rust core not available - cannot refresh database",
            }

        sd_path = os.environ.get(
            "SD_WEBUI_MODELS_DIR",
            str(EXTENSION_DIR.parent.parent / "models"),
        )

        def _do_scan() -> list[dict]:
            scanned: list[dict] = []
            if RUST_AVAILABLE:
                from .rust_facade import scan_model_dir

                extensions = ["safetensors", "ckpt", "pt", "bin", "pth"]
                model_types_dir = {
                    "Checkpoint": "Stable-diffusion",
                    "LORA": "Lora",
                    "TextualInversion": "embeddings",
                    "VAE": "VAE",
                    "Controlnet": "ControlNet",
                    "Upscaler": "ESRGAN",
                }
                for model_type, dir_name in model_types_dir.items():
                    dir_path = os.path.join(sd_path, dir_name)
                    if not os.path.isdir(dir_path):
                        continue
                    try:
                        parsed = scan_model_dir(dir_path, extensions)
                        for entry in parsed:
                            scanned.append({
                                "path": entry.get("path", ""),
                                "name": entry.get("name", ""),
                                "size": entry.get("size", 0),
                                "modelType": model_type,
                            })
                    except Exception as e:
                        logger.warning(f"Failed to scan {dir_path}: {e}")
                        continue
            return scanned

        try:
            scanned_files = await asyncio.to_thread(_do_scan)
            return {
                "status": "ok",
                "filesFound": len(scanned_files),
                "files": scanned_files[:1000],
            }
        except Exception as e:
            logger.error(f"Refresh failed: {e}")
            return {"status": "error", "message": str(e)}
