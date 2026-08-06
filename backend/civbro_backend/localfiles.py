"""Local-filesystem domain logic: sidecar naming, model deletion, and
on-disk install status. No FastAPI imports — pure, testable functions."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .rust_facade import subdir_for_type

logger = logging.getLogger("civbro.api")

SIDECAR_SUFFIX = ".civitai.info"
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
