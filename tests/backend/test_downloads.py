"""Tests for downloads.py: queue, scheduling, throttle, stale recovery."""
from __future__ import annotations

import os
import time

import pytest


def test_is_large():
    from civbro_backend.downloads import LARGE_THRESHOLD_KB, is_large

    assert is_large({"sizeKB": LARGE_THRESHOLD_KB + 1}) is True
    assert is_large({"sizeKB": LARGE_THRESHOLD_KB - 1}) is False
    assert is_large({"bytesTotal": (LARGE_THRESHOLD_KB + 1) * 1024}) is True
    assert is_large({"bytesTotal": (LARGE_THRESHOLD_KB - 1) * 1024}) is False
    assert is_large({}) is True


def test_create_and_find_entry(models_root):
    import asyncio
    from civbro_backend.downloads import create_download_entry, find_entry, remove_entry

    mp = models_root / "Lora"
    mp.mkdir(parents=True, exist_ok=True)
    entry = create_download_entry(
        model_id=1, version_id=2, file_id=3,
        file_name="model.safetensors",
        download_url="https://example.com/m",
        download_dir=str(mp),
        size_kb=1024, model_type="LORA",
    )
    assert entry["id"]
    assert entry["status"] == "pending"
    assert entry["downloadPath"] == str(mp / "model.safetensors")

    found = find_entry(entry["id"])
    assert found is not None
    assert found["modelId"] == 1

    asyncio.run(remove_entry(entry["id"]))
    assert find_entry(entry["id"]) is None


def test_create_entry_rejects_path_traversal(models_root):
    from civbro_backend.downloads import create_download_entry

    with pytest.raises(ValueError, match="escapes"):
        create_download_entry(1, 2, 3, "model.safetensors", "http://x", "/etc", 1, "Checkpoint")

    with pytest.raises(ValueError, match="Illegal"):
        create_download_entry(1, 2, 3, "../../evil.safetensors", "http://x", str(models_root), 1, "C")

    with pytest.raises(ValueError, match="Illegal"):
        create_download_entry(1, 2, 3, "sub/dir/f.safetensors", "http://x", str(models_root), 1, "C")


def test_reorder_queue(models_root):
    import asyncio
    from civbro_backend.downloads import create_download_entry, reorder_queue, remove_entry, _download_queue

    _download_queue.clear()
    d = str(models_root)
    e1 = create_download_entry(1, 1, 1, "a.safetensors", "http://x", d, 1, "Checkpoint")
    e2 = create_download_entry(2, 2, 2, "b.safetensors", "http://x", d, 1, "Checkpoint")
    e3 = create_download_entry(3, 3, 3, "c.safetensors", "http://x", d, 1, "Checkpoint")

    asyncio.run(reorder_queue([e3["id"], e1["id"]]))
    ordered = [d["modelId"] for d in _download_queue if d["status"] == "pending"]
    assert ordered[:2] == [3, 1]

    for e in [e1, e2, e3]:
        asyncio.run(remove_entry(e["id"]))


def test_throttle_set_get():
    from civbro_backend.downloads import get_throttle_until, set_throttle

    assert get_throttle_until() == 0.0
    set_throttle(True)
    assert get_throttle_until() > time.time()
    set_throttle(False)
    assert get_throttle_until() == 0.0


def test_installed_cache_invalidation():
    from civbro_backend.localfiles import get_installed_cache, invalidate_installed_cache

    cache = get_installed_cache()
    cache["t"] = time.time()
    cache["versions"] = [1, 2, 3]
    invalidate_installed_cache()
    assert cache["t"] == 0.0


def test_completed_download_remains_pollable(monkeypatch, models_root):
    import asyncio
    from civbro_backend import downloads

    class Response:
        status_code = 200
        headers = {"content-length": "4"}

        def raise_for_status(self):
            return None

        async def aiter_bytes(self, chunk_size=65536):
            yield b"data"

    class Stream:
        async def __aenter__(self):
            return Response()

        async def __aexit__(self, *args):
            return False

    class Client:
        def stream(self, *args, **kwargs):
            return Stream()

    async def no_sidecar(*args, **kwargs):
        return None

    monkeypatch.setattr(downloads, "get_http_client", lambda: Client())
    monkeypatch.setattr(downloads, "_save_download_sidecar", no_sidecar)
    entry = downloads.create_download_entry(
        model_id=11,
        version_id=22,
        file_id=33,
        file_name="pollable.safetensors",
        download_url="https://example.com/model",
        download_dir=str(models_root / "Lora"),
        size_kb=4 / 1024,
        model_type="LORA",
    )

    asyncio.run(downloads._process_download(entry["id"]))

    completed = downloads.find_entry(entry["id"])
    assert completed is not None
    assert completed["status"] == "completed"
    asyncio.run(downloads.remove_entry(entry["id"]))


def test_recover_stale_downloads():
    from civbro_backend.downloads import recover_stale_downloads, DB

    if DB is None:
        pytest.skip("Rust DB unavailable")
    count = recover_stale_downloads()
    assert isinstance(count, int)
