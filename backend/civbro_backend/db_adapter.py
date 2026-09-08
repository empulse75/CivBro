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


civbro_core = None

try:
    import civbro_core  # noqa: F811

    # Database() opens the file and runs the schema migration, so it can raise
    # long after the import succeeded (unwritable path, corrupt DB). Only claim
    # the core is available once we actually hold a usable handle.
    DB = civbro_core.Database(_resolve_db_path())
    RUST_AVAILABLE = True
    logger.info("[CivBro] Rust core loaded successfully")
except ImportError as e:
    logger.error(
        "[CivBro] Rust core (civbro_core) could not be imported: %s — "
        "CivBro has no Python fallback, so its endpoints will return errors. "
        "Build it with `cargo build --release` in core_rust/ or reinstall the "
        "extension so install.py can build it.",
        e,
    )
except Exception as e:
    # Never let a bad database take down WebUI startup: the extension is
    # imported inside the WebUI process and an escaping error here would abort
    # route registration entirely.
    logger.error(
        "[CivBro] Rust core loaded but the database at %s could not be opened: %s",
        _resolve_db_path(),
        e,
        exc_info=True,
    )


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
