"""Regression tests for defects found during the 2026-09-03 audit.

Each test fails against the code as it was before that pass.
"""
from __future__ import annotations

import asyncio

import pytest


# ---- search route: early access ---------------------------------------------

def test_trpc_search_passes_early_access_flag(client, monkeypatch):
    """The tRPC branch referenced an undefined `earlyAccess`, so every
    source=trpc search raised NameError and was masked as a generic 502."""
    import civbro_backend.routes_models as routes_models
    from civbro_backend.cache import clear_caches

    clear_caches()
    seen: dict = {}

    async def _fake(**kw):
        seen.update(kw)
        return {"items": [{"id": 7, "name": "EA"}], "nextCursor": None, "source": "trpc"}

    monkeypatch.setattr(routes_models, "fetch_from_trpc", _fake)

    resp = client.get(
        "/civbro/api/models", params={"source": "trpc", "earlyAccess": "true"}
    )
    assert resp.status_code == 200
    assert seen["early_access"] is True


def test_early_access_reaches_rest_source(client, monkeypatch):
    """The frontend sends earlyAccess=true; the REST branch used to drop it."""
    import civbro_backend.routes_models as routes_models
    from civbro_backend.cache import clear_caches

    clear_caches()
    seen: dict = {}

    async def _fake(**kw):
        seen.update(kw)
        return {"items": [{"id": 1}], "nextCursor": None, "source": "rest"}

    monkeypatch.setattr(routes_models, "fetch_from_rest", _fake)

    resp = client.get(
        "/civbro/api/models", params={"source": "rest", "earlyAccess": "true"}
    )
    assert resp.status_code == 200
    assert seen["early_access"] is True


def test_early_access_is_part_of_the_cache_key(client, monkeypatch):
    """Without earlyAccess in the key, an EA search served non-EA results."""
    import civbro_backend.routes_models as routes_models
    from civbro_backend.cache import clear_caches

    clear_caches()
    calls: list[bool] = []

    async def _fake(**kw):
        calls.append(kw["early_access"])
        return {"items": [{"id": 1}], "nextCursor": None, "source": "rest"}

    monkeypatch.setattr(routes_models, "fetch_from_rest", _fake)

    client.get("/civbro/api/models", params={"source": "rest"})
    client.get("/civbro/api/models", params={"source": "rest", "earlyAccess": "true"})
    assert calls == [False, True]


# ---- tRPC request shaping ---------------------------------------------------

def test_trpc_base_models_is_a_flat_list():
    """The route hands over a list; wrapping it again produced [["SDXL"]],
    which Civitai silently ignores."""
    import json

    import civbro_backend.civitai_api as civitai_api

    captured: dict = {}

    async def _fake_get(url, **kw):
        captured["input"] = json.loads(kw["params"]["input"])

        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"result": {"data": {"json": {"items": [], "nextCursor": None}}}}

        return _Resp()

    civitai_api.http_get_with_retry = _fake_get
    try:
        asyncio.run(civitai_api.fetch_from_trpc(base_model=["SDXL 1.0", "Pony"]))
    finally:
        pass

    assert captured["input"]["json"]["baseModels"] == ["SDXL 1.0", "Pony"]


def test_next_cursor_reads_the_trpc_envelope():
    """Extras pagination used json.loads() on an already-decoded dict, so the
    cursor was always None and only the first page was ever fetched."""
    from civbro_backend.trpc_extras import _next_cursor

    payload = {"result": {"data": {"json": {"nextCursor": "abc123"}}}}
    assert _next_cursor(payload) == "abc123"

    assert _next_cursor({"result": {"data": {"json": {"nextCursor": -1}}}}) is None
    assert _next_cursor({"result": {"data": {"json": {}}}}) is None
    assert _next_cursor({}) is None
    assert _next_cursor("not a dict") is None


# ---- download queue ---------------------------------------------------------

def test_cancel_download_does_not_deadlock(client, monkeypatch):
    """cancel_download held _schedule_lock and then called remove_entry, which
    takes the same non-reentrant asyncio.Lock — wedging the whole queue."""
    import civbro_backend.downloads as downloads

    entry = downloads.create_download_entry(
        model_id=1,
        version_id=2,
        file_id=3,
        file_name="m.safetensors",
        download_url="https://example.invalid/m.safetensors",
        download_dir="",
        size_kb=10,
    )

    async def _noop():
        return None

    monkeypatch.setattr(downloads, "schedule_downloads", _noop)

    resp = client.delete(f"/civbro/api/download/{entry['id']}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert downloads.find_entry(entry["id"]) is None


def test_missing_api_key_fails_the_entry_instead_of_wedging_the_slot(monkeypatch):
    """The civitai.red key check raised outside _process_download's try block.
    The task died, the entry stayed 'downloading', and its concurrency slot was
    never released."""
    import civbro_backend.downloads as downloads

    entry = downloads.create_download_entry(
        model_id=1,
        version_id=2,
        file_id=3,
        file_name="red.safetensors",
        download_url="https://civitai.red/api/download/models/2",
        download_dir="",
        size_kb=10,
    )

    monkeypatch.setattr(downloads, "get_civitai_key", lambda: "")

    async def _noop():
        return None

    monkeypatch.setattr(downloads, "schedule_downloads", _noop)

    asyncio.run(downloads._process_download(entry["id"]))

    assert entry["status"] == "failed"
    assert "API key" in (entry["errorMessage"] or "")


# ---- models root resolution -------------------------------------------------

def test_models_root_is_not_a_hardcoded_developer_path():
    """MODELS_ROOT used to fall back to an absolute path from the author's
    machine, which does not exist on any other install."""
    import civbro_backend.config as config

    assert "/home/gonzo/webui" not in config._resolve_models_root()


def test_models_root_prefers_the_environment_override(monkeypatch, tmp_path):
    import civbro_backend.config as config

    monkeypatch.setenv("SD_WEBUI_MODELS_DIR", str(tmp_path))
    assert config._resolve_models_root() == str(tmp_path)


# ---- local scanning coverage ------------------------------------------------

def test_scan_covers_every_routable_model_type(tmp_path):
    """scan_directories used its own 6-entry map while the downloader routes to
    13 directories, so most types never appeared in /local/scan."""
    from civbro_backend.config import TYPE_BY_DIR
    from civbro_backend.localfiles import scan_directories

    for dir_name in TYPE_BY_DIR:
        (tmp_path / dir_name).mkdir(parents=True, exist_ok=True)
        (tmp_path / dir_name / "a.safetensors").write_bytes(b"x")

    results = scan_directories(str(tmp_path), TYPE_BY_DIR, False)
    found = {k for k in results if k != "metadata"}
    assert found == set(TYPE_BY_DIR.values())
    assert all(results[t]["fileCount"] >= 1 for t in found)


def test_scan_counts_every_model_extension(tmp_path):
    """The old glob list omitted .pth and .gguf."""
    from civbro_backend.config import MODEL_EXTENSIONS, TYPE_BY_DIR
    from civbro_backend.localfiles import scan_directories

    lora = tmp_path / "Lora"
    lora.mkdir(parents=True)
    for ext in MODEL_EXTENSIONS:
        (lora / f"model{ext}").write_bytes(b"x")

    results = scan_directories(str(tmp_path), TYPE_BY_DIR, False)
    assert results["LORA"]["fileCount"] == len(MODEL_EXTENSIONS)


# ---- extras cache -----------------------------------------------------------

def test_extras_id_cache_is_bounded():
    from civbro_backend.trpc_extras import _cache_put

    cache: dict = {}
    for i in range(50):
        _cache_put(cache, i, (float(i), {"x": i}), 10)
    assert len(cache) == 10
    # Oldest entries evicted first.
    assert 0 not in cache
    assert 49 in cache
