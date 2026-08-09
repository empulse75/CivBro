"""Local-filesystem domain logic: scanning, sidecar naming, model deletion,
installed-version tracking, and on-disk install status.
No FastAPI imports — pure, testable functions."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from .rust_facade import subdir_for_type

logger = logging.getLogger("civbro.api")

SIDECAR_SUFFIX = ".civitai.info"

# ── installed-versions cache ─────────────────────────────────────────────────

_installed_cache: dict = {"t": 0.0, "versions": [], "models": []}


def get_installed_cache() -> dict:
    return _installed_cache


def invalidate_installed_cache() -> None:
    _installed_cache["t"] = 0.0


# ── filesystem scanning ─────────────────────────────────────────────────────

MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf"}

MODEL_TYPE_DIRS: dict[str, list[str]] = {
    "Checkpoint": ["Stable-diffusion"],
    "LORA": ["Lora"],
    "TextualInversion": ["embeddings"],
    "VAE": ["VAE"],
    "Controlnet": ["ControlNet"],
    "Upscaler": ["ESRGAN", "SwinIR", "RealESRGAN"],
}

MODEL_TYPE_DIR_SINGLE: dict[str, str] = {
    "Checkpoint": "Stable-diffusion",
    "LORA": "Lora",
    "TextualInversion": "embeddings",
    "VAE": "VAE",
    "Controlnet": "ControlNet",
    "Upscaler": "ESRGAN",
}


def scan_directories(models_root: str, type_by_dir: dict[str, str], rust_available: bool) -> dict[str, Any]:
    """Enumerate model directories and count files by type."""
    results: dict[str, Any] = {}
    base = Path(models_root)
    if not base.is_dir():
        return results

    for model_type, dir_names in MODEL_TYPE_DIRS.items():
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
        "rust_enabled": rust_available,
        "parallel_workers": min(os.cpu_count() or 4, 8) if rust_available else 1,
    }
    return results


def scan_installed(models_root: str) -> tuple[list[int], list[int]]:
    """Walk sidecars and return (sorted version IDs, sorted model IDs)."""
    versions: set[int] = set()
    models: set[int] = set()
    root = Path(models_root)
    try:
        for info in root.rglob(f"*{SIDECAR_SUFFIX}"):
            try:
                data = json.loads(info.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug(f"corrupt sidecar {info}: {e}")
                continue
            vid = data.get("id")
            mid = data.get("modelId")
            if isinstance(vid, int):
                versions.add(vid)
            if isinstance(mid, int):
                models.add(mid)
    except Exception as e:
        logger.debug(f"scan_installed failed: {e}")
    return sorted(versions), sorted(models)


def scan_local_models(models_root: str, type_by_dir: dict[str, str]) -> list[dict]:
    """List all model files with sidecar metadata."""
    root = Path(models_root)
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
                logger.debug(f"unexpected path for {p} inside {root}")
                top = ""
            mtype = type_by_dir.get(top, top or "Other")
            name = p.stem
            model_id = None
            version_id = None
            sidecar = p.with_name(p.stem + SIDECAR_SUFFIX)
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
                except Exception as e:
                    logger.debug(f"failed to read sidecar {sidecar}: {e}")
            try:
                size = p.stat().st_size
            except Exception as e:
                logger.debug(f"stat failed for {p}: {e}")
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


def refresh_database(models_root: str, rust_available: bool) -> list[dict]:
    """Scan model directories using Rust when available."""
    scanned: list[dict] = []
    if not rust_available:
        return scanned
    from .rust_facade import scan_model_dir

    extensions = ["safetensors", "ckpt", "pt", "bin", "pth"]
    for model_type, dir_name in MODEL_TYPE_DIR_SINGLE.items():
        dir_path = os.path.join(models_root, dir_name)
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
    return scanned
DELETE_EXTENSIONS = (
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
)
_SIZE_TOLERANCE_BYTES = 1024
_SIZE_TOLERANCE_RATIO = 0.01


def model_base_from_info(info: Path) -> Path:
    """Map 'name.civitai.info' back to the sidecar writer's base ('name').

    Path.with_suffix('') strips only the last suffix, which broke deletion
    (review finding 1.2).
    """
    name = info.name
    if name.endswith(SIDECAR_SUFFIX):
        name = name[: -len(SIDECAR_SUFFIX)]
    return info.with_name(name)


def delete_model_files(models_root: str, model_id: int) -> int:
    """Delete a model file plus all its sidecars. Returns files removed."""
    root = Path(models_root)
    removed = 0
    for info in root.rglob(f"*{SIDECAR_SUFFIX}"):
        try:
            data = json.loads(info.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("modelId") != model_id:
            continue
        base = model_base_from_info(info)
        for ext in DELETE_EXTENSIONS:
            f = Path(str(base) + ext)
            if not f.exists():
                continue
            try:
                f.unlink()
                removed += 1
            except OSError as e:
                logger.debug(f"delete failed for {f}: {e}")
    return removed


def _hash_ok(path: Path, want_hash: str) -> bool | None:
    try:
        from .rust_facade import compute_file_hash

        got = compute_file_hash(str(path), "sha256")
        return bool(got) and got.lower() == want_hash.lower()
    except Exception as e:
        logger.debug(f"hash verify failed: {e}")
        return None


def _entry_status(path: Path, expected: int, verify: int, rust_available: bool, want_hash: str) -> tuple[str, bool | None]:
    if not path.exists():
        return "missing", None
    actual = path.stat().st_size
    if expected > 0 and abs(actual - expected) > max(_SIZE_TOLERANCE_BYTES, expected * _SIZE_TOLERANCE_RATIO):
        return "incomplete", None
    hash_ok = None
    if verify and rust_available and want_hash:
        hash_ok = _hash_ok(path, want_hash)
    return ("corrupt" if hash_ok is False else "installed"), hash_ok


def _check_file(f: dict, model_type: str, models_root: str, verify: int, rust_available: bool) -> dict:
    name = f.get("name") or ""
    sub = subdir_for_type(f.get("type", ""), name, model_type)
    expected = int((f.get("sizeKB") or 0) * 1024)
    status, hash_ok = _entry_status(
        Path(models_root) / sub / name,
        expected,
        verify,
        rust_available,
        (f.get("hashes") or {}).get("SHA256", ""),
    )
    return {
        "fileId": f.get("id"),
        "name": name,
        "dir": sub,
        "status": status,
        "hashOk": hash_ok,
        "sizeKB": f.get("sizeKB", 0),
    }


def build_file_status(
    data: dict,
    trpc: dict,
    models_root: str,
    verify: int,
    rust_available: bool,
) -> list[dict]:
    """Install status for a version's files and its linked components.

    Pure Python — civbro_core is only touched for optional hash verification,
    so this never crashes when the Rust core is unavailable (finding 1.3).
    """
    model_type = ((data.get("model") or {}).get("type")) or ""
    out: list[dict] = []
    for f in data.get("files", []):
        if f.get("name"):
            out.append(_check_file(f, model_type, models_root, verify, rust_available))
    for c in trpc.get("linkedComponents") or []:
        if not (c.get("fileName") or ""):
            continue
        entry = _check_file(
            {
                "id": c.get("fileId"),
                "name": c["fileName"],
                "sizeKB": c.get("sizeKB"),
                "type": c.get("componentType", ""),
                "hashes": {},
            },
            "",
            models_root,
            verify,
            rust_available,
        )
        entry["dependency"] = True
        out.append(entry)
    return out
