"""Tests for trpc_extras.py: tRPC response parsing, extras building, dependency parsing."""
from __future__ import annotations

import json
import asyncio
import sys
import time
from unittest.mock import MagicMock


def _mock_rust_core(monkeypatch):
    """Set RUST_AVAILABLE=True and inject a mock civbro_core module."""
    monkeypatch.setattr("civbro_backend.rust_facade.RUST_AVAILABLE", True)
    mock_core = MagicMock()
    monkeypatch.setitem(sys.modules, "civbro_core", mock_core)
    return mock_core


def test_trpc_client_headers():
    from civbro_backend.trpc_extras import _trpc_client_headers

    h = _trpc_client_headers()
    assert "User-Agent" in h
    assert "x-client" in h
    assert "x-client-version" in h
    assert "x-client-date" in h
    assert "Referer" in h


def test_apply_extras_to_slim(monkeypatch):
    mock_core = _mock_rust_core(monkeypatch)

    model_in = {"id": 1, "name": "Test", "publishedAt": "2024-01-01", "availability": "Public"}
    extras_in = {
        "availability": "EarlyAccess",
        "earlyAccessDeadline": "2025-01-01",
        "publishedAt": "2025-01-01",
        "createdAt": "2024-06-01",
        "hasBuzz": True,
    }
    merged = {
        "id": 1,
        "name": "Test",
        "availability": "EarlyAccess",
        "earlyAccessDeadline": "2025-01-01",
        "publishedAt": "2024-01-01",
        "createdAt": "2024-06-01",
        "hasBuzz": True,
    }
    mock_core.merge_extras_into_slim.return_value = json.dumps(merged)

    from civbro_backend.trpc_extras import apply_extras_to_slim

    model = dict(model_in)
    apply_extras_to_slim(model, extras_in)
    assert model["availability"] == "EarlyAccess"
    assert model["earlyAccessDeadline"] == "2025-01-01"
    assert model["publishedAt"] == "2024-01-01"
    assert model["createdAt"] == "2024-06-01"
    assert model["hasBuzz"] is True


def test_make_slim_from_trpc(monkeypatch):
    mock_core = _mock_rust_core(monkeypatch)

    extras = {
        "name": "Early Model",
        "modelType": "Checkpoint",
        "nsfw": False,
        "availability": "EarlyAccess",
        "stats": {},
        "creator": {"username": "t", "image": ""},
        "images": [],
    }
    slim_result = {
        "id": 99,
        "name": "Early Model",
        "modelType": "Checkpoint",
        "_fromTrpcExtras": True,
        "availability": "EarlyAccess",
    }
    mock_core.build_slim_from_extras.return_value = json.dumps(slim_result)

    from civbro_backend.trpc_extras import make_slim_from_trpc

    slim = make_slim_from_trpc(extras, 99)
    assert slim["id"] == 99
    assert slim["name"] == "Early Model"
    assert slim["_fromTrpcExtras"] is True
    assert slim["availability"] == "EarlyAccess"


def test_parse_dependencies_extracts_components(monkeypatch):
    mock_core = _mock_rust_core(monkeypatch)

    trpc = {
        "linkedComponents": [
            {
                "componentType": "VAE",
                "modelId": 5,
                "modelName": "VAE Model",
                "versionId": 10,
                "versionName": "v1",
                "fileId": 99,
                "fileName": "vae.safetensors",
                "sizeKB": 512,
                "isRequired": True,
            }
        ]
    }
    deps_result = [
        {
            "type": "VAE",
            "versionId": 10,
            "required": True,
            "downloadUrl": "https://civitai.com/api/download/models/99",
        }
    ]
    mock_core.parse_deps.return_value = json.dumps(deps_result)

    from civbro_backend.trpc_extras import parse_dependencies

    deps = parse_dependencies(trpc)
    assert len(deps) == 1
    assert deps[0]["type"] == "VAE"
    assert deps[0]["versionId"] == 10
    assert deps[0]["required"] is True
    assert "download" in deps[0]["downloadUrl"]


def test_cosmetic_cache_ttl_based_retrieval():
    from civbro_backend.trpc_extras import _COSMETIC_CACHE

    _COSMETIC_CACHE.clear()
    now = time.time()
    _COSMETIC_CACHE["key"] = (now, {"data": 1})
    assert "key" in _COSMETIC_CACHE
    _COSMETIC_CACHE.clear()


def test_extras_id_cache_ttl_based_retrieval():
    from civbro_backend.trpc_extras import _EXTRAS_ID_CACHE

    _EXTRAS_ID_CACHE.clear()
    now = time.time()
    _EXTRAS_ID_CACHE[42] = (now, {"a": 1})
    assert 42 in _EXTRAS_ID_CACHE
    _EXTRAS_ID_CACHE.clear()


def test_failed_extras_fetch_is_retried(monkeypatch):
    from civbro_backend import trpc_extras

    trpc_extras._EXTRAS_ID_CACHE.clear()
    calls = 0

    class Response:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body

        def json(self):
            return self._body

    async def fake_get(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return Response(503, {})
        return Response(200, [{"result": {"data": {"json": {"id": 42}}}}])

    monkeypatch.setattr(trpc_extras, "http_get_with_retry", fake_get)
    monkeypatch.setattr(trpc_extras, "extract_trpc_extras", lambda item: {"profileBackground": {"url": "animated.webm", "type": "video"}})

    assert asyncio.run(trpc_extras.fetch_extras_by_ids([42])) == {}
    assert asyncio.run(trpc_extras.fetch_extras_by_ids([42]))["42"]["profileBackground"]["type"] == "video"
    assert calls >= 2
    trpc_extras._EXTRAS_ID_CACHE.clear()
