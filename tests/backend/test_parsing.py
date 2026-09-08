"""Tests for parsing.py: model parsing via Rust core."""
from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock


def _mk_model_with_creator(overrides: dict | None = None):
    d = {
        "id": 42,
        "name": "Test Model",
        "type": "Checkpoint",
        "nsfw": False,
        "creator": {"username": "tester", "image": ""},
        "tags": ["anime", "portrait"],
        "modelVersions": [
            {
                "id": 100,
                "name": "v1",
                "baseModel": "SDXL 1.0",
                "downloadUrl": "https://civitai.com/api/download/models/100",
                "images": [{"url": "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/a/original=true/1.png", "type": "image"}],
                "files": [
                    {"id": 7, "name": "m.safetensors", "sizeKB": 1024, "type": "Model", "primary": True,
                     "metadata": {"format": "SafeTensor", "fp": "fp16"}}],
                "stats": {"downloadCount": 42, "rating": 4.5},
                "availability": "Public",
                "buzz": 500,
            }
        ],
        "stats": {"downloadCount": 100, "rating": 4.8, "thumbsUpCount": 50, "favoriteCount": 20,
                   "commentCount": 5, "ratingCount": 60, "tippedAmountCount": 3,
                   "thumbsDownCount": 1},
        "baseModel": "SDXL 1.0",
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-06-01T00:00:00Z",
        "lastVersionAt": "2024-03-01T00:00:00Z",
    }
    if overrides:
        d.update(overrides)
    return d


def _mock_rust_core(monkeypatch, parse_models_side_effect=None):
    """Set RUST_AVAILABLE=True and inject a mock civbro_core module."""
    monkeypatch.setattr("civbro_backend.rust_facade.RUST_AVAILABLE", True)
    mock_core = MagicMock()
    if parse_models_side_effect is not None:
        mock_core.parse_models = parse_models_side_effect
    monkeypatch.setitem(sys.modules, "civbro_core", mock_core)
    return mock_core


def test_parse_model_slim_basic(monkeypatch):
    raw = _mk_model_with_creator()
    result = {
        "id": 42,
        "name": "Test Model",
        "modelType": "Checkpoint",
        "baseModel": "SDXL 1.0",
        "tags": ["anime", "portrait"],
        "availability": "Public",
        "earlyAccessDeadline": "",
        "stats": {"downloadCount": 100, "tippedAmountCount": 3},
    }
    _mock_rust_core(monkeypatch, parse_models_side_effect=lambda raw_json, style: json.dumps([result]))

    from civbro_backend.rust_facade import parse_model_slim
    r = parse_model_slim(raw)
    assert r["id"] == 42
    assert r["name"] == "Test Model"
    assert r["modelType"] == "Checkpoint"
    assert r["baseModel"] == "SDXL 1.0"
    assert len(r["tags"]) == 2
    assert r["availability"] == "Public"
    assert "earlyAccessDeadline" in r
    assert r["stats"]["downloadCount"] == 100
    assert r["stats"]["tippedAmountCount"] == 3


def test_parse_model_slim_video_poster(monkeypatch):
    data = _mk_model_with_creator()
    data["modelVersions"][0]["images"] = [
        {"url": "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/v/original=true/v.mp4", "type": "video"},
        {"url": "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/p/original=true/p.png", "type": "image"},
    ]
    result = {
        "id": 42,
        "name": "Test Model",
        "images": [{"type": "video"}],
        "poster": "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/p/width=300/p.png",
    }
    _mock_rust_core(monkeypatch, parse_models_side_effect=lambda raw_json, style: json.dumps([result]))

    from civbro_backend.rust_facade import parse_model_slim
    r = parse_model_slim(data)
    assert r["images"][0]["type"] == "video"
    assert r["poster"] and "width=300" in r["poster"]


def test_parse_trpc_model_basic(monkeypatch):
    raw = _mk_model_with_creator({"modelType": "LORA"})
    raw["mode"] = "Training"
    result = {"id": 42, "modelType": "LORA", "mode": "Training"}
    _mock_rust_core(monkeypatch, parse_models_side_effect=lambda raw_json, style: json.dumps([result]))

    from civbro_backend.rust_facade import parse_trpc_model
    r = parse_trpc_model(raw)
    assert r["modelType"] == "LORA"


def test_parse_rest_model_basic(monkeypatch):
    raw = _mk_model_with_creator()
    result = {
        "id": 42,
        "name": "Test Model",
        "modelType": "Checkpoint",
        "baseModel": "SDXL 1.0",
        "modelVersions": [{"id": 100}],
        "creator": {"username": "tester"},
        "stats": {"thumbsDownCount": 1},
    }
    _mock_rust_core(monkeypatch, parse_models_side_effect=lambda raw_json, style: json.dumps([result]))

    from civbro_backend.rust_facade import parse_rest_model
    r = parse_rest_model(raw)
    assert r["id"] == 42
    assert r["modelType"] == "Checkpoint"
    assert r["baseModel"] == "SDXL 1.0"
    assert r["modelVersions"][0]["id"] == 100
    assert r["creator"]["username"] == "tester"
    assert r["stats"]["thumbsDownCount"] == 1
