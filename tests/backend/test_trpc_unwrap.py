"""Tests for tRPC response unwrapping consolidation."""
from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock


def _mock_rust_core(monkeypatch):
    monkeypatch.setattr("civbro_backend.rust_facade.RUST_AVAILABLE", True)
    mock_core = MagicMock()
    monkeypatch.setitem(sys.modules, "civbro_core", mock_core)
    return mock_core


def test_fetch_trpc_uses_rust_parse_trpc_items(monkeypatch):
    """civitai_api.fetch_from_trpc must delegate item extraction to Rust parse_trpc_items,
    not walk the dict manually."""
    mock_core = _mock_rust_core(monkeypatch)

    t0 = 1_000_000_000.0
    monkeypatch.setattr("civbro_backend.civitai_api.time.time", lambda: t0)

    parse_calls = []

    def _fake_parse(response_json, style):
        parse_calls.append(style)
        return json.dumps([{"id": 42, "name": "Parsed by Rust", "modelType": "Checkpoint"}])

    mock_core.parse_models.side_effect = _fake_parse

    parse_trpc_calls = []

    def _fake_parse_trpc(response_json):
        parse_trpc_calls.append(json.loads(response_json))
        return json.dumps([
            {"id": 42, "name": "Model from Rust"},
            {"id": 43, "name": "Another Model"},
        ])

    mock_core.parse_trpc_response.side_effect = _fake_parse_trpc

    # Mock HTTP client
    import httpx

    resp = httpx.Response(200, json={
        "result": {
            "data": {
                "json": {
                    "items": [
                        {"id": 42, "name": "Model 42"},
                        {"id": 43, "name": "Model 43"},
                    ],
                    "nextCursor": "cursor_abc",
                }
            }
        }
    })

    async def fake_get(*args, **kwargs):
        return resp

    monkeypatch.setattr("civbro_backend.civitai_api.http_get_with_retry", fake_get)
    monkeypatch.setattr("civbro_backend.civitai_api._trpc_client_headers", lambda: {})

    import asyncio
    from civbro_backend.civitai_api import fetch_from_trpc

    result = asyncio.run(fetch_from_trpc(query="test", limit=2))

    # Items parsed by Rust parse_models
    assert len(result["items"]) == 2
    assert result["items"][0]["id"] == 42
    assert result["items"][0]["name"] == "Parsed by Rust"
    assert result["nextCursor"] == "cursor_abc"
    assert result["source"] == "trpc"

    # Verify Rust parse_trpc_response was called (item extraction delegated to Rust)
    assert len(parse_trpc_calls) == 1
    # Verify parse_models was called for each item
    assert len(parse_calls) == 2
