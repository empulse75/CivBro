"""Local-filesystem domain logic: scanning, sidecar naming, model deletion,
installed-version tracking, and on-disk install status.
No FastAPI imports — pure, testable functions."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .config import MODEL_EXTENSIONS
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

# WebUI directories that hold the same model type as a canonical TYPE_BY_DIR
# entry but under a different name. Everything else is derived from the shared
# directory map so scanning covers every type the downloader can route to.
ALIAS_DIRS: dict[str, str] = {
    "SwinIR": "Upscaler",
    "RealESRGAN": "Upscaler",
}


def _dirs_by_type(type_by_dir: dict[str, str]) -> dict[str, list[str]]:
    """Invert {dir: type} into {type: [dirs]}, including alias directories."""
    out: dict[str, list[str]] = {}
    for dir_name, model_type in {**type_by_dir, **ALIAS_DIRS}.items():
        out.setdefault(model_type, []).append(dir_name)
    return out


def scan_directories(models_root: str, type_by_dir: dict[str, str], rust_available: bool) -> dict[str, Any]:
    """Enumerate model directories and count files by type."""
    from . import config

    results: dict[str, Any] = {}

    for model_type, dir_names in _dirs_by_type(type_by_dir).items():
        for dir_name in dir_names:
            dir_str = config.get_model_dir(dir_name, models_root)
            dir_path = Path(dir_str)
            if dir_path.is_dir():
                try:
                    count = sum(
                        1
                        for p in dir_path.iterdir()
                        if p.is_file() and p.suffix.lower() in MODEL_EXTENSIONS
                    )
                    if model_type not in results:
                        results[model_type] = {"paths": [], "fileCount": 0}
                    results[model_type]["paths"].append(str(dir_path))
                    results[model_type]["fileCount"] += count
                except Exception as e:
                    logger.debug(f"scan_directories failed for {dir_path}: {e}")

    results["metadata"] = {
        "rust_enabled": rust_available,
        "parallel_workers": min(os.cpu_count() or 4, 8) if rust_available else 1,
    }
    return results

def scan_installed(models_root: str) -> tuple[list[int], list[int]]:
    """Walk sidecars and return (sorted version IDs, sorted model IDs)."""
    from . import config

    versions: set[int] = set()
    models: set[int] = set()
    roots = config.get_allowed_model_roots(models_root)
    seen_infos: set[Path] = set()

    for root in roots:
        if not root.is_dir():
            continue
        try:
            for info in root.rglob(f"*{SIDECAR_SUFFIX}"):
                try:
                    info_res = info.resolve()
                    if info_res in seen_infos:
                        continue
                    seen_infos.add(info_res)
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
            logger.debug(f"scan_installed failed for {root}: {e}")
    return sorted(versions), sorted(models)

def scan_local_models(models_root: str, type_by_dir: dict[str, str]) -> list[dict]:
    """List all model files with sidecar metadata across allowed model roots."""
    from . import config

    roots = config.get_allowed_model_roots(models_root)
    category_roots = sorted(
        ((Path(config.get_model_dir(name, models_root)).resolve(), kind)
         for name, kind in {**type_by_dir, **ALIAS_DIRS}.items()),
        key=lambda pair: len(pair[0].parts), reverse=True,
    )
    items: list[dict] = []
    seen_paths: set[Path] = set()
    idc = 0

    for root in roots:
        if not root.is_dir():
            continue
        try:
            for p in root.rglob("*"):
                if not p.is_file() or p.suffix.lower() not in MODEL_EXTENSIONS:
                    continue
                try:
                    p_res = p.resolve()
                    if p_res in seen_paths:
                        continue
                    seen_paths.add(p_res)
                except Exception:
                    pass

                mtype = next(
                    (kind for directory, kind in category_roots if p.resolve().is_relative_to(directory)),
                    "Other",
                )

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
            logger.error(f"Failed to list local models in {root}: {e}")
    items.sort(key=lambda m: m["name"].lower())
    return items

def refresh_database(
    models_root: str, rust_available: bool, type_by_dir: dict[str, str] | None = None
) -> list[dict]:
    """Scan model directories using Rust when available."""
    from . import config

    scanned: list[dict] = []
    if not rust_available:
        return scanned
    from .config import TYPE_BY_DIR
    from .rust_facade import scan_model_dir

    if type_by_dir is None:
        type_by_dir = TYPE_BY_DIR

    extensions = [ext.lstrip(".") for ext in sorted(MODEL_EXTENSIONS)]
    for dir_name, model_type in {**type_by_dir, **ALIAS_DIRS}.items():
        dir_path = config.get_model_dir(dir_name, models_root)
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
    from . import config

    roots = config.get_allowed_model_roots(models_root)
    removed = 0
    seen_sidecars: set[Path] = set()

    for root in roots:
        if not root.is_dir():
            continue
        try:
            for info in root.rglob(f"*{SIDECAR_SUFFIX}"):
                try:
                    info_res = info.resolve()
                    if info_res in seen_sidecars:
                        continue
                    seen_sidecars.add(info_res)
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
        except Exception as e:
            logger.debug(f"delete_model_files failed for {root}: {e}")
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
    from . import config

    name = f.get("name") or ""
    sub = subdir_for_type(f.get("type", ""), name, model_type)
    expected = int((f.get("sizeKB") or 0) * 1024)
    target_dir = config.get_model_dir(sub, models_root)
    status, hash_ok = _entry_status(
        Path(target_dir) / name,
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
