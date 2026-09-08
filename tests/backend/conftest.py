"""Shared pytest fixtures for the CivBro backend.

Runs against the real Rust core (civbro_core.so) with an isolated database and
models root, so tests never touch the user's real civbro.db or model files.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Test the extension shipped alongside this suite.
EXT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = EXT_DIR / "backend"
PKG_DIR = BACKEND_DIR / "civbro_backend"
for _p in (str(BACKEND_DIR), str(PKG_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Isolate DB + models root BEFORE any civbro_backend module is imported.
_TMP = Path(tempfile.mkdtemp(prefix="civbro-test-"))
os.environ["CIVBRO_DB_PATH"] = str(_TMP / "test.db")
os.environ["SD_WEBUI_MODELS_DIR"] = str(_TMP / "models")
(_TMP / "models").mkdir(parents=True, exist_ok=True)

TEST_MODELS_ROOT = _TMP / "models"


@pytest.fixture(autouse=True)
def _reset_process_caches():
    """In-process caches are module globals; without this, tests see each
    other's cached responses and the suite becomes order-dependent."""
    yield
    from civbro_backend import cache, http_adapter, localfiles
    from civbro_backend.trpc_extras import _COSMETIC_CACHE, _EXTRAS_ID_CACHE

    cache._SEARCH_CACHE.clear()
    _COSMETIC_CACHE.clear()
    _EXTRAS_ID_CACHE.clear()
    localfiles._installed_cache.update({"t": 0.0, "versions": [], "models": []})
    localfiles._sidecar_meta_cache.clear()
    http_adapter._HTTP_CLIENT = None


@pytest.fixture()
def models_root(monkeypatch) -> Path:
    """Point the backend at the throwaway models directory."""
    from civbro_backend import config

    monkeypatch.setattr(config, "MODELS_ROOT", str(TEST_MODELS_ROOT))
    return TEST_MODELS_ROOT


@pytest.fixture()
def client(models_root):
    """FastAPI TestClient with all CivBro routes registered."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from civbro_backend.routes import register_routes

    app = FastAPI()
    register_routes(app)
    return TestClient(app)
