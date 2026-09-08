"""Tests for rust_facade.py: consolidated Rust pass-through module."""
from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock


def _mock_rust_core(monkeypatch):
    monkeypatch.setattr("civbro_backend.rust_facade.RUST_AVAILABLE", True)
    mock_core = MagicMock()
    monkeypatch.setitem(sys.modules, "civbro_core", mock_core)
    return mock_core


def test_all_public_functions_exist():
    from civbro_backend import rust_facade

    expected = [
        "parse_trpc_model",
        "parse_model_slim",
        "parse_rest_model",
        "extract_cosmetic",
        "extract_creator_cosmetics",
        "subdir_for_type",
        "optimize_image_url",
        "extract_trpc_extras",
        "parse_trpc_items",
        "apply_extras_to_slim",
        "make_slim_from_trpc",
        "parse_dependencies",
        "scan_model_dir",
        "build_version_list",
        "build_version_detail",
        "compute_file_hash",
    ]
    for name in expected:
        assert hasattr(rust_facade, name), f"rust_facade missing {name}"
        assert callable(getattr(rust_facade, name)), f"rust_facade.{name} is not callable"


def test_parsing_re_exports_from_rust_facade(monkeypatch):
    mock_core = _mock_rust_core(monkeypatch)
    result = {"id": 42, "name": "Test"}
    mock_core.parse_models.return_value = json.dumps([result])

    from civbro_backend.rust_facade import parse_model_slim, parse_trpc_model, parse_rest_model

    r = parse_model_slim({"id": 42})
    assert r["id"] == 42

    r2 = parse_trpc_model({"id": 42})
    assert r2["id"] == 42

    r3 = parse_rest_model({"id": 42})
    assert r3["id"] == 42


def test_cosmetics_re_exports_from_rust_facade(monkeypatch):
    mock_core = _mock_rust_core(monkeypatch)
    mock_core.build_extras.return_value = json.dumps({
        "cosmetic": {"cssFrame": "linear-gradient(90deg, red, blue)", "glow": True},
        "avatarDeco": None,
        "badge": None,
        "nameplate": None,
    })

    from civbro_backend.rust_facade import extract_cosmetic, extract_creator_cosmetics

    c = extract_cosmetic({"id": 1})
    assert c is not None
    assert "linear-gradient" in c["cssFrame"]

    deco, badge, plate = extract_creator_cosmetics({"id": 1})
    assert deco is None
    assert badge is None
    assert plate is None


def test_utils_re_exports_from_rust_facade(monkeypatch):
    mock_core = _mock_rust_core(monkeypatch)
    mock_core.file_subdir.return_value = "Lora"
    mock_core.optimize_cdn_url.return_value = "https://image.civitai.com/width=450/img.png"

    from civbro_backend.rust_facade import subdir_for_type, optimize_image_url

    assert subdir_for_type("LORA", "", "") == "Lora"
    result = optimize_image_url("https://image.civitai.com/x/1.png", 450, "image")
    assert "width=450" in result


def test_trpc_extras_pass_through_functions(monkeypatch):
    mock_core = _mock_rust_core(monkeypatch)
    mock_core.build_extras.return_value = json.dumps({"cosmetic": {"glow": True}})
    mock_core.parse_trpc_response.return_value = json.dumps([{"id": 1}])
    mock_core.merge_extras_into_slim.return_value = json.dumps({"id": 1, "enriched": True})
    mock_core.build_slim_from_extras.return_value = json.dumps({"id": 1, "slim": True})
    mock_core.parse_deps.return_value = json.dumps([{"name": "dep1"}])

    from civbro_backend.rust_facade import (
        extract_trpc_extras,
        parse_trpc_items,
        apply_extras_to_slim,
        make_slim_from_trpc,
        parse_dependencies,
    )

    extras = extract_trpc_extras({"id": 1})
    assert extras["cosmetic"]["glow"] is True

    items = parse_trpc_items({"result": {}})
    assert items[0]["id"] == 1

    model = {"id": 1}
    apply_extras_to_slim(model, {})
    assert model["enriched"] is True

    slim = make_slim_from_trpc({}, 1)
    assert slim["slim"] is True

def test_missing_facade_functions(monkeypatch):
    mock_core = _mock_rust_core(monkeypatch)
    mock_core.scan_model_dir.return_value = json.dumps([{"path": "/m/a.safetensors", "name": "a.safetensors", "size": 1000}])
    mock_core.build_version_list.return_value = json.dumps([{"id": 1}])
    mock_core.build_version_detail.return_value = json.dumps({"id": 2, "files": []})
    mock_core.compute_file_hash.return_value = "abc123"

    from civbro_backend.rust_facade import scan_model_dir, build_version_list, build_version_detail, compute_file_hash

    results = scan_model_dir("/models/Stable-diffusion", ["safetensors"])
    assert len(results) == 1
    assert results[0]["name"] == "a.safetensors"

    versions = build_version_list(json.dumps({"id": 1}))
    assert versions[0]["id"] == 1

    detail = build_version_detail(json.dumps({"id": 2}), json.dumps({}))
    assert detail["id"] == 2

    h = compute_file_hash("/path/to/file.safetensors", "sha256")
    assert h == "abc123"
