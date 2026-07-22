from __future__ import annotations

import json
import logging
import time
from typing import Any

from .client import DB, RUST_AVAILABLE, get_http_client, http_get_with_retry
from .config import CIVITAI_TRPC_API, COSMETIC_CACHE_TTL, EXTRAS_ID_TTL
from .utils import optimize_image_url

logger = logging.getLogger("civbro.api")

_COSMETIC_CACHE: dict[str, tuple[float, dict]] = {}
_EXTRAS_ID_CACHE: dict[int, tuple[float, dict]] = {}


def _trpc_client_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "x-client": "web",
        "x-client-version": "5.0.2014",
        "x-client-date": str(int(time.time() * 1000)),
        "Referer": "https://civitai.com/models",
    }


def _extract_trpc_extras(item: dict) -> dict:
    if RUST_AVAILABLE:
        try:
            import civbro_core
            return json.loads(civbro_core.build_extras(json.dumps(item)))
        except Exception as e:
            logger.debug(f"Rust build_extras failed: {e}")
    return _py_extract_trpc_extras(item)


def _py_extract_trpc_extras(item: dict) -> dict:
    from .cosmetics import extract_cosmetic, extract_creator_cosmetics

    extras: dict[str, Any] = {}
    cos = extract_cosmetic(item)
    if cos:
        extras["cosmetic"] = cos
    base_models = item.get("baseModels")
    if isinstance(base_models, list) and base_models:
        extras["baseModels"] = [str(b) for b in base_models if b]
    deco, badge, nameplate = extract_creator_cosmetics(item)
    if deco:
        extras["avatarDeco"] = deco
    if badge:
        extras["badge"] = badge
    if nameplate:
        extras["nameplate"] = nameplate
    avail = item.get("availability")
    if avail:
        extras["availability"] = avail
    if item.get("earlyAccessDeadline"):
        extras["earlyAccessDeadline"] = item.get("earlyAccessDeadline")
    if item.get("publishedAt"):
        extras["publishedAt"] = item.get("publishedAt")
    if item.get("createdAt"):
        extras["createdAt"] = item.get("createdAt")
    versions = item.get("modelVersions")
    if isinstance(versions, list) and any(
        isinstance(v, dict) and v.get("requiresBuzz") for v in versions
    ):
        extras["hasBuzz"] = True
    if item.get("mode"):
        extras["mode"] = item.get("mode")
    extras["name"] = item.get("name", "")
    extras["modelType"] = item.get("modelType") or item.get("type", "")
    extras["nsfw"] = item.get("nsfw", False)
    extras["stats"] = item.get("stats", {})
    creator = item.get("creator") if isinstance(item.get("creator"), dict) else {}
    extras["creator"] = {"username": creator.get("username", ""), "image": creator.get("image", "")}
    mvs = item.get("modelVersions", [])
    if not isinstance(mvs, list):
        mvs = []
    imgs = (mvs[0].get("images", []) if mvs else []) or item.get("images", []) or []
    if imgs:
        im = dict(imgs[0]) if isinstance(imgs[0], dict) else {}
        im["url"] = optimize_image_url(im.get("url", ""), 300, im.get("type", "image"))
        extras["images"] = [im]
    return extras


def parse_trpc_items(resp_json: dict) -> list[dict]:
    if RUST_AVAILABLE:
        try:
            import civbro_core
            return json.loads(civbro_core.parse_trpc_response(json.dumps(resp_json)))
        except Exception as e:
            logger.debug(f"Rust parse_trpc_items failed: {e}")
    return _py_parse_trpc_items(resp_json)


def _py_parse_trpc_items(resp_json: dict) -> list[dict]:
    from .cosmetics import extract_cosmetic, extract_creator_cosmetics

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
                    _py_resolve_user_field(obj, arr)
                    _py_resolve_cosmetic_field(obj, arr)
                    items.append(obj)
            return items
    except Exception as e:
        logger.debug(f"parse_trpc_items failed: {e}")
    return []


def _py_resolve_cosmetic_field(obj: dict, arr: list) -> None:
    try:
        cos = obj.get("cosmetic")
        if not isinstance(cos, dict):
            return
        data_idx = cos.get("data")
        if isinstance(data_idx, int) and 0 <= data_idx < len(arr):
            data_tpl = arr[data_idx]
            if isinstance(data_tpl, dict) and all(isinstance(v, int) for v in data_tpl.values()):
                cos["data"] = {
                    k: arr[vi]
                    for k, vi in data_tpl.items()
                    if isinstance(vi, int) and 0 <= vi < len(arr)
                }
    except Exception:
        pass


def _py_resolve_user_field(obj: dict, arr: list) -> None:
    def _resolve(val: Any, depth: int = 0) -> Any:
        if depth > 5:
            return val
        if isinstance(val, int) and 0 <= val < len(arr):
            return _resolve(arr[val], depth + 1)
        if isinstance(val, list):
            return [_resolve(v, depth + 1) for v in val]
        if isinstance(val, dict):
            vs = list(val.values())
            if vs and all(isinstance(v, int) for v in vs):
                return {
                    k: _resolve(arr[vi], depth + 1)
                    for k, vi in val.items()
                    if isinstance(vi, int) and 0 <= vi < len(arr)
                }
            return val
        return val

    try:
        user_raw = obj.get("user")
        if isinstance(user_raw, dict):
            obj["user"] = _resolve(user_raw)
    except Exception:
        pass


async def fetch_trpc_extras(
    sort: str, period: str, model_type: Any, query: str, nsfw: bool = False
) -> dict:
    key = json.dumps([sort, period, model_type, query, nsfw], sort_keys=True, default=str)
    hit = _COSMETIC_CACHE.get(key)
    if hit and time.time() - hit[0] < COSMETIC_CACHE_TTL:
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
        for _ in range(20):
            req_inp = {k: dict(v) if isinstance(v, dict) else v for k, v in inp.items()}
            if cursor is not None:
                req_inp["json"]["cursor"] = cursor
            resp = await http_get_with_retry(
                f"{CIVITAI_TRPC_API}/model.getAll",
                params={"input": json.dumps(req_inp, separators=(",", ":"))},
                headers=headers,
                timeout=15.0,
            )
            if resp.status_code != 200:
                break
            items = parse_trpc_items(resp.json())
            if not items:
                break
            for it in items:
                mid = it.get("id")
                if mid is None:
                    continue
                extras = _extract_trpc_extras(it)
                if extras:
                    out[str(mid)] = extras
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


async def fetch_extras_by_ids(ids: list[int]) -> dict:
    now = time.time()
    out: dict = {}
    misses: list[int] = []
    for i in ids:
        hit = _EXTRAS_ID_CACHE.get(i)
        if hit and now - hit[0] < EXTRAS_ID_TTL:
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
        inp = {
            str(idx): {"json": {"id": mid, "browsingLevel": 127}}
            for idx, mid in enumerate(chunk)
        }
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


def apply_extras_to_slim(model: dict, extras: dict) -> None:
    if RUST_AVAILABLE:
        try:
            import civbro_core
            merged = json.loads(civbro_core.merge_extras_into_slim(json.dumps(model), json.dumps(extras)))
            model.clear()
            model.update(merged)
            return
        except Exception as e:
            logger.debug(f"Rust merge_extras failed: {e}")

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


def make_slim_from_trpc(extras: dict, model_id: int) -> dict:
    if RUST_AVAILABLE:
        try:
            import civbro_core
            return json.loads(civbro_core.build_slim_from_extras(json.dumps(extras), model_id))
        except Exception as e:
            logger.debug(f"Rust build_slim failed: {e}")

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


async def fetch_trpc_version_detail(version_id: int, api_key: str = "") -> dict:
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
            return (
                ((resp.json().get("result", {}) or {}).get("data", {}) or {})
                .get("json", {})
                or {}
            )
        logger.debug(f"tRPC version {version_id} returned HTTP {resp.status_code}")
    except Exception as e:
        logger.debug(f"tRPC version detail failed for {version_id}: {e}")
    return {}


def parse_dependencies(trpc: dict) -> list[dict]:
    if RUST_AVAILABLE:
        try:
            import civbro_core
            return json.loads(civbro_core.parse_deps(json.dumps(trpc)))
        except Exception as e:
            logger.debug(f"Rust parse_deps failed: {e}")

    deps = []
    for c in trpc.get("linkedComponents") or []:
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
