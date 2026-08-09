from __future__ import annotations

"""Backward-compatible re-exports from the HTTP and DB adapters.

All existing imports from .client continue to work unchanged.
New code should import from .http_adapter or .db_adapter directly.
"""

from .db_adapter import (
    DB,
    RUST_AVAILABLE,
    _resolve_db_path,
    cleanup_orphan_parts,
    get_civitai_key,
)
from .http_adapter import (
    ensure_warmup_started as _ensure_warmup_started,
    get_http_client,
    get_raw_http_client,
    http_get_with_retry,
)

HTTP_CLIENT = get_raw_http_client()


def ensure_warmup_started() -> None:
    _ensure_warmup_started(get_civitai_key)
