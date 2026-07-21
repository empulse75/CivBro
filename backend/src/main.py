from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

logger = logging.getLogger("civbro.api")

CIVITAI_REST_API = "https://civitai.com/api/v1"
CIVITAI_TRPC_API = "https://civitai.com/api/trpc"
CIVITAI_RED_API = "https://civitai.red/api/v1"
CDN_URL = "https://image.civitai.com"

MODELS_ROOT = os.environ.get("SD_WEBUI_MODELS_DIR") or "/home/gonzo/webui/sd-webui-forge-classic/models"


def _subdir_for_type(t: str, name: str = "", model_type: str = "") -> str:
    """Map a file's type/name to its WebUI model subdirectory (mirrors the frontend)."""
    s = (t or "").lower()
    if "vae" in s:
        return "VAE"
    if "encoder" in s or s == "te":
        return "text_encoder"
    if "lora" in s or "locon" in s or "dora" in s:
        return "Lora"
    if "embed" in s or "textualinversion" in s:
        return "embeddings"
    if "controlnet" in s:
        return "ControlNet"
    if "upscal" in s or "esrgan" in s:
        return "ESRGAN"
    n = (name or "").lower()
    if re.search(r"(^|[_\-.])vae([_\-.]|$)", n):
        return "VAE"
    if re.search(r"text.?encoder|(^|[_\-.])te([_\-.]|$)|(^|[_\-.])txt([_\-.]|$)|t5xxl|clip[_\-]?[lg]", n):
        return "text_encoder"
    mt = (model_type or "").lower()
    dir_map = {
        "checkpoint": "Stable-diffusion", "lora": "Lora", "locon": "Lora",
        "textualinversion": "embeddings", "hypernetwork": "hypernetworks",
        "vae": "VAE", "controlnet": "ControlNet", "upscaler": "ESRGAN",
    }
    return dir_map.get(mt, "Stable-diffusion")


def _cleanup_orphan_parts() -> int:
    """Delete leftover *.part files (from interrupted downloads). Any .part is an
    orphan because downloads don't resume across restarts."""
    removed = 0
    try:
        if RUST_AVAILABLE and hasattr(civbro_core, "clean_orphan_parts"):
            removed = civbro_core.clean_orphan_parts(MODELS_ROOT)
        else:
            from pathlib import Path as _P
            for part in _P(MODELS_ROOT).rglob("*.part"):
                try:
                    part.unlink()
                    removed += 1
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"orphan .part cleanup failed: {e}")
    if removed:
        logger.info(f"[CivBro] cleaned {removed} orphan .part file(s)")
    return removed


HTTP_CLIENT: httpx.AsyncClient | None = None
RUST_AVAILABLE = False
DB = None

try:
    import civbro_core

    RUST_AVAILABLE = True
    DB = civbro_core.Database()
    logger.info("[CivBro] Rust core loaded successfully")
except ImportError:
    logger.warning("[CivBro] Rust core not available, using pure Python fallbacks")
    RUST_AVAILABLE = False

EXTENSION_DIR = Path(__file__).parent.parent.resolve()
CACHE_DIR = EXTENSION_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CIVITAI_NSFW = "None"
DEFAULT_LIMIT = 20
DEFAULT_QUERY = ""


def get_http_client() -> httpx.AsyncClient:
    global HTTP_CLIENT
    if HTTP_CLIENT is None:
        kwargs = dict(
            # Short connect timeout (fail fast on dead links) but a generous read
            # timeout because civitai.red streams its response body very slowly.
            timeout=httpx.Timeout(connect=8.0, read=45.0, write=15.0, pool=45.0),
            # Keep upstream connections warm for 5 minutes so a reused (already
            # TLS-negotiated) socket is available for the next search instead of
            # paying the multi-second cold-connect penalty every time.
            limits=httpx.Limits(
                max_connections=40,
                max_keepalive_connections=20,
                keepalive_expiry=300.0,
            ),
            headers={
                "User-Agent": "CivBro/1.0",
                "Accept": "application/json",
            },
        )
        # HTTP/2 multiplexes the parallel Civitai calls (REST + tRPC gather,
        # version-detail enrichment) over a single connection, cutting handshake
        # overhead. Falls back to HTTP/1.1 if the optional `h2` dep is missing.
        try:
            HTTP_CLIENT = httpx.AsyncClient(http2=True, **kwargs)
        except ImportError:
            logger.warning("[CivBro] h2 not installed — using HTTP/1.1")
            HTTP_CLIENT = httpx.AsyncClient(**kwargs)
    return HTTP_CLIENT


async def _http_get_with_retry(url: str, **kw: Any) -> httpx.Response:
    """httpx GET with one automatic retry on HTTP/2 stream errors (ConnectionTerminated /
    RemoteProtocolError) — civitai.red sometimes resets idle h2 streams. Falls back
    to a fresh client on retry to avoid reusing a stale connection."""
    client = get_http_client()
    try:
        return await client.get(url, **kw)
    except (httpx.RemoteProtocolError, httpx.ConnectError) as e:
        msg = str(e)
        if "ConnectionTerminated" in msg or "RemoteProtocolError" in msg:
            logger.debug(f"retrying after h2 stream error: {msg}")
            # Fresh client to force a new connection
            try:
                async with httpx.AsyncClient(timeout=client.timeout, limits=client.limits, headers=client.headers) as c2:
                    return await c2.get(url, **kw)
            except Exception:
                raise e
        raise


# ---------------------------------------------------------------------------
# Cosmetics (creator-equipped card "content decorations")
#
# Civitai renders a multi-colour gradient border + glow around some model cards.
# It is NOT per-base-model: it's a cosmetic the creator equipped, delivered only
# via the tRPC `model.getAll` endpoint as `cosmetic.data.cssFrame` (a CSS
# gradient) + `cosmetic.data.glow`. REST/red omit it. We fetch a cosmetic map
# from tRPC (with the required client headers) and merge it into search results.
# ---------------------------------------------------------------------------
_GRADIENT_RE = re.compile(
    r"^(?:repeating-)?(?:linear|radial|conic)-gradient\([#%.,()\-\s\w]*\)$"
)


def _sanitize_css_frame(value: Any) -> str:
    """Return a safe CSS gradient string (for an inline style attr) or ''.
    Rejects anything that isn't a plain gradient (blocks url()/injection)."""
    if not isinstance(value, str):
        return ""
    v = value.strip().rstrip(";").strip()
    if not v or "url(" in v.lower() or "<" in v or "@" in v:
        return ""
    return v if _GRADIENT_RE.match(v) else ""


def _extract_cosmetic(raw: dict) -> dict | None:
    cos = raw.get("cosmetic")
    if isinstance(cos, dict):
        data = cos.get("data") if isinstance(cos.get("data"), dict) else cos
        css = _sanitize_css_frame(data.get("cssFrame"))
        if css:
            return {"cssFrame": css, "glow": bool(data.get("glow"))}

    user = raw.get("creator") if isinstance(raw.get("creator"), dict) else (raw.get("user") if isinstance(raw.get("user"), dict) else {})
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


# Civitai stores cosmetic images as bare UUIDs; turn them into full CDN URLs.
_CIVITAI_IMG_BUCKET = "xG1nkqKTMzGDvpLrqFT7WA"


def _cosmetic_img_url(raw: str) -> str:
    if not raw:
        return ""
    if raw.startswith("http"):
        return raw
    # original=true preserves transparency/animation of the decoration/badge PNG
    return f"{CDN_URL}/{_CIVITAI_IMG_BUCKET}/{raw}/original=true/deco.png"


_HEX_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def _hex_ok(c: Any) -> bool:
    return isinstance(c, str) and bool(_HEX_RE.match(c.strip()))


def _extract_nameplate(data: dict) -> dict | None:
    """Turn a NamePlate cosmetic's data into a safe css payload for the username.
    Gradient variant -> {gradient: 'linear-gradient(..)'}; solid -> {color: '#hex'}."""
    if not isinstance(data, dict):
        return None
    variant = data.get("variant")
    grad = data.get("gradient") if isinstance(data.get("gradient"), dict) else None
    if grad and _hex_ok(grad.get("from")) and _hex_ok(grad.get("to")):
        deg = grad.get("deg")
        deg = int(deg) if isinstance(deg, (int, float)) else 90
        return {"gradient": f"linear-gradient({deg}deg, {grad['from'].strip()}, {grad['to'].strip()})"}
    color = data.get("color")
    if _hex_ok(color):
        return {"color": color.strip()}
    return None


def _extract_creator_cosmetics(item: dict) -> tuple[str, str, dict | None]:
    """Return (avatarDecorationUrl, badgeUrl, nameplate) from a model item's user/creator cosmetics."""
    user = item.get("creator") if isinstance(item.get("creator"), dict) else (item.get("user") if isinstance(item.get("user"), dict) else {})
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


def _extract_trpc_extras(item: dict) -> dict:
    """Build the lazy 'extras' payload for one tRPC model item: the cosmetic
    border, the base-model family list, the creator's avatar decoration + badge +
    nameplate colour, and a buzz flag. All tRPC-only (REST/red omit it)."""
    extras: dict[str, Any] = {}
    cos = _extract_cosmetic(item)
    if cos:
        extras["cosmetic"] = cos
    base_models = item.get("baseModels")
    if isinstance(base_models, list) and base_models:
        extras["baseModels"] = [str(b) for b in base_models if b]
    deco, badge, nameplate = _extract_creator_cosmetics(item)
    if deco:
        extras["avatarDeco"] = deco
    if badge:
        extras["badge"] = badge
    if nameplate:
        extras["nameplate"] = nameplate
    # Availability / recency for the Early-Access and Updated pills.
    avail = item.get("availability")
    if avail:
        extras["availability"] = avail
    if item.get("earlyAccessDeadline"):
        extras["earlyAccessDeadline"] = item.get("earlyAccessDeadline")
    if item.get("publishedAt"):
        extras["publishedAt"] = item.get("publishedAt")
    if item.get("createdAt"):
        extras["createdAt"] = item.get("createdAt")
    # buzz flag (best-effort; tRPC getAll rarely includes per-version buzz)
    versions = item.get("modelVersions")
    if isinstance(versions, list) and any(isinstance(v, dict) and v.get("requiresBuzz") for v in versions):
        extras["hasBuzz"] = True
    if item.get("mode"):
        extras["mode"] = item.get("mode")
    # Core fields needed to construct a slim card model for EA models not in REST/red
    extras["name"] = item.get("name", "")
    extras["modelType"] = item.get("modelType") or item.get("type", "")
    extras["nsfw"] = item.get("nsfw", False)
    extras["stats"] = item.get("stats", {})
    creator = item.get("creator") if isinstance(item.get("creator"), dict) else {}
    extras["creator"] = {
        "username": creator.get("username", ""),
        "image": creator.get("image", ""),
    }
    mvs = item.get("modelVersions", [])
    if not isinstance(mvs, list):
        mvs = []
    imgs = (mvs[0].get("images", []) if mvs else []) or item.get("images", []) or []
    if imgs:
        im = dict(imgs[0]) if isinstance(imgs[0], dict) else {}
        im["url"] = optimize_image_url(im.get("url", ""), 300, im.get("type", "image"))
        extras["images"] = [im]
    return extras


def _apply_extras_to_slim(model: dict, extras: dict) -> None:
    """Patch a slim-parsed model dict with tRPC extras fields in-place.
    Only sets fields that are not already present (REST/red response may have
    more recent version-level dates)."""
    if extras.get("availability"):
        model["availability"] = extras["availability"]
    if extras.get("earlyAccessDeadline"):
        model["earlyAccessDeadline"] = extras["earlyAccessDeadline"]
    if extras.get("publishedAt") and not model.get("publishedAt"):
        model["publishedAt"] = extras["publishedAt"]
    if extras.get("createdAt") and not model.get("createdAt"):
        model["createdAt"] = extras["createdAt"]
    if extras.get("hasBuzz"):
        model["hasBuzz"] = True


def _make_slim_from_trpc(extras: dict, model_id: int) -> dict:
    """Build a minimal slim model dict from tRPC extras (for EA models not in REST/red)."""
    return {
        "id": model_id,
        "name": extras.get("name", str(model_id)),
        "modelType": extras.get("modelType", "Checkpoint"),
        "type": extras.get("modelType", "Checkpoint"),
        "nsfw": extras.get("nsfw", False),
        "baseModel": "",
        "tags": [],
        "images": extras.get("images", []),
        "poster": extras.get("poster", ""),
        "cosmetic": extras.get("cosmetic"),
        "availability": extras.get("availability", "EarlyAccess"),
        "earlyAccessDeadline": extras.get("earlyAccessDeadline"),
        "publishedAt": extras.get("publishedAt"),
        "createdAt": extras.get("createdAt"),
        "hasBuzz": extras.get("hasBuzz", False),
        "stats": extras.get("stats", {}),
        "creator": extras.get("creator", {"username": "", "image": ""}),
        "baseModels": extras.get("baseModels", []),
        "avatarDeco": extras.get("avatarDeco"),
        "badge": extras.get("badge"),
        "nameplate": extras.get("nameplate"),
        "_fromTrpcExtras": True,
    }


def _trpc_client_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "x-client": "web",
        "x-client-version": "5.0.2014",
        "x-client-date": str(int(time.time() * 1000)),
        "Referer": "https://civitai.com/models",
    }


def _parse_trpc_items(resp_json: dict) -> list[dict]:
    """Extract model items from a tRPC model.getAll response. Handles both the
    old nested-dict format (data.json.items) and the superjson format (data is a
    serialised key/value index array). Returns raw values (no recursive resolution)."""
    try:
        result = resp_json.get("result") or {}
        data = result.get("data")
        if data is None:
            return []
        if isinstance(data, dict):
            return (data.get("json") or {}).get("items", []) or []
        if isinstance(data, str):
            arr = json.loads(data)
            if not isinstance(arr, list) or len(arr) < 3:
                return []
            meta = arr[0] if isinstance(arr[0], dict) else {}
            tpl = arr[2] if isinstance(arr[2], dict) else {}
            if not tpl:
                return []
            stride = max((v for v in tpl.values() if isinstance(v, int)), default=0) + 1
            items = []
            for model_i in range(meta.get("items", 1)):
                base = 3 + model_i * stride
                obj = {}
                for key, vi in tpl.items():
                    if isinstance(vi, int):
                        idx = vi if model_i == 0 else base + vi
                        if 0 <= idx < len(arr):
                            obj[key] = arr[idx]
                if obj.get("id"):
                    # Resolve nested fields: user (for avatarDeco/badge/nameplate)
                    # and cosmetic.data (for card border cssFrame)
                    _resolve_user_field(obj, arr)
                    _resolve_cosmetic_field(obj, arr)
                    items.append(obj)
            return items
    except Exception:
        pass
    return []


def _resolve_cosmetic_field(obj: dict, arr: list) -> None:
    """Resolve the 'cosmetic.data' field in-place from the superjson array."""
    try:
        cos = obj.get("cosmetic")
        if not isinstance(cos, dict):
            return
        data_idx = cos.get("data")
        if isinstance(data_idx, int) and 0 <= data_idx < len(arr):
            data_tpl = arr[data_idx]
            if isinstance(data_tpl, dict) and all(isinstance(v, int) for v in data_tpl.values()):
                cos["data"] = {k: arr[vi] for k, vi in data_tpl.items()
                               if isinstance(vi, int) and 0 <= vi < len(arr)}
    except Exception:
        pass


def _resolve_user_field(obj: dict, arr: list) -> None:
    """Resolve the 'user' object in-place from the superjson array.
    Resolves all int references recursively up to depth 5 to handle
    the user→cosmetics→wrapper→cosmetic→data chain."""
    def _resolve(val, depth=0):
        if depth > 5:
            return val
        if isinstance(val, int) and 0 <= val < len(arr):
            return _resolve(arr[val], depth + 1)
        if isinstance(val, list):
            return [_resolve(v, depth + 1) for v in val]
        if isinstance(val, dict):
            vs = list(val.values())
            if vs and all(isinstance(v, int) for v in vs):
                return {k: _resolve(arr[vi], depth + 1) for k, vi in val.items()
                        if isinstance(vi, int) and 0 <= vi < len(arr)}
            return val
        return val
    try:
        user_raw = obj.get("user")
        if isinstance(user_raw, dict):
            obj["user"] = _resolve(user_raw)
    except Exception:
        pass


_COSMETIC_CACHE: dict[str, tuple[float, dict]] = {}
_COSMETIC_TTL = 3600.0  # 1 hour


async def _fetch_trpc_extras(
    sort: str, period: str, model_type: Any, query: str, nsfw: bool = False
) -> dict:
    """Return {modelId: {cosmetic, baseModels, avatarDeco, badge, hasBuzz}} for the
    given filter combo via tRPC. This is the lazy, non-blocking enrichment for the
    grid (the grid itself renders from the fast slim REST/red path). Cached for an
    hour, keyed by filter (not cursor), so every page reuses it. When nsfw, browses
    at level 31 and authenticates with the account key so NSFW models are included.
    Best-effort: {} on any failure."""
    key = json.dumps([sort, period, model_type, query, nsfw], sort_keys=True, default=str)
    hit = _COSMETIC_CACHE.get(key)
    if hit and time.time() - hit[0] < _COSMETIC_TTL:
        return hit[1]

    inp: dict[str, Any] = {
        "json": {
            "browsingLevel": 127 if nsfw else 1,
            "sort": sort or "Most Downloaded",
            "period": period or "AllTime",
            "periodMode": "published",
            "pending": False,
            "disablePoi": True,
            "disableMinor": None,
            "excludedTagIds": [5161, 5162, 5188, 5249, 130818, 130820, 133182, 130401, 110980],
            "direction": "forward",
            "limit": 100,
        },
        "meta": {"values": {"disableMinor": ["undefined"]}, "v": 1},
    }
    if model_type:
        inp["json"]["types"] = [model_type] if isinstance(model_type, str) else list(model_type)
    if query:
        inp["json"]["query"] = query

    headers = _trpc_client_headers()
    if DB is not None:
        try:
            api_key = DB.get_setting("civitaiRedApiKey") or ""
            if api_key:
                headers["Authorization"] = "Bearer " + api_key
        except Exception:
            pass

    out: dict = {}
    try:
        client = get_http_client()
        cursor = None
        for _ in range(20):  # superjson = 1 model/page, fetch up to 20
            req_inp = {k: dict(v) if isinstance(v, dict) else v for k, v in inp.items()}
            if cursor is not None:
                req_inp["json"]["cursor"] = cursor
            resp = await _http_get_with_retry(
                f"{CIVITAI_TRPC_API}/model.getAll",
                params={"input": json.dumps(req_inp, separators=(",", ":"))},
                headers=headers,
                timeout=15.0,
            )
            if resp.status_code != 200:
                break
            items = _parse_trpc_items(resp.json())
            if not items:
                break
            for it in items:
                mid = it.get("id")
                if mid is None:
                    continue
                extras = _extract_trpc_extras(it)
                if extras:
                    out[str(mid)] = extras
            # Get next cursor from superjson meta
            try:
                raw = json.loads(((resp.json().get("result") or {}).get("data") or ""))
                if isinstance(raw, list) and raw:
                    meta = raw[0] if isinstance(raw[0], dict) else {}
                    nxt = meta.get("nextCursor")
                    cursor = nxt if nxt and nxt != -1 else None
                else:
                    cursor = None
            except Exception:
                cursor = None
            if cursor is None:
                break
    except Exception as e:
        logger.debug(f"trpc extras fetch failed: {e}")

    _COSMETIC_CACHE[key] = (time.time(), out)
    return out


_EXTRAS_ID_CACHE: dict[int, tuple[float, dict]] = {}
_EXTRAS_ID_TTL = 3600.0


async def _fetch_extras_by_ids(ids: list[int]) -> dict:
    """Return {modelId: extras} for the exact grid model ids via tRPC model.getById
    batching. Per-id cached for 1 hour."""
    now = time.time()
    out: dict = {}
    misses: list[int] = []
    for i in ids:
        hit = _EXTRAS_ID_CACHE.get(i)
        if hit and now - hit[0] < _EXTRAS_ID_TTL:
            if hit[1]:
                out[str(i)] = hit[1]
        else:
            misses.append(i)
    if not misses:
        return out

    headers = _trpc_client_headers()
    client = get_http_client()

    for b_idx in range(0, len(misses), 10):
        chunk = misses[b_idx : b_idx + 10]
        endpoint_str = ",".join(["model.getById"] * len(chunk))
        url = f"{CIVITAI_TRPC_API}/{endpoint_str}"
        inp = {str(idx): {"json": {"id": mid, "browsingLevel": 127}} for idx, mid in enumerate(chunk)}
        try:
            resp = await client.get(
                url,
                params={"batch": "1", "input": json.dumps(inp, separators=(",", ":"))},
                headers=headers,
                timeout=15.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                if not isinstance(data, list):
                    data = [data]
                for item in data:
                    res = item.get("result", {}).get("data", {})
                    json_data = res.get("json") if isinstance(res, dict) else {}
                    if not isinstance(json_data, dict):
                        continue
                    mid = json_data.get("id")
                    if not mid:
                        continue
                    extras = _extract_trpc_extras(json_data)
                    _EXTRAS_ID_CACHE[mid] = (now, extras)
                    if extras:
                        out[str(mid)] = extras
            else:
                for mid in chunk:
                    _EXTRAS_ID_CACHE[mid] = (now, {})
        except Exception as e:
            logger.debug(f"batch tRPC extras fetch failed: {e}")
            for mid in chunk:
                _EXTRAS_ID_CACHE[mid] = (now, {})

    return out


# ---------------------------------------------------------------------------
# Connection warm-up
#
# The browser-side diagnosis showed the first request to each civitai upstream
# pays an 8-62s cold-connection penalty (TLS + upstream warmup), while a reused
# warm connection returns in 0.2-3s. Keep the pool warm with a lightweight
# background pinger so real user searches always land on a hot connection.
# The loop is started lazily from the first request handler so it runs on
# uvicorn's event loop (and therefore shares the one AsyncClient instance).
# ---------------------------------------------------------------------------
_WARMUP_STARTED = False
_WARMUP_INTERVAL = 45.0


async def _warm_connections() -> None:
    client = get_http_client()

    async def _ping(url: str, params: dict) -> None:
        try:
            await _http_get_with_retry(url, params=params, timeout=httpx.Timeout(connect=8.0, read=20.0, write=10.0, pool=20.0))
        except Exception:
            pass

    targets: list[tuple[str, dict]] = [
        (f"{CIVITAI_REST_API}/models", {"limit": 1}),
    ]
    api_key = ""
    if DB is not None:
        try:
            api_key = DB.get_setting("civitaiRedApiKey") or ""
        except Exception:
            api_key = ""
    if api_key:
        targets.append((f"{CIVITAI_RED_API}/models", {"limit": 1, "token": api_key}))

    await asyncio.gather(*(_ping(u, p) for u, p in targets))


async def _warmup_loop() -> None:
    while True:
        await _warm_connections()
        await asyncio.sleep(_WARMUP_INTERVAL)


def _ensure_warmup_started() -> None:
    """Start the background warm-up loop once, on the currently-running (uvicorn)
    event loop. Safe to call from any request handler."""
    global _WARMUP_STARTED
    if _WARMUP_STARTED:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _WARMUP_STARTED = True
    loop.create_task(_warmup_loop())
    logger.info("[CivBro] connection warm-up loop started")


# ---------------------------------------------------------------------------
# Search response cache
#
# civitai.red throttles its response body server-side (3-17s to deliver even a
# 15KB payload, even over a warm reused connection), so repeat navigation,
# pagination and filter re-toggles would each re-pay that cost. Cache successful
# non-empty slim /models responses for a short TTL, keyed by the exact query
# params. This keeps the user's chosen source intact (incl. NSFW / all files via
# civitai.red) while making repeat views effectively instant, and it also masks
# the source's intermittent empty responses.
# ---------------------------------------------------------------------------
_SEARCH_CACHE: dict[str, tuple[float, dict]] = {}
_SEARCH_CACHE_TTL = 604800.0  # 1 week; in-memory only, so it also clears on WebUI restart
_SEARCH_CACHE_MAX = 1024


def _search_cache_key(**kw: Any) -> str:
    return json.dumps(kw, sort_keys=True, default=str)


def _search_cache_get(key: str) -> dict | None:
    hit = _SEARCH_CACHE.get(key)
    if not hit:
        return None
    ts, data = hit
    if time.time() - ts > _SEARCH_CACHE_TTL:
        _SEARCH_CACHE.pop(key, None)
        return None
    items = data.get("items", [])
    if items and any(isinstance(it, dict) and not it.get("baseModels") for it in items[:10]):
        _SEARCH_CACHE.pop(key, None)
        return None
    return data


def _search_cache_put(key: str, data: dict) -> None:
    if not data or not data.get("items"):
        return
    if len(_SEARCH_CACHE) >= _SEARCH_CACHE_MAX:
        oldest = min(_SEARCH_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _SEARCH_CACHE.pop(oldest, None)
    _SEARCH_CACHE[key] = (time.time(), data)


def optimize_image_url(url: str, width: int = 450, image_type: str = "image") -> str:
    if not url or CDN_URL not in url:
        return url
    if image_type == "video":
        # Serve a width-limited, transcoded (faststart, web-optimized) clip. The
        # raw `original=true` file often isn't faststart (moov atom at the end),
        # so the browser would download the whole thing before showing a frame —
        # that's the "grey/blank" video box. The transcoded transform plays and
        # shows its first frame immediately.
        vt = f"transcode=true,width={width or 450},optimized=true"
        if "/original=true/" in url:
            return url.replace("/original=true/", f"/{vt}/")
        m = re.search(r"/width=\d+[^/]*/", url)
        if m:
            return url[:m.start()] + f"/{vt}/" + url[m.end():]
        return url
    url = url.replace("/original=true/", "/")
    if "/width=" not in url:
        return url.replace(CDN_URL, f"{CDN_URL}/width={width},format=webp")
    return url


def _parse_trpc_model(raw: dict) -> dict:
    images = []
    for mv in raw.get("modelVersions", []):
        for img in mv.get("images", []):
            img_url = img.get("url", "")
            img["url"] = optimize_image_url(img_url, 450, img.get("type", "image"))
            images.append(img)

    tags_list = raw.get("tags", [])
    if isinstance(tags_list, list) and tags_list:
        if isinstance(tags_list[0], dict):
            tags = [t.get("name", "") for t in tags_list]
        else:
            tags = tags_list
    else:
        tags = []

    model_versions = []
    for mv in raw.get("modelVersions", []):
        version_images = []
        for img in mv.get("images", []):
            img_url = img.get("url", "")
            img["url"] = optimize_image_url(img_url, 450, img.get("type", "image"))
            version_images.append(img)
        model_versions.append({
            "id": mv.get("id"),
            "name": mv.get("name"),
            "baseModel": mv.get("baseModel"),
            "trainedWords": mv.get("trainedWords", []),
            "images": version_images,
            "downloadUrl": mv.get("downloadUrl", ""),
            "files": mv.get("files", []),
            "createdAt": mv.get("createdAt"),
            "stats": mv.get("stats", {}),
        })

    stats = raw.get("stats", {})
    deco, badge, nameplate = _extract_creator_cosmetics(raw)
    raw_base_models = raw.get("baseModels")
    mvs = raw.get("modelVersions", []) or []
    base_model = mvs[0].get("baseModel", "") if mvs else raw.get("baseModel", "")
    if isinstance(raw_base_models, list) and raw_base_models:
        base_models = [str(b) for b in raw_base_models if b]
    else:
        base_models = [base_model] if base_model else []

    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "description": raw.get("description", ""),
        "modelType": raw.get("modelType") or raw.get("type"),
        "baseModel": base_model,
        "baseModels": base_models,
        "nsfw": raw.get("nsfw", False),
        "tags": tags,
        "images": images,
        "modelVersions": model_versions,
        "cosmetic": _extract_cosmetic(raw),
        "avatarDeco": deco or None,
        "badge": badge or None,
        "nameplate": nameplate or None,
        "stats": {
            "downloadCount": stats.get("downloadCount", 0),
            "favoriteCount": stats.get("favoriteCount", 0),
            "commentCount": stats.get("commentCount", 0),
            "ratingCount": stats.get("ratingCount", 0),
            "rating": stats.get("rating", 0),
            "thumbsUpCount": stats.get("thumbsUpCount", 0),
            "thumbsDownCount": stats.get("thumbsDownCount", 0),
        },
        "creator": {
            "username": raw.get("creator", {}).get("username", "")
            if isinstance(raw.get("creator"), dict)
            else "",
            "image": raw.get("creator", {}).get("image", "")
            if isinstance(raw.get("creator"), dict)
            else "",
        },
        "createdAt": raw.get("createdAt"),
        "updatedAt": raw.get("updatedAt"),
        "lastVersionAt": raw.get("lastVersionAt"),
    }


def _parse_model_slim(raw: dict) -> dict:
    """Lightweight model shape for the search grid: only the first preview image
    (at card width) and card stats. Avoids shipping every version's full image/file
    list (which made the /models response multiple MB). Full data is fetched on
    demand when the detail popup opens."""
    mvs = raw.get("modelVersions", []) or []
    imgs = (mvs[0].get("images", []) if mvs else []) or raw.get("images", []) or []
    images = []
    poster = ""
    if imgs:
        # Keep the model's real first preview (video covers stay videos).
        im = dict(imgs[0])
        im["url"] = optimize_image_url(im.get("url", ""), 300, im.get("type", "image"))
        images = [im]
        # If the cover is a video, also emit a still poster (the first non-video
        # image) so the card shows a real first-frame placeholder immediately,
        # before the clip loads — matching Civitai. Zero extra latency (the images
        # are already in this response).
        if (imgs[0].get("type") or "image") == "video":
            for cand in imgs:
                if (cand.get("type") or "image") != "video" and cand.get("url"):
                    poster = optimize_image_url(cand.get("url", ""), 300, "image")
                    break

    tags_list = raw.get("tags", [])
    if isinstance(tags_list, list) and tags_list and isinstance(tags_list[0], dict):
        tags = [t.get("name", "") for t in tags_list]
    elif isinstance(tags_list, list):
        tags = tags_list
    else:
        tags = []

    stats = raw.get("stats", {}) or {}
    base_model = mvs[0].get("baseModel", "") if mvs else raw.get("baseModel", "")
    raw_base_models = raw.get("baseModels")
    if isinstance(raw_base_models, list) and raw_base_models:
        base_models = [str(b) for b in raw_base_models if b]
    else:
        base_models = [base_model] if base_model else []

    creator = raw.get("creator") if isinstance(raw.get("creator"), dict) else {}
    deco, badge, nameplate = _extract_creator_cosmetics(raw)

    # Early-Access / Updated pill data directly from the search response
    # (also available via tRPC extras, but the REST/red responses often have them too
    #  and including them here means the pills render immediately, not after the extras load)
    ea_deadline = raw.get("earlyAccessDeadline") or raw.get("earlyAccessEndsAt")
    if not ea_deadline:
        ea_cfg = raw.get("earlyAccessConfig")
        if isinstance(ea_cfg, dict):
            ea_deadline = ea_cfg.get("timeframe") or ea_cfg.get("deadline")
    # The REST/red APIs may not include model-level publishedAt/createdAt, but the
    # first modelVersion often has publishedAt. Use it as a fallback for Updated pill.
    mv0 = mvs[0] if mvs else {}
    published_at = raw.get("publishedAt") or mv0.get("publishedAt")
    created_at = raw.get("createdAt") or mv0.get("createdAt")
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "modelType": raw.get("modelType") or raw.get("type"),
        "type": raw.get("type") or raw.get("modelType"),
        "nsfw": raw.get("nsfw", False),
        "baseModel": base_model,
        "baseModels": base_models,
        "tags": tags[:8],
        "availability": raw.get("availability") or "Public",
        "earlyAccessDeadline": ea_deadline or None,
        "publishedAt": published_at or None,
        "createdAt": created_at or None,
        "images": images,
        "poster": poster,
        "cosmetic": _extract_cosmetic(raw),
        "avatarDeco": deco or None,
        "badge": badge or None,
        "nameplate": nameplate or None,
        "stats": {
            "downloadCount": stats.get("downloadCount", 0),
            "rating": stats.get("rating", 0),
            "thumbsUpCount": stats.get("thumbsUpCount", 0),
            "favoriteCount": stats.get("favoriteCount", 0),
            "commentCount": stats.get("commentCount", 0),
            "tippedAmountCount": stats.get("tippedAmountCount", 0),
        },
        "creator": {
            "username": creator.get("username", ""),
            "image": creator.get("image", ""),
        },
    }


def _parse_rest_model(raw: dict) -> dict:
    images = []
    for mv in raw.get("modelVersions", []):
        for img in mv.get("images", []):
            img_url = img.get("url", "")
            img["url"] = optimize_image_url(img_url, 450, img.get("type", "image"))
            images.append(img)

    tags_list = raw.get("tags", [])
    if isinstance(tags_list, list) and tags_list:
        if isinstance(tags_list[0], dict):
            tags = [t.get("name", "") for t in tags_list]
        else:
            tags = tags_list
    else:
        tags = []

    model_versions = []
    for mv in raw.get("modelVersions", []):
        version_images = []
        for img in mv.get("images", []):
            img_url = img.get("url", "")
            img["url"] = optimize_image_url(img_url, 450, img.get("type", "image"))
            version_images.append(img)
        model_versions.append({
            "id": mv.get("id"),
            "name": mv.get("name"),
            "baseModel": mv.get("baseModel"),
            "trainedWords": mv.get("trainedWords", []),
            "images": version_images,
            "downloadUrl": mv.get("downloadUrl", ""),
            "files": mv.get("files", []),
            "createdAt": mv.get("createdAt"),
            "stats": mv.get("stats", {}),
        })

    stats = raw.get("stats", {})
    deco, badge, nameplate = _extract_creator_cosmetics(raw)
    raw_base_models = raw.get("baseModels")
    mvs = raw.get("modelVersions", []) or []
    base_model = mvs[0].get("baseModel", "") if mvs else raw.get("baseModel", "")
    if isinstance(raw_base_models, list) and raw_base_models:
        base_models = [str(b) for b in raw_base_models if b]
    else:
        base_models = [base_model] if base_model else []

    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "description": raw.get("description", ""),
        "modelType": raw.get("modelType") or raw.get("type"),
        "baseModel": base_model,
        "baseModels": base_models,
        "nsfw": raw.get("nsfw", False),
        "tags": tags,
        "images": images,
        "modelVersions": model_versions,
        "cosmetic": _extract_cosmetic(raw),
        "avatarDeco": deco or None,
        "badge": badge or None,
        "nameplate": nameplate or None,
        "stats": {
            "downloadCount": stats.get("downloadCount", 0),
            "favoriteCount": stats.get("favoriteCount", 0),
            "commentCount": stats.get("commentCount", 0),
            "ratingCount": stats.get("ratingCount", 0),
            "rating": stats.get("rating", 0),
            "thumbsUpCount": stats.get("thumbsUpCount", 0),
            "thumbsDownCount": stats.get("thumbsDownCount", 0),
        },
        "creator": {
            "username": raw.get("creator", {}).get("username", "")
            if isinstance(raw.get("creator"), dict)
            else "",
            "image": raw.get("creator", {}).get("image", "")
            if isinstance(raw.get("creator"), dict)
            else "",
        },
        "createdAt": raw.get("createdAt"),
        "updatedAt": raw.get("updatedAt"),
        "lastVersionAt": raw.get("lastVersionAt"),
        "mode": raw.get("mode"),
    }


async def fetch_from_trpc(
    query: str = "",
    model_type: str | list[str] | None = None,
    base_model: str | None = None,
    tag: str | None = None,
    nsfw: str = DEFAULT_CIVITAI_NSFW,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> dict:
    client = get_http_client()

    input_data: dict[str, Any] = {
        "limit": limit,
        "nsfw": nsfw,
    }
    if query:
        input_data["query"] = query
    if model_type:
        input_data["types"] = model_type if isinstance(model_type, list) else [model_type]
    if base_model:
        input_data["baseModels"] = [base_model]
    if tag:
        input_data["tag"] = tag
    if cursor is not None:
        try:
            input_data["cursor"] = int(cursor)
        except (ValueError, TypeError):
            input_data["cursor"] = cursor

    input_json = json.dumps(input_data, separators=(",", ":"))

    t0 = time.time()
    try:
        resp = await _http_get_with_retry(
            f"{CIVITAI_TRPC_API}/model.getAll",
            params={"input": input_json},
            headers=_trpc_client_headers(),
        )
        t1 = time.time()
        logger.debug(f"tRPC request took {t1 - t0:.2f}s")

        data = resp.json()

        result_data = data
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "result" in item:
                    inner = item["result"]
                    if isinstance(inner, dict) and "data" in inner:
                        data_str = inner["data"]
                        if isinstance(data_str, str):
                            result_data = json.loads(data_str)
                        elif isinstance(data_str, dict):
                            result_data = data_str
                    break

        items_raw = []
        next_cursor = None
        if isinstance(result_data, dict):
            json_data = result_data.get("json")
            if isinstance(json_data, dict):
                items_raw = json_data.get("items", [])
                next_cursor_val = json_data.get("nextCursor")
                next_cursor = (
                    str(next_cursor_val)
                    if next_cursor_val is not None
                    else None
                )
            elif isinstance(result_data.get("result"), dict):
                inner = result_data["result"]
                data_inner = inner.get("data", {})
                if isinstance(data_inner, str):
                    data_inner = json.loads(data_inner)
                json_data = data_inner.get("json", {})
                if isinstance(json_data, str):
                    json_data = json.loads(json_data)
                items_raw = json_data.get("items", [])
                next_cursor_val = json_data.get("nextCursor")
                next_cursor = (
                    str(next_cursor_val)
                    if next_cursor_val is not None
                    else None
                )

        items = [_parse_trpc_model(item) for item in items_raw]

        if DB is not None:
            try:
                for item in items:
                    DB.upsert_model(json.dumps(item))
            except Exception as e:
                logger.debug(f"Cache upsert error: {e}")

        return {
            "items": items,
            "nextCursor": next_cursor,
            "source": "trpc",
        }
    except Exception as e:
        logger.warning(f"tRPC request failed: {e}")
        raise


async def fetch_from_rest(
    query: str = "",
    model_type: str | list[str] | None = None,
    base_model: str | None = None,
    tag: str | None = None,
    nsfw: str = DEFAULT_CIVITAI_NSFW,
    sort: str = "Newest",
    period: str = "AllTime",
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> dict:
    client = get_http_client()

    params: dict[str, Any] = {
        "limit": limit,
        "nsfw": "true" if nsfw in ("true", "True", "Soft", "Mature", "X") else "false",
    }
    if query:
        params["query"] = query
    if tag:
        params["tag"] = tag
    if model_type:
        params["types"] = model_type
    if base_model:
        params["baseModels"] = base_model
    if sort and sort != "Newest":
        params["sort"] = sort
    if period and period != "AllTime":
        params["period"] = period
    if cursor:
        params["cursor"] = cursor

    t0 = time.time()
    resp = await _http_get_with_retry(f"{CIVITAI_REST_API}/models", params=params)
    t1 = time.time()
    logger.debug(f"REST request took {t1 - t0:.2f}s")

    data = resp.json()
    items_raw = data.get("items", [])
    metadata = data.get("metadata", {})

    items = [_parse_model_slim(item) for item in items_raw]
    if items:
        logger.info(f"[CivBro] fetch_from_rest returned item 0 keys: {list(items[0].keys())}")

    next_cursor = metadata.get("nextCursor")

    return {
        "items": items,
        "nextCursor": next_cursor,
        "source": "rest",
    }


async def fetch_from_red(
    query: str = "",
    model_type: str | list[str] | None = None,
    base_model: str | None = None,
    tag: str | None = None,
    nsfw: str = DEFAULT_CIVITAI_NSFW,
    sort: str = "Newest",
    period: str = "AllTime",
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> dict:
    api_key = ""
    if DB is not None:
        api_key = DB.get_setting("civitaiRedApiKey") or ""
    if not api_key:
        raise HTTPException(status_code=401, detail="civitai.red API key not configured")

    client = get_http_client()

    params: dict[str, Any] = {
        "limit": limit,
        "nsfw": "true" if nsfw in ("true", "True", "Soft", "Mature", "X") else "false",
        "token": api_key,
    }
    if query:
        params["query"] = query
    if tag:
        params["tag"] = tag
    if model_type:
        params["types"] = model_type
    if base_model:
        params["baseModels"] = base_model
    if sort and sort != "Newest":
        params["sort"] = sort
    if period and period != "AllTime":
        params["period"] = period
    if cursor:
        params["cursor"] = cursor

    t0 = time.time()
    resp = await _http_get_with_retry(f"{CIVITAI_RED_API}/models", params=params)
    t1 = time.time()
    logger.debug(f"civitai.red request took {t1 - t0:.2f}s")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"civitai.red returned {resp.status_code}: {resp.text[:200]}",
        )

    data = resp.json()
    items_raw = data.get("items", [])
    metadata = data.get("metadata", {})

    items = [_parse_model_slim(item) for item in items_raw]

    next_cursor = metadata.get("nextCursor")

    return {
        "items": items,
        "nextCursor": next_cursor,
        "source": "red",
    }


def _get_civitai_key() -> str:
    if DB is not None:
        try:
            return DB.get_setting("civitaiRedApiKey") or ""
        except Exception:
            return ""
    return ""


async def fetch_trpc_version_detail(version_id: int, api_key: str = "") -> dict:
    """Fetch richer per-version data from Civitai's tRPC API (authenticated via the
    `token` query param). Exposes fields the public REST API omits — notably
    `linkedComponents` (the "Required Components": VAE / Text Encoder / etc.),
    `recommendedResources`, `air`, `clipSkip`, `epochs`, `steps`."""
    client = get_http_client()
    params: dict[str, Any] = {"input": json.dumps({"json": {"id": version_id}})}
    if api_key:
        params["token"] = api_key
    try:
        resp = await client.get(
            f"{CIVITAI_TRPC_API}/modelVersion.getById",
            params=params,
            timeout=20.0,
        )
        if resp.status_code == 200:
            return ((resp.json().get("result", {}) or {}).get("data", {}) or {}).get("json", {}) or {}
        logger.debug(f"tRPC version {version_id} returned HTTP {resp.status_code}")
    except Exception as e:
        logger.debug(f"tRPC version detail failed for {version_id}: {e}")
    return {}


def _parse_dependencies(trpc: dict) -> list[dict]:
    """Build the 'Required Components' list from tRPC linkedComponents."""
    deps = []
    for c in (trpc.get("linkedComponents") or []):
        vid = c.get("versionId")
        if not vid:
            continue
        deps.append({
            "type": c.get("componentType") or c.get("fileType") or "",
            "modelId": c.get("modelId"),
            "modelName": c.get("modelName"),
            "versionId": vid,
            "versionName": c.get("versionName"),
            "fileId": c.get("fileId"),
            "name": c.get("fileName") or c.get("modelName") or "",
            "sizeKB": c.get("sizeKB", 0),
            "required": c.get("isRequired", True),
            "downloadUrl": f"https://civitai.com/api/download/models/{vid}",
        })
    return deps


def register_routes(app):
    PREFIX = "/civbro/api"
    logger.info(f"[CivBro] Registering routes under {PREFIX}")

    # Clean up any leftover partial downloads from a previous (interrupted) session.
    _cleanup_orphan_parts()
    _download_queue: list[dict] = []

    @app.get(f"{PREFIX}/health")
    async def health():
        return {
            "status": "ok",
            "rust_available": RUST_AVAILABLE,
            "version": "1.0.0",
        }

    @app.get(f"{PREFIX}/models")
    async def search_models(
        query: str = Query(default="", description="Search query"),
        modelType: list[str] | None = Query(
            default=None, alias="type"
        ),
        baseModel: list[str] | None = Query(
            default=None, alias="baseModel"
        ),
        tag: str | None = Query(default=None),
        nsfw: str = Query(default=DEFAULT_CIVITAI_NSFW),
        sort: str = Query(default="Newest"),
        period: str = Query(default="AllTime"),
        limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=100),
        cursor: str | None = Query(default=None),
        source: str = Query(
            default="trpc",
            description="API source: trpc, rest, red, or auto",
        ),
    ):
        # Kick off the background connection warm-up on the first request so
        # subsequent searches land on a hot upstream connection.
        _ensure_warmup_started()

        cache_key = _search_cache_key(
            source=source, query=query, modelType=modelType,
            baseModel=baseModel, tag=tag, nsfw=nsfw, sort=sort,
            period=period, limit=limit, cursor=cursor,
        )
        cached = _search_cache_get(cache_key)
        if cached is not None:
            return cached

        if source == "red":
            try:
                result = await fetch_from_red(
                    query=query,
                    model_type=modelType,
                    base_model=baseModel,
                    tag=tag,
                    nsfw=nsfw,
                    sort=sort,
                    period=period,
                    limit=limit,
                    cursor=cursor,
                )
                # Enrich red results with tRPC availability/EA/updated data.
                # The red API omits EarlyAccess models and availability fields, but
                # tRPC has them. Query tRPC for the same filter and merge.
                api_key = _get_civitai_key()
                if api_key:
                    try:
                        trpc_extras = await _fetch_trpc_extras(
                            sort, period, modelType, query, nsfw=False
                        )
                        red_ids = {str(m.get("id")) for m in result.get("items", [])}
                        ea_models = []
                        for mid, ex in trpc_extras.items():
                            if mid in red_ids:
                                # Patch existing models with EA/updated fields
                                for m in result["items"]:
                                    if str(m.get("id")) == mid:
                                        _apply_extras_to_slim(m, ex)
                                        break
                            elif ex.get("availability") == "EarlyAccess":
                                # Add EA models not in red results
                                ea_models.append(_make_slim_from_trpc(ex, int(mid)))
                        if ea_models:
                            result["items"] = ea_models + result["items"]
                    except Exception:
                        pass

                _search_cache_put(cache_key, result)
                return result
            except Exception as e:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to fetch models from civitai.red: {str(e)}",
                )

        use_trpc = source in ("trpc", "auto")

        if use_trpc:
            try:
                result = await fetch_from_trpc(
                    query=query,
                    model_type=modelType,
                    base_model=baseModel,
                    tag=tag,
                    nsfw=nsfw,
                    limit=limit,
                    cursor=cursor,
                )
                _search_cache_put(cache_key, result)
                return result
            except Exception:
                if source == "trpc":
                    raise HTTPException(
                        status_code=502,
                        detail="tRPC API request failed",
                    )

        try:
            result = await fetch_from_rest(
                query=query,
                model_type=modelType,
                base_model=baseModel,
                tag=tag,
                nsfw=nsfw,
                sort=sort,
                period=period,
                limit=limit,
                cursor=cursor,
            )
            _search_cache_put(cache_key, result)
            return result
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch models from Civitai: {str(e)}",
            )

    @app.get(f"{PREFIX}/models/extras")
    async def model_extras(
        id: list[int] | None = Query(default=None),
        query: str = Query(default=""),
        modelType: list[str] | None = Query(default=None, alias="type"),
        sort: str = Query(default="Newest"),
        period: str = Query(default="AllTime"),
        nsfw: bool = Query(default=False),
    ):
        """Lazy, non-blocking card enrichment: cosmetic border, base-model family,
        avatar decoration, badge, nameplate, EA/updated. Fetched from tRPC (which
        the fast slim grid path omits). Prefer `id=` (exact grid model ids) for
        full coverage; falls back to the sort/period query otherwise. Called AFTER
        the grid renders, so it never delays the grid."""
        _ensure_warmup_started()
        if id:
            return {"extras": await _fetch_extras_by_ids(id)}
        mt = modelType[0] if isinstance(modelType, list) and modelType else modelType
        extras = await _fetch_trpc_extras(sort, period, mt, query, nsfw=bool(nsfw))
        return {"extras": extras}

    @app.get(f"{PREFIX}/models/{{civitai_id}}")
    async def get_model(civitai_id: int):
        client = get_http_client()

        try:
            resp = await client.get(f"{CIVITAI_REST_API}/models/{civitai_id}")
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Model not found")
            resp.raise_for_status()
            data = resp.json()
            return _parse_rest_model(data)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch model: {str(e)}",
            )

    @app.get(f"{PREFIX}/models/{{civitai_id}}/versions")
    async def get_model_versions(civitai_id: int):
        client = get_http_client()

        try:
            resp = await client.get(
                f"{CIVITAI_REST_API}/models/{civitai_id}"
            )
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Model not found")
            resp.raise_for_status()
            data = resp.json()

            versions = []
            for mv in data.get("modelVersions", []):
                version_images = []
                for img in mv.get("images", []):
                    img_url = img.get("url", "")
                    img["url"] = optimize_image_url(img_url, 450, img.get("type", "image"))
                    version_images.append(img)

                versions.append({
                    "id": mv.get("id"),
                    "name": mv.get("name"),
                    "baseModel": mv.get("baseModel"),
                    "trainedWords": mv.get("trainedWords", []),
                    "images": version_images,
                    "downloadUrl": mv.get("downloadUrl", ""),
                    "files": [
                        {
                            "id": f.get("id"),
                            "name": f.get("name"),
                            "sizeKB": f.get("sizeKB", 0),
                            "type": f.get("type", ""),
                            "primary": f.get("primary", False),
                            "format": f.get("metadata", {}).get("format", ""),
                            "fp": f.get("metadata", {}).get("fp", ""),
                            "sizeType": f.get("metadata", {}).get("size", ""),
                            "hashes": f.get("hashes", {}),
                            "downloadUrl": f.get("downloadUrl", ""),
                            "scannedAt": f.get("scannedAt"),
                            "pickleScanResult": f.get("pickleScanResult"),
                            "virusScanResult": f.get("virusScanResult"),
                        }
                        for f in mv.get("files", [])
                    ],
                    "createdAt": mv.get("createdAt"),
                    "availability": mv.get("availability"),
                    "buzzCost": mv.get("buzz"),
                    "stats": mv.get("stats", {}),
                    "description": mv.get("description", ""),
                    "availability": mv.get("availability", "Public"),
                    "earlyAccessEndsAt": mv.get("earlyAccessEndsAt") or (mv.get("earlyAccessConfig") or {}).get("timeframe"),
                })

            return {
                "modelId": civitai_id,
                "versions": versions,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch model versions: {str(e)}",
            )

    @app.get(f"{PREFIX}/versions/{{version_id}}")
    async def get_version(version_id: int):
        client = get_http_client()

        try:
            # Combined fetch: REST model-version detail + tRPC (Required Components etc.)
            # run in PARALLEL so total latency ≈ the slower single request, not the sum.
            rest_resp, trpc = await asyncio.gather(
                client.get(f"{CIVITAI_REST_API}/model-versions/{version_id}"),
                fetch_trpc_version_detail(version_id, _get_civitai_key()),
            )
            resp = rest_resp
            if resp.status_code == 404:
                raise HTTPException(
                    status_code=404, detail="Version not found"
                )
            resp.raise_for_status()
            data = resp.json()

            images = []
            for img in data.get("images", []):
                img_url = img.get("url", "")
                img["url"] = optimize_image_url(img_url, 450, img.get("type", "image"))
                images.append(img)

            dependencies = _parse_dependencies(trpc)

            # License & model-level metadata (from the embedded model object)
            model_obj = (data.get("model") or {}) if isinstance(data.get("model"), dict) else {}
            creator_obj = model_obj.get("creator") if isinstance(model_obj.get("creator"), dict) else {}
            availability = data.get("availability") or "Public"
            # The version detail endpoint may not return availability, but if
            # earlyAccessEndsAt is set and in the future, it's still Early Access.
            if availability == "Public":
                ea_ends = data.get("earlyAccessEndsAt")
                if ea_ends:
                    try:
                        from datetime import datetime, timezone
                        t = datetime.fromisoformat(ea_ends.replace("Z", "+00:00"))
                        if t > datetime.now(timezone.utc):
                            availability = "EarlyAccess"
                    except Exception:
                        pass
            early_access_ends = (
                data.get("earlyAccessEndsAt")
                or (data.get("earlyAccessConfig") or {}).get("timeframe")
            )
            buzz_cost = data.get("buzz") or data.get("buzzCost") or 0

            return {
                "id": data.get("id"),
                "modelId": data.get("modelId"),
                "name": data.get("name"),
                "baseModel": data.get("baseModel"),
                "trainedWords": data.get("trainedWords", []),
                "images": images,
                "downloadUrl": data.get("downloadUrl", ""),
                "dependencies": dependencies,
                "air": trpc.get("air", ""),
                "clipSkip": trpc.get("clipSkip"),
                "epochs": trpc.get("epochs"),
                "steps": trpc.get("steps"),
                "tensorType": trpc.get("tensorType") or model_obj.get("tensorType"),
                "modelSize": trpc.get("modelSize") or model_obj.get("modelSize"),
                "availability": availability,
                "earlyAccessEndsAt": early_access_ends,
                "buzzCost": int(buzz_cost) if buzz_cost else 0,
                "allowCommercialUse": model_obj.get("allowCommercialUse"),
                "allowDerivatives": model_obj.get("allowDerivatives"),
                "allowNoCredit": model_obj.get("allowNoCredit"),
                "allowDifferentLicense": model_obj.get("allowDifferentLicense"),
                "baseModels": model_obj.get("baseModels") or [],
                "creator": {
                    "username": creator_obj.get("username", ""),
                    "image": creator_obj.get("image", ""),
                    "createdAt": creator_obj.get("createdAt"),
                },
                "updatedAt": data.get("updatedAt"),
                "files": [
                    {
                        "id": f.get("id"),
                        "name": f.get("name"),
                        "sizeKB": f.get("sizeKB", 0),
                        "type": f.get("type", ""),
                        "primary": f.get("primary", False),
                        "format": f.get("metadata", {}).get("format", ""),
                        "fp": f.get("metadata", {}).get("fp", ""),
                        "sizeType": f.get("metadata", {}).get("size", ""),
                        "hashes": f.get("hashes", {}),
                        "downloadUrl": f.get("downloadUrl", ""),
                        "scannedAt": f.get("scannedAt"),
                        "pickleScanResult": f.get("pickleScanResult"),
                        "virusScanResult": f.get("virusScanResult"),
                    }
                    for f in data.get("files", [])
                ],
                "createdAt": data.get("createdAt"),
                "stats": data.get("stats", {}),
                "description": data.get("description", ""),
                "model": _parse_rest_model(data.get("model", {})),
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch version: {str(e)}",
            )

    @app.get(f"{PREFIX}/tags")
    async def search_tags(
        query: str = Query(default=""),
        limit: int = Query(default=20, ge=1, le=100),
    ):
        client = get_http_client()

        try:
            params: dict[str, Any] = {"limit": limit}
            if query:
                params["query"] = query

            resp = await client.get(
                f"{CIVITAI_REST_API}/tags", params=params
            )
            resp.raise_for_status()
            data = resp.json()
            return {"items": data.get("items", [])}
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch tags: {str(e)}",
            )

    @app.get(f"{PREFIX}/search/suggestions")
    async def search_suggestions(
        query: str = Query(default=""),
    ):
        # Use the models search endpoint with a small limit for suggestions
        client = get_http_client()

        try:
            params: dict[str, Any] = {
                "query": query,
                "limit": 5,
            }
            resp = await client.get(
                f"{CIVITAI_REST_API}/models", params=params
            )
            resp.raise_for_status()
            data = resp.json()

            suggestions = []
            for item in data.get("items", []):
                suggestions.append({
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "modelType": item.get("type"),
                    "nsfw": item.get("nsfw", False),
                })

            return {"items": suggestions}
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch suggestions: {str(e)}",
            )

    # Concurrency policy: large files (checkpoints > 2 GB) download one-at-a-time so the
    # connection isn't overwhelmed; smaller files (VAEs, TEs, LoRAs) run in parallel.
    LARGE_THRESHOLD_KB = 2 * 1024 * 1024  # 2 GB
    MAX_LARGE_CONCURRENT = 1
    MAX_SMALL_CONCURRENT = 4

    # Download bandwidth throttle: when a version-detail popup is loading the UI
    # needs bandwidth, so downloads slow to THROTTLE_SPEED_MULTIPLIER x normal.
    _download_throttle_until: float = 0.0
    THROTTLE_SPEED_MULTIPLIER = 0.20  # 20% bandwidth while popup loads
    THROTTLE_DURATION = 8.0           # seconds; short auto-expiring window that
                                      # covers popup image loading. The popup also
                                      # clears it on close; a small cap prevents a
                                      # dropped "disable" call from throttling
                                      # background downloads for long.

    @app.post(f"{PREFIX}/download/throttle")
    async def set_download_throttle(request: Request):
        """Frontend calls this when a popup starts loading version detail, so
        in-flight downloads yield bandwidth to the UI."""
        nonlocal _download_throttle_until
        try:
            body = await request.json()
            enable = body.get("enable", True)
            if enable:
                _download_throttle_until = time.time() + THROTTLE_DURATION
            else:
                _download_throttle_until = 0.0
        except Exception:
            _download_throttle_until = time.time() + THROTTLE_DURATION
        return {"throttled": _download_throttle_until > time.time()}

    def _is_large(entry: dict) -> bool:
        kb = entry.get("sizeKB") or 0
        if not kb and entry.get("bytesTotal"):
            kb = entry["bytesTotal"] / 1024
        return kb > LARGE_THRESHOLD_KB

    _schedule_lock = asyncio.Lock()

    def _schedule_downloads():
        if _schedule_lock.locked():
            asyncio.create_task(_schedule_downloads_async())
            return
        _schedule_downloads_sync()

    async def _schedule_downloads_async():
        async with _schedule_lock:
            _schedule_downloads_sync()

    def _schedule_downloads_sync():
        active_large = sum(1 for d in _download_queue if d["status"] == "downloading" and _is_large(d))
        active_small = sum(1 for d in _download_queue if d["status"] == "downloading" and not _is_large(d))
        for d in _download_queue:
            if d["status"] != "pending":
                continue
            large = _is_large(d)
            if large and active_large < MAX_LARGE_CONCURRENT:
                active_large += 1
                d["status"] = "downloading"
                d["updatedAt"] = time.time()
                asyncio.create_task(_process_download(d["id"]))
            elif not large and active_small < MAX_SMALL_CONCURRENT:
                active_small += 1
                d["status"] = "downloading"
                d["updatedAt"] = time.time()
                asyncio.create_task(_process_download(d["id"]))

    @app.post(f"{PREFIX}/download")
    async def start_download(request: Request):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        model_id = body.get("modelId")
        version_id = body.get("versionId")
        file_id = body.get("fileId")
        file_name = body.get("fileName", "model.safetensors")
        download_url = body.get("downloadUrl")
        size_kb = body.get("sizeKB") or 0
        download_dir = body.get(
            "downloadDir",
            str(EXTENSION_DIR / "downloads"),
        )
        model_type = body.get("modelType", "Checkpoint")

        if not download_url:
            raise HTTPException(
                status_code=400, detail="downloadUrl is required"
            )

        download_path = os.path.join(download_dir, file_name)

        download_id = str(uuid.uuid4())[:8]
        entry = {
            "id": download_id,
            "modelId": model_id,
            "versionId": version_id,
            "fileId": file_id,
            "fileName": file_name,
            "url": download_url,
            "downloadPath": download_path,
            "modelType": model_type,
            "sizeKB": size_kb,
            "status": "pending",
            "progress": 0,
            "bytesTotal": int(size_kb * 1024) if size_kb else 0,
            "bytesDownloaded": 0,
            "errorMessage": None,
            "createdAt": time.time(),
            "updatedAt": time.time(),
        }
        _download_queue.append(entry)

        if DB is not None:
            try:
                DB.add_download(json.dumps(entry))
            except Exception as e:
                logger.debug(f"Failed to add download to DB: {e}")

        _schedule_downloads()
        return entry

    @app.get(f"{PREFIX}/download/queue")
    async def get_download_queue():
        return {"items": _download_queue}

    @app.post(f"{PREFIX}/download/reorder")
    async def reorder_download_queue(request: Request):
        try:
            body = await request.json()
            order = body.get("order", [])
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        # Create a lookup for current queue entries
        by_id = {d["id"]: d for d in _download_queue}
        seen = set()
        new_queue = []
        # Place ordered items first, keeping only those still in queue
        for did in order:
            d = by_id.get(did)
            if d and d["status"] in ("pending", "queued"):
                new_queue.append(d)
                seen.add(did)
        # Append remaining queued/pending items not in the order list
        for d in _download_queue:
            if d["id"] not in seen and d["status"] in ("pending", "queued"):
                new_queue.append(d)
                seen.add(d["id"])
        # Append active (downloading) and terminal items
        for d in _download_queue:
            if d["id"] not in seen:
                new_queue.append(d)
                seen.add(d["id"])
        _download_queue[:] = new_queue
        return {"ok": True}

    async def _save_download_sidecar(client, entry, download_path, api_key):
        """Save first preview image + Civitai metadata beside a downloaded model."""
        version_id = entry.get("versionId")
        if not version_id:
            return
        base = str(Path(download_path).with_suffix(""))

        params = {"token": api_key} if api_key else None
        resp = await client.get(
            f"{CIVITAI_REST_API}/model-versions/{version_id}",
            params=params,
            timeout=30.0,
        )
        if resp.status_code != 200:
            logger.debug(f"sidecar: version {version_id} metadata HTTP {resp.status_code}")
            return
        data = resp.json()

        # 1) Full version metadata
        try:
            with open(base + ".civitai.info", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"sidecar .civitai.info write failed: {e}")

        # 2) Editable metadata sidecar
        try:
            model_info = data.get("model") or {}
            meta = {
                "description": model_info.get("description") or data.get("description") or "",
                "sd version": data.get("baseModel", ""),
                "activation text": ", ".join(data.get("trainedWords", []) or []),
                "preferred weight": 0,
                "modelId": data.get("modelId"),
                "modelVersionId": data.get("id"),
                "notes": "",
            }
            with open(base + ".json", "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"sidecar .json write failed: {e}")

        # 3) First non-video preview image
        images = data.get("images") or []
        preview_url = None
        for img in images:
            if isinstance(img, dict) and img.get("url") and img.get("type") != "video":
                preview_url = img["url"]
                break
        if not preview_url:
            return
        preview_url = optimize_image_url(preview_url, 512, "image")
        try:
            img_resp = await client.get(
                preview_url,
                follow_redirects=True,
                headers={"Accept": "image/*,*/*"},
                timeout=60.0,
            )
            if img_resp.status_code == 200:
                ct = img_resp.headers.get("content-type", "").lower()
                ext = "png" if "png" in ct else ("webp" if "webp" in ct else ("gif" if "gif" in ct else "jpeg"))
                with open(base + f".preview.{ext}", "wb") as f:
                    f.write(img_resp.content)
        except Exception as e:
            logger.debug(f"sidecar preview image failed: {e}")

    async def _process_download(download_id: str):
        entry = next(
            (d for d in _download_queue if d["id"] == download_id), None
        )
        if entry is None:
            return

        entry["status"] = "downloading"
        entry["updatedAt"] = time.time()

        client = get_http_client()
        download_path = Path(entry["downloadPath"])
        download_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = download_path.with_name(download_path.name + ".part")

        req_url = entry["url"]
        api_key = ""
        download_headers = {"Accept": "*/*"}
        if DB is not None:
            try:
                api_key = DB.get_setting("civitaiRedApiKey") or ""
            except Exception:
                api_key = ""
        if api_key:
            if "civitai.red" in req_url:
                if "token=" not in req_url:
                    sep = "&" if "?" in req_url else "?"
                    req_url = f"{req_url}{sep}token={api_key}"
            elif "civitai.com" in req_url:
                download_headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with client.stream(
                "GET",
                req_url,
                follow_redirects=True,
                headers=download_headers,
            ) as response:
                if response.status_code in (401, 403):
                    raise RuntimeError("This model requires Buzz to download — unlock it on civitai.com first, then retry")
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length:
                    entry["bytesTotal"] = int(content_length)

                with open(part_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        # Honour cancellation promptly: stop streaming so a
                        # cancelled download can't finish and get published to
                        # the models directory as an orphan.
                        if entry.get("status") == "cancelled":
                            break
                        f.write(chunk)
                        entry["bytesDownloaded"] += len(chunk)
                        # Respect the bandwidth throttle while the UI loads a popup.
                        if time.time() < _download_throttle_until:
                            await asyncio.sleep(0.05)
                        if entry["bytesTotal"] > 0:
                            entry["progress"] = min(
                                100,
                                int(entry["bytesDownloaded"] / entry["bytesTotal"] * 100),
                            )

            # Cancelled mid-stream: discard the partial file and stop before the
            # verify/rename step so nothing ever lands in the models folder.
            if entry.get("status") == "cancelled":
                try:
                    if part_path.exists():
                        part_path.unlink()
                except Exception as ce:
                    logger.debug(f"Failed to remove cancelled partial {part_path}: {ce}")
                entry["updatedAt"] = time.time()
                if DB is not None:
                    try:
                        DB.update_download_status(download_id, "cancelled")
                    except Exception:
                        pass
                _download_queue[:] = [d for d in _download_queue if d.get("id") != download_id]
                _schedule_downloads()
                return

            # Verify completeness
            expected = entry.get("bytesTotal") or 0
            got = part_path.stat().st_size if part_path.exists() else 0
            if expected > 0 and got < expected:
                raise ValueError(f"Incomplete download: {got}/{expected} bytes")
            if got == 0:
                raise ValueError("Downloaded 0 bytes")

            os.replace(str(part_path), str(download_path))

            entry["status"] = "completed"
            entry["progress"] = 100

            try:
                await _save_download_sidecar(client, entry, download_path, api_key)
            except Exception as se:
                logger.warning(f"Sidecar (preview/metadata) save failed for {download_id}: {se}")
            _installed_cache["t"] = 0.0
        except Exception as e:
            entry["status"] = "failed"
            entry["errorMessage"] = str(e)
            logger.error(f"Download {download_id} failed: {e}")
            try:
                if part_path.exists():
                    part_path.unlink()
            except Exception as ce:
                logger.debug(f"Failed to remove partial file {part_path}: {ce}")

        entry["updatedAt"] = time.time()

        if DB is not None:
            try:
                DB.update_download_status(download_id, entry["status"])
            except Exception as e:
                logger.debug(f"Failed to update download status: {e}")

        _schedule_downloads()

    # ---- Startup: recover stale entries from a prior (interrupted) session ----
    if DB is not None:
        try:
            prior = DB.get_pending_downloads()
            data = json.loads(prior) if isinstance(prior, str) else prior
            rows = data if isinstance(data, list) else []
        except Exception:
            rows = []
        stale_count = 0
        for r in rows:
            status = r.get("status", "")
            if status not in ("pending", "queued", "downloading"):
                continue
            r["status"] = "failed"
            r["errorMessage"] = "Download interrupted by WebUI restart"
            r["updatedAt"] = time.time()
            stale_count += 1
            try:
                DB.update_download_status(r.get("id", ""), "failed")
                part_path = Path(r.get("downloadPath", "")).with_name((r.get("fileName") or "") + ".part")
                if part_path.exists():
                    part_path.unlink()
            except Exception:
                pass
        if stale_count:
            logger.info(f"[CivBro] Marked {stale_count} stale download(s) from previous session as failed")

    @app.delete(f"{PREFIX}/download/{{download_id}}")
    async def cancel_download(download_id: str):
        entry = next(
            (d for d in _download_queue if d["id"] == download_id), None
        )
        if entry is None:
            raise HTTPException(
                status_code=404, detail="Download not found"
            )

        if entry["status"] in ("pending", "downloading"):
            entry["status"] = "cancelled"
            entry["updatedAt"] = time.time()

            if DB is not None:
                try:
                    DB.update_download_status(download_id, "cancelled")
                except Exception as e:
                    logger.debug(f"Failed to update download status: {e}")

        _download_queue[:] = [
            d for d in _download_queue if d["id"] != download_id
        ]

        return {"status": "cancelled"}

    @app.get(f"{PREFIX}/local/scan")
    async def scan_local_directories():
        sd_paths = [
            os.environ.get("SD_WEBUI_MODELS_DIR", ""),
            str(EXTENSION_DIR.parent.parent / "models"),
        ]

        results = {}
        for sd_path in sd_paths:
            if not sd_path or not os.path.isdir(sd_path):
                continue
            base = Path(sd_path)
            model_types = {
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

        if RUST_AVAILABLE:
            try:
                import civbro_core

                cpu_count = os.cpu_count() or 4
                results["metadata"] = {
                    "rust_enabled": True,
                    "parallel_workers": min(cpu_count, 8),
                }
            except Exception:
                results["metadata"] = {"rust_enabled": False}

        return results

    _installed_cache: dict = {"t": 0.0, "versions": [], "models": []}

    @app.get(f"{PREFIX}/local/filestatus")
    async def local_filestatus(version_id: int, verify: int = 0):
        """For each file of a version, report whether a healthy copy already exists
        locally (so the UI can avoid re-downloading). 'healthy' = present at the
        expected path with a matching size; with verify=1 the SHA256 is also checked
        against Civitai's hash (slower). Also reports incomplete/corrupt files."""
        from pathlib import Path as _P
        client = get_http_client()
        try:
            resp = await client.get(f"{CIVITAI_REST_API}/model-versions/{version_id}", timeout=20.0)
            if resp.status_code != 200:
                return {"files": []}
            data = resp.json()
        except Exception as e:
            logger.debug(f"filestatus fetch failed: {e}")
            return {"files": []}

        model_type = ((data.get("model") or {}).get("type")) or ""

        # Build the on-disk status (size checks + optional SHA256 hashing) in a
        # worker thread — hashing a multi-GB checkpoint would otherwise block the
        # event loop and stall every other request.
        trpc = await fetch_trpc_version_detail(version_id, _get_civitai_key())

        def _build_status() -> list:
            out = []

            def _check(name: str, sub: str, expected_kb, file_id, want_hash=""):
                path = _P(MODELS_ROOT) / sub / name
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
                return {"fileId": file_id, "name": name, "dir": sub, "status": status, "hashOk": hash_ok}

            for f in data.get("files", []):
                name = f.get("name") or ""
                if not name:
                    continue
                r = _check(name, _subdir_for_type(f.get("type", ""), name, model_type), f.get("sizeKB"), f.get("id"), (f.get("hashes") or {}).get("SHA256", ""))
                r["sizeKB"] = f.get("sizeKB", 0)
                out.append(r)

            # Also check linked-component dependencies (VAE / Text Encoder as separate models).
            for c in (trpc.get("linkedComponents") or []):
                name = c.get("fileName") or ""
                if not name:
                    continue
                sub = _subdir_for_type(c.get("componentType", ""), name, "")
                r = _check(name, sub, c.get("sizeKB"), c.get("fileId"))
                r["sizeKB"] = c.get("sizeKB", 0)
                r["dependency"] = True
                out.append(r)
            return out

        out = await asyncio.to_thread(_build_status)
        return {"files": out}

    @app.get(f"{PREFIX}/local/installed")
    async def local_installed():
        """Return version/model IDs present on disk, detected via `.civitai.info`
        sidecars (written by CivBro downloads and other Civitai tools). Cached briefly."""
        now = time.time()
        if _installed_cache["t"] and (now - _installed_cache["t"] < 20):
            return {"versionIds": _installed_cache["versions"], "modelIds": _installed_cache["models"]}

        def _scan_installed():
            versions: set[int] = set()
            models: set[int] = set()
            root = Path(
                os.environ.get("SD_WEBUI_MODELS_DIR")
                or "/home/gonzo/webui/sd-webui-forge-classic/models"
            )
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
        _installed_cache["t"] = now
        _installed_cache["versions"] = v_sorted
        _installed_cache["models"] = m_sorted
        return {"versionIds": _installed_cache["versions"], "modelIds": _installed_cache["models"]}

    @app.get(f"{PREFIX}/local/models")
    async def get_local_models():
        """List installed model files by walking the models tree and enriching each
        with its `.civitai.info` sidecar (modelId / versionId / friendly name).

        This reads the filesystem directly rather than the SQLite cache — the cache
        is not populated by the download/scan pipeline, so relying on it left the
        Local view permanently empty. The (blocking) directory walk runs in a worker
        thread so it never stalls the event loop."""
        def _scan() -> list[dict]:
            root = Path(MODELS_ROOT)
            type_by_dir = {
                "Stable-diffusion": "Checkpoint",
                "Lora": "LORA",
                "embeddings": "TextualInversion",
                "VAE": "VAE",
                "text_encoder": "TextEncoder",
                "ControlNet": "Controlnet",
                "ESRGAN": "Upscaler",
                "hypernetworks": "Hypernetwork",
                "AnimateDiff": "MotionModule",
            }
            exts = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf"}
            items: list[dict] = []
            idc = 0
            try:
                for p in root.rglob("*"):
                    if not p.is_file() or p.suffix.lower() not in exts:
                        continue
                    try:
                        rel = p.relative_to(root)
                        top = rel.parts[0] if rel.parts else ""
                    except Exception:
                        top = ""
                    mtype = type_by_dir.get(top, top or "Other")

                    name = p.stem
                    model_id = None
                    version_id = None
                    sidecar = p.with_name(p.stem + ".civitai.info")
                    if sidecar.exists():
                        try:
                            info = json.loads(sidecar.read_text(encoding="utf-8"))
                            version_id = info.get("id") if isinstance(info.get("id"), int) else version_id
                            model_id = info.get("modelId") if isinstance(info.get("modelId"), int) else model_id
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
        """Remove all locally stored files + sidecars for the referenced model.
        Called when the user clicks the installed download button on a card."""
        root = Path(MODELS_ROOT)
        removed = 0
        try:
            for info in root.rglob("*.civitai.info"):
                try:
                    data = json.loads(info.read_text(encoding="utf-8"))
                    if data.get("modelId") == model_id:
                        base = str(Path(info).with_suffix(""))
                        for ext in (".civitai.info", ".json", ".preview.png", ".preview.jpeg",
                                     ".preview.jpg", ".preview.webp",
                                     ".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf"):
                            f = Path(base + ext)
                            if f.exists():
                                f.unlink()
                                removed += 1
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"delete local model {model_id} failed: {e}")
        # invalidate installed cache so the pill goes away
        _installed_cache["t"] = 0.0
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

        scanned_files = []

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
                        parsed = json.loads(result) if isinstance(result, str) else result
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
                # Pure Python fallback
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
                    for root, _dirs, files in os.walk(dir_path):
                        for f in files:
                            ext = f.rsplit(".", 1)[-1].lower()
                            if ext in extensions:
                                full_path = os.path.join(root, f)
                                scanned.append({
                                    "path": full_path,
                                    "name": f,
                                    "size": os.path.getsize(full_path),
                                    "modelType": model_type,
                                })
            return scanned

        try:
            # Directory walking (and the Rust scan, which now releases the GIL)
            # runs in a worker thread so it never blocks the event loop.
            scanned_files = await asyncio.to_thread(_do_scan)
            return {
                "status": "ok",
                "filesFound": len(scanned_files),
                "files": scanned_files[:1000],
            }
        except Exception as e:
            logger.error(f"Refresh failed: {e}")
            return {"status": "error", "message": str(e)}


    @app.get(f"{PREFIX}/settings/_all")
    async def get_all_settings():
        if DB is None:
            return {"settings": {}}
        try:
            keys = ["showNsfw", "defaultModelTypes", "defaultBaseModels", "defaultModelType", "defaultBaseModel", "defaultSort", "defaultPeriod", "nsfwBlur", "civitaiRedApiKey", "useCivitaiRed"]
            result = {}
            for key in keys:
                val = DB.get_setting(key)
                if val is not None:
                    try:
                        result[key] = json.loads(val)
                    except Exception:
                        result[key] = val
            return {"settings": result}
        except Exception as e:
            return {"settings": {}, "error": str(e)}

    @app.post(f"{PREFIX}/settings/_all")
    async def set_all_settings(request: Request):
        if DB is None:
            raise HTTPException(status_code=500, detail="Rust core not available")
        try:
            body = await request.json()
            value = body.get("value", "{}")
            if isinstance(value, str):
                settings = json.loads(value)
            else:
                settings = value
            for key, val in (settings or {}).items():
                if not isinstance(val, str):
                    val = json.dumps(val)
                DB.set_setting(key, val)
            return {"status": "ok"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post(f"{PREFIX}/settings/validate-key")
    async def validate_api_key(request: Request):
        body = await request.json()
        key = body.get("key", "").strip()
        if not key:
            return {"valid": False, "message": "Key is empty"}

        client = get_http_client()
        try:
            # Validate against an AUTH-GATED endpoint. `favorites=true` is user-scoped
            # and returns 401 without a valid token, 200 with one. A public endpoint
            # (e.g. plain /models) returns 200 for ANY key and cannot validate.
            # Civitai auth mechanism is the `token` query param (NOT a custom header).
            resp = await client.get(
                f"{CIVITAI_RED_API}/models",
                params={"limit": 1, "favorites": "true", "token": key},
                timeout=15.0,
            )
            if resp.status_code == 200:
                if DB is not None:
                    DB.set_setting("civitaiRedApiKey", key)
                return {"valid": True, "message": "Key is valid"}
            elif resp.status_code == 401 or resp.status_code == 403:
                return {"valid": False, "message": "Invalid or unauthorized key"}
            else:
                return {"valid": False, "message": f"Server returned {resp.status_code}"}
        except httpx.TimeoutException:
            return {"valid": False, "message": "Connection timed out"}
        except Exception as e:
            return {"valid": False, "message": str(e)}

    @app.get(f"{PREFIX}/settings/{{key:path}}")
    async def get_setting(key: str):
        if DB is None:
            return {"key": key, "value": None}

        try:
            value = DB.get_setting(key)
            return {"key": key, "value": value}
        except Exception as e:
            logger.error(f"Failed to get setting {key}: {e}")
            return {"key": key, "value": None}

    @app.post(f"{PREFIX}/settings/{{key:path}}")
    async def set_setting(key: str, request: Request):
        if DB is None:
            raise HTTPException(
                status_code=500,
                detail="Rust core not available",
            )

        try:
            body = await request.json()
            value = body.get("value")
            if value is None:
                raise HTTPException(
                    status_code=400, detail="value is required"
                )

            if not isinstance(value, str):
                value = json.dumps(value)

            DB.set_setting(key, value)
            return {"key": key, "value": value}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to set setting {key}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save setting: {str(e)}",
            )

    @app.delete(f"{PREFIX}/cache")
    async def clear_cache():
        global _SEARCH_CACHE, _COSMETIC_CACHE, _EXTRAS_ID_CACHE
        _SEARCH_CACHE.clear()
        _COSMETIC_CACHE.clear()
        _EXTRAS_ID_CACHE.clear()
        if DB is not None:
            try:
                DB.clear_cache()
            except Exception as e:
                logger.error(f"Failed to clear cache: {e}")

        try:
            import shutil

            if CACHE_DIR.exists():
                shutil.rmtree(CACHE_DIR)
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to clear file cache: {e}")

        return {"status": "ok", "message": "Cache cleared"}


    logger.info(f"[CivBro] All routes registered under {PREFIX}")
