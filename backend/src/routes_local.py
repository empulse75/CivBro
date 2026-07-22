from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Query

from .client import DB, RUST_AVAILABLE, get_http_client, get_civitai_key
from .config import (
    EXTENSION_DIR,
    MODEL_EXTENSIONS,
    MODELS_ROOT,
    TYPE_BY_DIR,
)
from .downloads import get_installed_cache, invalidate_installed_cache
from .trpc_extras import fetch_trpc_version_detail
from .utils import subdir_for_type

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
        client = get_http_client()
        try:
            resp = await client.get(
                f"https://civitai.com/api/v1/model-versions/{version_id}", timeout=20.0
            )
            if resp.status_code != 200:
                return {"files": []}
            data = resp.json()
        except Exception as e:
            logger.debug(f"filestatus fetch failed: {e}")
            return {"files": []}

        model_type = ((data.get("model") or {}).get("type")) or ""
        trpc = await fetch_trpc_version_detail(version_id, get_civitai_key())

        def _build_status() -> list:
            import civbro_core

            out: list[dict] = []

            def _check(name: str, sub: str, expected_kb: Any, file_id: Any, want_hash: str = "") -> dict:
                path = Path(MODELS_ROOT) / sub / name
                expected = int((expected_kb or 0) * 1024)
                status = "missing"
                hash_ok = None
                if path.exists():
                    actual = path.stat().st_size
                    if expected <= 0 or abs(actual - expected) <= max(1024, expected * 0.01):
                        status = "installed"
                        if verify and RUST_AVAILABLE and want_hash:
                            try:
                                got = civbro_core.compute_file_hash(str(path), "sha256")
                                hash_ok = bool(got) and got.lower() == want_hash.lower()
                                if hash_ok is False:
                                    status = "corrupt"
                            except Exception as he:
                                logger.debug(f"hash verify failed: {he}")
                    else:
                        status = "incomplete"
                return {
                    "fileId": file_id,
                    "name": name,
                    "dir": sub,
                    "status": status,
                    "hashOk": hash_ok,
                }

            for f in data.get("files", []):
                name = f.get("name") or ""
                if not name:
                    continue
                r = _check(
                    name,
                    subdir_for_type(f.get("type", ""), name, model_type),
                    f.get("sizeKB"),
                    f.get("id"),
                    (f.get("hashes") or {}).get("SHA256", ""),
                )
                r["sizeKB"] = f.get("sizeKB", 0)
                out.append(r)

            for c in trpc.get("linkedComponents") or []:
                name = c.get("fileName") or ""
                if not name:
                    continue
                sub = subdir_for_type(c.get("componentType", ""), name, "")
                r = _check(name, sub, c.get("sizeKB"), c.get("fileId"))
                r["sizeKB"] = c.get("sizeKB", 0)
                r["dependency"] = True
                out.append(r)
            return out

        return {"files": await asyncio.to_thread(_build_status)}

    @app.get(f"{PREFIX}/local/installed")
    async def local_installed():
        now = time.time()
        cache = get_installed_cache()
        if cache["t"] and (now - cache["t"] < 20):
            return {"versionIds": cache["versions"], "modelIds": cache["models"]}

        def _scan_installed():
            versions: set[int] = set()
            models: set[int] = set()
            root = Path(MODELS_ROOT)
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
            root = Path(MODELS_ROOT)
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
        root = Path(MODELS_ROOT)
        removed = 0
        try:
            for info in root.rglob("*.civitai.info"):
                try:
                    data = json.loads(info.read_text(encoding="utf-8"))
                    if data.get("modelId") == model_id:
                        base = str(Path(info).with_suffix(""))
                        for ext in (
                            ".civitai.info",
                            ".json",
                            ".preview.png",
                            ".preview.jpeg",
                            ".preview.jpg",
                            ".preview.webp",
                            ".safetensors",
                            ".ckpt",
                            ".pt",
                            ".pth",
                            ".bin",
                            ".gguf",
                        ):
                            f = Path(base + ext)
                            if f.exists():
                                f.unlink()
                                removed += 1
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"delete local model {model_id} failed: {e}")
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
                import civbro_core

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
                        result = civbro_core.scan_model_dir(dir_path, extensions)
                        parsed = (
                            json.loads(result)
                            if isinstance(result, str)
                            else result
                        )
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
            else:
                model_types_dir = {
                    "Checkpoint": "Stable-diffusion",
                    "LORA": "Lora",
                    "TextualInversion": "embeddings",
                    "VAE": "VAE",
                    "Controlnet": "ControlNet",
                }
                extensions = ["safetensors", "ckpt", "pt", "bin", "pth"]
                for model_type, dir_name in model_types_dir.items():
                    dir_path = os.path.join(sd_path, dir_name)
                    if not os.path.isdir(dir_path):
                        continue
                    for root_path, _dirs, files in os.walk(dir_path):
                        for f in files:
                            ext = f.rsplit(".", 1)[-1].lower()
                            if ext in extensions:
                                full_path = os.path.join(root_path, f)
                                scanned.append({
                                    "path": full_path,
                                    "name": f,
                                    "size": os.path.getsize(full_path),
                                    "modelType": model_type,
                                })
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
