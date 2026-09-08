"""Local-filesystem domain logic: scanning, sidecar naming, model deletion,
installed-version tracking, and on-disk install status.
No FastAPI imports — pure, testable functions."""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .config import MODEL_EXTENSIONS
from .rust_facade import subdir_for_type

logger = logging.getLogger("civbro.api")

SIDECAR_SUFFIX = ".civitai.info"


# ── filesystem walking and sidecar reads ────────────────────────────────────


def iter_files(root: Path | str) -> Iterator[os.DirEntry]:
    """Yield a DirEntry for every file below `root`.

    os.scandir carries the dirent's file/dir kind, so this costs one syscall
    per directory where Path.rglob("*") costs an extra stat() per entry.
    Directory symlinks are deliberately not followed: rglob does not follow
    them either, and a self-referential link would otherwise loop forever.
    """
    stack: list[str] = [str(root)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file():
                            yield entry
                    except OSError as e:  # entry vanished mid-walk
                        logger.debug(f"skipping {entry.path}: {e}")
        except OSError as e:
            logger.debug(f"cannot scan {current}: {e}")


# path -> (mtime_ns, size, versionId, modelId, model name). Sidecars are
# written once when a download completes, so identity plus mtime and size is a
# sound cache key. This matters because the frontend polls /local/installed
# every 20s and re-parsing every sidecar JSON on a multi-thousand-model
# library is what dominated that request.
_sidecar_meta_cache: dict[str, tuple[int, int, int | None, int | None, str | None]] = {}


def _sidecar_meta(path: str, st: os.stat_result) -> tuple[int | None, int | None, str | None]:
    """Read (versionId, modelId, model name) from a sidecar, memoized on mtime."""
    cached = _sidecar_meta_cache.get(path)
    if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
        return cached[2], cached[3], cached[4]
    try:
        with open(path, "rb") as fh:
            data = json.loads(fh.read())
    except FileNotFoundError:
        return None, None, None
    except Exception as e:
        logger.debug(f"corrupt sidecar {path}: {e}")
        return None, None, None
    vid = data.get("id")
    mid = data.get("modelId")
    name = (data.get("model") or {}).get("name") if isinstance(data.get("model"), dict) else None
    meta = (
        vid if isinstance(vid, int) else None,
        mid if isinstance(mid, int) else None,
        name if isinstance(name, str) and name else None,
    )
    _sidecar_meta_cache[path] = (st.st_mtime_ns, st.st_size, *meta)
    return meta


def _prune_sidecar_cache(live_paths: set[str]) -> None:
    """Drop memo entries for sidecars that no longer exist.

    Only a full sweep of every allowed root may call this; a partial walk would
    evict entries it simply did not visit.
    """
    if len(_sidecar_meta_cache) <= len(live_paths):
        return
    for stale in [p for p in _sidecar_meta_cache if p not in live_paths]:
        _sidecar_meta_cache.pop(stale, None)


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
                        for e in os.scandir(dir_str)
                        if os.path.splitext(e.name)[1].lower() in MODEL_EXTENSIONS
                        and e.is_file()
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

def _category_lookup(models_root: str, type_by_dir: dict[str, str]):
    """Return dir -> model type, resolving each directory at most once.

    The category roots are matched longest-first so a nested category wins over
    an ancestor. Resolving per directory instead of per file is what keeps this
    off the syscall hot path: the previous version called Path.resolve() once
    per candidate category for every file it found.
    """
    from . import config

    category_roots = sorted(
        ((Path(config.get_model_dir(name, models_root)).resolve(), kind)
         for name, kind in {**type_by_dir, **ALIAS_DIRS}.items()),
        key=lambda pair: len(pair[0].parts), reverse=True,
    )
    cache: dict[str, str] = {}

    def lookup(directory: str) -> str:
        hit = cache.get(directory)
        if hit is not None:
            return hit
        try:
            resolved = Path(directory).resolve()
        except OSError:
            resolved = Path(directory)
        kind = next(
            (k for candidate, k in category_roots if resolved.is_relative_to(candidate)),
            "Other",
        )
        cache[directory] = kind
        return kind

    return lookup


def scan_installed(models_root: str) -> tuple[list[int], list[int]]:
    """Walk sidecars and return (sorted version IDs, sorted model IDs)."""
    from . import config

    versions: set[int] = set()
    models: set[int] = set()
    seen_files: set[tuple[int, int]] = set()
    live_paths: set[str] = set()

    for root in config.get_allowed_model_roots(models_root):
        if not root.is_dir():
            continue
        for entry in iter_files(root):
            if not entry.name.endswith(SIDECAR_SUFFIX):
                continue
            try:
                st = entry.stat()
            except OSError as e:
                logger.debug(f"stat failed for {entry.path}: {e}")
                continue
            # (device, inode) dedupes overlapping roots, symlinks and hardlinks
            # using the stat() this loop already needs for the cache key.
            identity = (st.st_dev, st.st_ino)
            if identity in seen_files:
                continue
            seen_files.add(identity)
            live_paths.add(entry.path)
            vid, mid, _ = _sidecar_meta(entry.path, st)
            if vid is not None:
                versions.add(vid)
            if mid is not None:
                models.add(mid)

    _prune_sidecar_cache(live_paths)
    return sorted(versions), sorted(models)


def scan_local_models(models_root: str, type_by_dir: dict[str, str]) -> list[dict]:
    """List all model files with sidecar metadata across allowed model roots."""
    from . import config

    category_of = _category_lookup(models_root, type_by_dir)
    items: list[dict] = []
    seen_files: set[tuple[int, int]] = set()
    idc = 0

    for root in config.get_allowed_model_roots(models_root):
        if not root.is_dir():
            continue
        for entry in iter_files(root):
            stem, ext = os.path.splitext(entry.name)
            if ext.lower() not in MODEL_EXTENSIONS:
                continue
            try:
                st = entry.stat()
            except OSError as e:
                logger.debug(f"stat failed for {entry.path}: {e}")
                continue
            identity = (st.st_dev, st.st_ino)
            if identity in seen_files:
                continue
            seen_files.add(identity)

            directory = os.path.dirname(entry.path)
            sidecar = os.path.join(directory, stem + SIDECAR_SUFFIX)
            version_id = model_id = None
            name = stem
            try:
                sidecar_st = os.stat(sidecar)
            except OSError:
                pass
            else:
                version_id, model_id, model_name = _sidecar_meta(sidecar, sidecar_st)
                if model_name:
                    name = model_name

            idc += 1
            items.append({
                "id": idc,
                "name": name,
                "path": entry.path,
                "size": st.st_size,
                "modelId": model_id,
                "versionId": version_id,
                "type": category_of(directory),
                "installed": True,
            })

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

    removed = 0
    seen_files: set[tuple[int, int]] = set()

    for root in config.get_allowed_model_roots(models_root):
        if not root.is_dir():
            continue
        for entry in iter_files(root):
            if not entry.name.endswith(SIDECAR_SUFFIX):
                continue
            try:
                st = entry.stat()
            except OSError:
                continue
            identity = (st.st_dev, st.st_ino)
            if identity in seen_files:
                continue
            seen_files.add(identity)
            if _sidecar_meta(entry.path, st)[1] != model_id:
                continue
            base = model_base_from_info(Path(entry.path))
            for ext in DELETE_EXTENSIONS:
                f = Path(str(base) + ext)
                try:
                    f.unlink()
                    removed += 1
                except FileNotFoundError:
                    continue
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
