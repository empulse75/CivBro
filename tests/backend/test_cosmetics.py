"""Tests for cosmetics.py: cosmetic extraction via Rust core."""
from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock


def _mock_rust_core(monkeypatch):
    """Set RUST_AVAILABLE=True and inject a mock civbro_core module."""
    monkeypatch.setattr("civbro_backend.rust_facade.RUST_AVAILABLE", True)
    mock_core = MagicMock()
    monkeypatch.setitem(sys.modules, "civbro_core", mock_core)
    return mock_core


def test_extract_cosmetic_from_raw_item(monkeypatch):
    mock_core = _mock_rust_core(monkeypatch)

    raw = {
        "cosmetic": {
            "type": "ContentDecoration",
            "data": {"cssFrame": "linear-gradient(90deg, #aabbcc, #ddeeff)", "glow": True},
        }
    }
    mock_core.build_extras.return_value = json.dumps({
        "cosmetic": {"cssFrame": "linear-gradient(90deg, #aabbcc, #ddeeff)", "glow": True},
    })

    from civbro_backend.rust_facade import extract_cosmetic

    result = extract_cosmetic(raw)
    assert result is not None
    assert "linear-gradient" in result["cssFrame"]
    assert result["glow"] is True

    # No cosmetic
    mock_core.build_extras.return_value = json.dumps({})
    assert extract_cosmetic({"name": "plain"}) is None


def test_extract_creator_cosmetics_returns_tuple(monkeypatch):
    monkeypatch.setattr("civbro_backend.rust_facade.RUST_AVAILABLE", False)
    from civbro_backend.rust_facade import extract_creator_cosmetics

    # Without Rust core, returns (None, None, None) gracefully
    deco, badge, nameplate = extract_creator_cosmetics({"name": "plain"})
    assert deco is None
    assert badge is None
    assert nameplate is None


def test_extract_creator_cosmetics_with_rust(monkeypatch):
    mock_core = _mock_rust_core(monkeypatch)

    item = {
        "creator": {
            "username": "tester",
            "avatarDeco": "deco123",
            "badge": "badge456",
            "nameplate": {"gradient": {"from": "#111", "to": "#222", "deg": 90}},
            "cosmetics": [
                {"cosmetic": {"type": "ProfileDecoration", "data": {"url": "pd_url"}}},
                {"cosmetic": {"type": "Badge", "data": {"url": "b_url"}}},
            ],
        }
    }
    mock_core.build_extras.return_value = json.dumps({
        "avatarDeco": "https://image.civitai.com/deco123/original=true/deco.png",
        "badge": "https://image.civitai.com/badge456/original=true/deco.png",
        "nameplate": {"gradient": "linear-gradient(90deg, #111, #222)"},
    })

    from civbro_backend.rust_facade import extract_creator_cosmetics

    deco, badge, nameplate = extract_creator_cosmetics(item)
    assert deco is not None
    assert badge is not None
    assert nameplate is not None
