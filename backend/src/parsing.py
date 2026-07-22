from __future__ import annotations

import json
import logging
from typing import Any

from .client import RUST_AVAILABLE

logger = logging.getLogger("civbro.api")


def parse_trpc_model(raw: dict) -> dict:
    if RUST_AVAILABLE:
        try:
            import civbro_core
            items = json.loads(civbro_core.parse_models(json.dumps([raw]), "trpc"))
            return items[0] if items else _py_parse_trpc_model(raw)
        except Exception as e:
            logger.debug(f"Rust model parsing failed: {e}")
    return _py_parse_trpc_model(raw)


def parse_model_slim(raw: dict) -> dict:
    if RUST_AVAILABLE:
        try:
            import civbro_core
            items = json.loads(civbro_core.parse_models(json.dumps([raw]), "slim"))
            return items[0] if items else _py_parse_model_slim(raw)
        except Exception as e:
            logger.debug(f"Rust model parsing failed: {e}")
    return _py_parse_model_slim(raw)


def parse_rest_model(raw: dict) -> dict:
    if RUST_AVAILABLE:
        try:
            import civbro_core
            items = json.loads(civbro_core.parse_models(json.dumps([raw]), "rich"))
            return items[0] if items else _py_parse_rest_model(raw)
        except Exception as e:
            logger.debug(f"Rust model parsing failed: {e}")
    return _py_parse_rest_model(raw)


# ---- Pure-Python fallbacks ----
from .cosmetics import extract_cosmetic, extract_creator_cosmetics
from .utils import optimize_image_url


def _parse_base_models(raw: dict) -> list[str]:
    raw_base_models = raw.get("baseModels")
    mvs = raw.get("modelVersions", []) or []
    base_model = mvs[0].get("baseModel", "") if mvs else raw.get("baseModel", "")
    if isinstance(raw_base_models, list) and raw_base_models:
        return [str(b) for b in raw_base_models if b]
    return [base_model] if base_model else []


def _parse_tags(raw: dict) -> list[str]:
    tags_list = raw.get("tags", [])
    if isinstance(tags_list, list) and tags_list and isinstance(tags_list[0], dict):
        return [t.get("name", "") for t in tags_list]
    if isinstance(tags_list, list):
        return tags_list
    return []


def _parse_images_for_versions(model_versions: list, width: int = 450) -> list:
    images = []
    for mv in model_versions:
        for img in mv.get("images", []):
            img_url = img.get("url", "")
            img["url"] = optimize_image_url(img_url, width, img.get("type", "image"))
            images.append(img)
    return images


def _parse_creator(raw: dict) -> dict:
    creator = raw.get("creator", {})
    if not isinstance(creator, dict):
        return {"username": "", "image": ""}
    return {"username": creator.get("username", ""), "image": creator.get("image", "")}


def _py_parse_trpc_model(raw: dict) -> dict:
    images = _parse_images_for_versions(raw.get("modelVersions", []))
    tags = _parse_tags(raw)
    model_versions = [
        {
            "id": mv.get("id"),
            "name": mv.get("name"),
            "baseModel": mv.get("baseModel"),
            "trainedWords": mv.get("trainedWords", []),
            "images": _parse_images_for_versions([mv]),
            "downloadUrl": mv.get("downloadUrl", ""),
            "files": mv.get("files", []),
            "createdAt": mv.get("createdAt"),
            "stats": mv.get("stats", {}),
        }
        for mv in raw.get("modelVersions", [])
    ]
    stats = raw.get("stats", {})
    deco, badge, nameplate = extract_creator_cosmetics(raw)
    base_models = _parse_base_models(raw)
    base_model = base_models[0] if base_models else ""
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
        "cosmetic": extract_cosmetic(raw),
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
        "creator": _parse_creator(raw),
        "createdAt": raw.get("createdAt"),
        "updatedAt": raw.get("updatedAt"),
        "lastVersionAt": raw.get("lastVersionAt"),
    }


def _py_parse_model_slim(raw: dict) -> dict:
    mvs = raw.get("modelVersions", []) or []
    imgs = (mvs[0].get("images", []) if mvs else []) or raw.get("images", []) or []
    images = []
    poster = ""
    if imgs:
        im = dict(imgs[0])
        im["url"] = optimize_image_url(im.get("url", ""), 300, im.get("type", "image"))
        images = [im]
        if (imgs[0].get("type") or "image") == "video":
            for cand in imgs:
                if (cand.get("type") or "image") != "video" and cand.get("url"):
                    poster = optimize_image_url(cand.get("url", ""), 300, "image")
                    break
    tags = _parse_tags(raw)[:8]
    stats = raw.get("stats", {}) or {}
    base_models = _parse_base_models(raw)
    base_model = base_models[0] if base_models else ""
    creator = raw.get("creator") if isinstance(raw.get("creator"), dict) else {}
    deco, badge, nameplate = extract_creator_cosmetics(raw)
    ea_deadline = raw.get("earlyAccessDeadline") or raw.get("earlyAccessEndsAt")
    if not ea_deadline:
        ea_cfg = raw.get("earlyAccessConfig")
        if isinstance(ea_cfg, dict):
            ea_deadline = ea_cfg.get("timeframe") or ea_cfg.get("deadline")
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
        "tags": tags,
        "availability": raw.get("availability") or "Public",
        "earlyAccessDeadline": ea_deadline or None,
        "publishedAt": published_at or None,
        "createdAt": created_at or None,
        "images": images,
        "poster": poster,
        "cosmetic": extract_cosmetic(raw),
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
        "creator": {"username": creator.get("username", ""), "image": creator.get("image", "")},
    }


def _py_parse_rest_model(raw: dict) -> dict:
    images = _parse_images_for_versions(raw.get("modelVersions", []))
    tags = _parse_tags(raw)
    model_versions = [
        {
            "id": mv.get("id"),
            "name": mv.get("name"),
            "baseModel": mv.get("baseModel"),
            "trainedWords": mv.get("trainedWords", []),
            "images": _parse_images_for_versions([mv]),
            "downloadUrl": mv.get("downloadUrl", ""),
            "files": mv.get("files", []),
            "createdAt": mv.get("createdAt"),
            "stats": mv.get("stats", {}),
        }
        for mv in raw.get("modelVersions", [])
    ]
    stats = raw.get("stats", {})
    deco, badge, nameplate = extract_creator_cosmetics(raw)
    base_models = _parse_base_models(raw)
    base_model = base_models[0] if base_models else ""
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
        "cosmetic": extract_cosmetic(raw),
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
        "creator": _parse_creator(raw),
        "createdAt": raw.get("createdAt"),
        "updatedAt": raw.get("updatedAt"),
        "lastVersionAt": raw.get("lastVersionAt"),
        "mode": raw.get("mode"),
    }
