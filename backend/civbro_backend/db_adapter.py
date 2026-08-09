from __future__ import annotations

import logging
import os
from pathlib import Path

from .config import DB_PATH

logger = logging.getLogger("civbro.api")

RUST_AVAILABLE = False
DB = None


def _resolve_db_path(candidates: list[Path] | None = None) -> str:
    if candidates is None:
        env_path = os.environ.get("CIVBRO_DB_PATH")
        if env_path:
            return env_path
        candidates = [DB_PATH]
    target = candidates[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    return str(target)


try:
    import civbro_core

    RUST_AVAILABLE = True
    DB = civbro_core.Database(_resolve_db_path())
    logger.info("[CivBro] Rust core loaded successfully")
except ImportError:
    logger.warning("[CivBro] Rust core not available, using pure Python fallbacks")
    RUST_AVAILABLE = False


def get_civitai_key() -> str:
    if DB is not None:
        try:
            return DB.get_setting("civitaiRedApiKey") or ""
        except Exception:
            return ""
    return ""


def cleanup_orphan_parts() -> int:
    from .config import MODELS_ROOT

    if not RUST_AVAILABLE or not hasattr(civbro_core, "clean_orphan_parts"):
        return 0
    removed = 0
    try:
        removed = civbro_core.clean_orphan_parts(MODELS_ROOT)
    except Exception as e:
        logger.debug(f"orphan .part cleanup failed: {e}", exc_info=True)
    if removed:
        logger.info(f"[CivBro] cleaned {removed} orphan .part file(s)")
    return removed
