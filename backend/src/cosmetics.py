from __future__ import annotations

import json
import logging
from typing import Any

from .client import RUST_AVAILABLE

logger = logging.getLogger("civbro.api")


def extract_cosmetic(raw: dict) -> dict | None:
    if RUST_AVAILABLE:
        try:
            import civbro_core
            result = json.loads(civbro_core.build_extras(json.dumps(raw)))
            return result.get("cosmetic")
        except Exception as e:
            logger.debug(f"Rust cosmetic extraction failed: {e}")
    return _py_extract_cosmetic(raw)


def extract_creator_cosmetics(item: dict) -> tuple[str, str, dict | None]:
    if RUST_AVAILABLE:
        try:
            import civbro_core
            result = json.loads(civbro_core.build_extras(json.dumps(item)))
            return (
                result.get("avatarDeco") or "",
                result.get("badge") or "",
                result.get("nameplate"),
            )
        except Exception as e:
            logger.debug(f"Rust creator cosmetics extraction failed: {e}")
    return _py_extract_creator_cosmetics(item)


# ---- Pure-Python fallbacks ----
import re
from .config import CDN_URL, CIVITAI_IMG_BUCKET

_GRADIENT_RE = re.compile(r"^(?:repeating-)?(?:linear|radial|conic)-gradient\([#%.,()\-\s\w]*\)$")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def _sanitize_css_frame(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    v = value.strip().rstrip(";").strip()
    if not v or "url(" in v.lower() or "<" in v or "@" in v:
        return ""
    return v if _GRADIENT_RE.match(v) else ""


def _cosmetic_img_url(raw: str) -> str:
    if not raw:
        return ""
    if raw.startswith("http"):
        return raw
    return f"{CDN_URL}/{CIVITAI_IMG_BUCKET}/{raw}/original=true/deco.png"


def _hex_ok(c: Any) -> bool:
    return isinstance(c, str) and bool(_HEX_RE.match(c.strip()))


def _py_extract_cosmetic(raw: dict) -> dict | None:
    cos = raw.get("cosmetic")
    if isinstance(cos, dict):
        data = cos.get("data") if isinstance(cos.get("data"), dict) else cos
        css = _sanitize_css_frame(data.get("cssFrame"))
        if css:
            return {"cssFrame": css, "glow": bool(data.get("glow"))}
    user = (
        raw.get("creator") if isinstance(raw.get("creator"), dict)
        else (raw.get("user") if isinstance(raw.get("user"), dict) else {})
    )
    cosmetics = user.get("cosmetics") or raw.get("cosmetics") or []
    for c in cosmetics:
        if not isinstance(c, dict):
            continue
        c_item = c.get("cosmetic") if isinstance(c.get("cosmetic"), dict) else c
        if not isinstance(c_item, dict):
            continue
        if c_item.get("type") == "ContentDecoration":
            data = c_item.get("data") if isinstance(c_item.get("data"), dict) else c_item
            css = _sanitize_css_frame(data.get("cssFrame"))
            if css:
                return {"cssFrame": css, "glow": bool(data.get("glow"))}
    return None


def _extract_nameplate(data: dict) -> dict | None:
    if not isinstance(data, dict):
        return None
    grad = data.get("gradient") if isinstance(data.get("gradient"), dict) else None
    if grad and _hex_ok(grad.get("from")) and _hex_ok(grad.get("to")):
        deg = grad.get("deg")
        deg = int(deg) if isinstance(deg, (int, float)) else 90
        return {"gradient": f"linear-gradient({deg}deg, {grad['from'].strip()}, {grad['to'].strip()})"}
    color = data.get("color")
    if _hex_ok(color):
        return {"color": color.strip()}
    return None


def _py_extract_creator_cosmetics(item: dict) -> tuple[str, str, dict | None]:
    user = (
        item.get("creator") if isinstance(item.get("creator"), dict)
        else (item.get("user") if isinstance(item.get("user"), dict) else {})
    )
    cosmetics = user.get("cosmetics") or item.get("cosmetics") or []
    deco = _cosmetic_img_url(user.get("avatarDeco") or user.get("profileDecoration") or "")
    badge = _cosmetic_img_url(user.get("badge") or "")
    nameplate = user.get("nameplate") if isinstance(user.get("nameplate"), dict) else None
    for c in cosmetics:
        if not isinstance(c, dict):
            continue
        cos = c.get("cosmetic") if isinstance(c.get("cosmetic"), dict) else c
        if not isinstance(cos, dict):
            continue
        ctype = cos.get("type")
        data = cos.get("data") if isinstance(cos.get("data"), dict) else cos
        url = data.get("url", "")
        if ctype == "ProfileDecoration" and not deco:
            deco = _cosmetic_img_url(url)
        elif ctype == "Badge" and not badge:
            badge = _cosmetic_img_url(url)
        elif ctype == "NamePlate" and nameplate is None:
            nameplate = _extract_nameplate(data)
    return deco, badge, nameplate
