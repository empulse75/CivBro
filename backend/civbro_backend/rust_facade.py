from __future__ import annotations

import json

from .client import RUST_AVAILABLE


def _ensure_rust():
    if not RUST_AVAILABLE:
        raise RuntimeError("Rust core not available — cannot perform this operation")
    import civbro_core
    return civbro_core


# ── parsing ──────────────────────────────────────────────────────────────────

def parse_trpc_model(raw: dict) -> dict:
    core = _ensure_rust()
    items = json.loads(core.parse_models(json.dumps([raw]), "trpc"))
    return items[0] if items else {}


def parse_model_slim(raw: dict) -> dict:
    core = _ensure_rust()
    items = json.loads(core.parse_models(json.dumps([raw]), "slim"))
    return items[0] if items else {}


def parse_rest_model(raw: dict) -> dict:
    core = _ensure_rust()
    items = json.loads(core.parse_models(json.dumps([raw]), "rich"))
    return items[0] if items else {}


# ── cosmetics ────────────────────────────────────────────────────────────────

def extract_cosmetic(raw: dict) -> dict | None:
    core = _ensure_rust()
    result = json.loads(core.build_extras(json.dumps(raw)))
    return result.get("cosmetic")


def extract_creator_cosmetics(raw: dict) -> tuple[str | None, str | None, dict | None]:
    if not RUST_AVAILABLE:
        return None, None, None
    import civbro_core
    result = json.loads(civbro_core.build_extras(json.dumps(raw)))
    return (
        result.get("avatarDeco"),
        result.get("badge"),
        result.get("nameplate"),
    )


# ── utils ────────────────────────────────────────────────────────────────────

def subdir_for_type(file_type: str, name: str = "", model_type: str = "") -> str:
    core = _ensure_rust()
    return core.file_subdir(file_type, name, model_type)


def optimize_image_url(url: str, width: int = 450, image_type: str = "image") -> str:
    if not RUST_AVAILABLE:
        return url
    import civbro_core
    return civbro_core.optimize_cdn_url(url, width, image_type)


# ── trpc_extras pass-through ─────────────────────────────────────────────────

def extract_trpc_extras(item: dict) -> dict:
    core = _ensure_rust()
    return json.loads(core.build_extras(json.dumps(item)))


def parse_trpc_items(resp_json: dict) -> list[dict]:
    core = _ensure_rust()
    return json.loads(core.parse_trpc_response(json.dumps(resp_json)))


def apply_extras_to_slim(model: dict, extras: dict) -> None:
    core = _ensure_rust()
    merged = json.loads(core.merge_extras_into_slim(json.dumps(model), json.dumps(extras)))
    model.clear()
    model.update(merged)


def make_slim_from_trpc(extras: dict, model_id: int) -> dict:
    core = _ensure_rust()
    return json.loads(core.build_slim_from_extras(json.dumps(extras), model_id))


def parse_dependencies(trpc: dict) -> list[dict]:
    core = _ensure_rust()
    return json.loads(core.parse_deps(json.dumps(trpc)))
