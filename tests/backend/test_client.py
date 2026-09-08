"""Tests for client.py: HTTP client, retry, warmup, orphan cleanup, DB path."""
from __future__ import annotations

import os
import asyncio
import time
from pathlib import Path

import pytest


def test_red_fetch_uses_shared_key_accessor(monkeypatch):
    from civbro_backend import civitai_api

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"items": [], "metadata": {}}

    async def fake_get(*args, **kwargs):
        assert kwargs["params"]["token"] == "configured-key"
        return Response()

    monkeypatch.setattr(civitai_api, "get_civitai_key", lambda: "configured-key", raising=False)
    monkeypatch.setattr(civitai_api, "http_get_with_retry", fake_get)

    result = asyncio.run(civitai_api.fetch_from_red())
    assert result == {"items": [], "nextCursor": None, "source": "red"}


def test_get_http_client_returns_same_instance():
    from civbro_backend.client import get_http_client

    c1 = get_http_client()
    c2 = get_http_client()
    assert c1 is c2


def test_get_civitai_key_empty_when_none():
    from civbro_backend.client import get_civitai_key
    # In test env DB is fresh; key should be empty
    key = get_civitai_key()
    assert key == ""


# ---- _resolve_db_path tests (expanded from test_client_dbpath.py) ----


def _touch(path: Path, mtime: float) -> None:
    path.write_bytes(b"db")
    os.utime(path, (mtime, mtime))


def test_fresh_install_returns_anchored_target(tmp_path):
    from civbro_backend.client import _resolve_db_path

    target = tmp_path / "ext" / "civbro.db"
    legacy = tmp_path / "cwd" / "civbro.db"
    assert _resolve_db_path([target, legacy]) == str(target)


def test_resolve_returns_target(tmp_path):
    from civbro_backend.client import _resolve_db_path

    target = tmp_path / "ext" / "civbro.db"
    assert _resolve_db_path([target]) == str(target)
    assert target.parent.exists()


def test_resolve_returns_target_with_legacy_present(tmp_path):
    from civbro_backend.client import _resolve_db_path

    target = tmp_path / "ext" / "civbro.db"
    target.parent.mkdir(parents=True)
    legacy = tmp_path / "cwd" / "civbro.db"
    legacy.parent.mkdir(parents=True)
    _touch(legacy, 2_000_000_000)

    assert _resolve_db_path([target]) == str(target)
    assert target.parent.exists()


def test_resolve_returns_existing_target(tmp_path):
    from civbro_backend.client import _resolve_db_path

    target = tmp_path / "civbro.db"
    _touch(target, 1_500_000_000)
    assert _resolve_db_path([target]) == str(target)
