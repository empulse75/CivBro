"""Tests for cache.py: search cache get/put/eviction, TTL."""
from __future__ import annotations

import time

import pytest


def test_search_cache_key_is_deterministic():
    from civbro_backend.cache import search_cache_key

    a = search_cache_key(source="rest", query="anime", limit=20, sort="Newest")
    b = search_cache_key(source="rest", limit=20, query="anime", sort="Newest")
    assert a == b
    c = search_cache_key(source="trpc", query="anime", limit=20, sort="Newest")
    assert a != c


def test_cache_put_and_get():
    from civbro_backend.cache import search_cache_get, search_cache_key, search_cache_put, clear_caches

    clear_caches()
    key = search_cache_key(source="rest", query="test", limit=20)
    data = {"items": [{"id": 1, "baseModels": ["SD 1.5"]}]}
    search_cache_put(key, data)
    result = search_cache_get(key)
    assert result is not None
    assert result["items"][0]["id"] == 1


def test_cache_get_expired_entry_is_none(monkeypatch):
    from civbro_backend.cache import search_cache_get, search_cache_key, search_cache_put, clear_caches

    clear_caches()
    key = search_cache_key(query="soon", limit=1)
    search_cache_put(key, {"items": [{"id": 1, "baseModels": ["Pony"]}]})

    # Fake time so the entry is far in the past
    _real_time = time.time
    monkeypatch.setattr(time, "time", lambda: _real_time() + 9999999)
    assert search_cache_get(key) is None


def test_cache_get_empty_items_ignored():
    from civbro_backend.cache import search_cache_get, search_cache_key, search_cache_put, clear_caches

    clear_caches()
    key = search_cache_key(query="x", limit=1)
    search_cache_put(key, {"items": []})
    assert search_cache_get(key) is None  # put ignores empty items


def test_cache_get_strips_missing_base_models():
    from civbro_backend.cache import search_cache_get, search_cache_key, search_cache_put, clear_caches

    clear_caches()
    key = search_cache_key(query="broken", limit=5)
    items = [{"id": 99}]
    search_cache_put(key, {"items": items})
    # Missing baseModels on the first item → cache invalidated
    assert search_cache_get(key) is None


def test_cache_eviction_on_max_capacity():
    from civbro_backend import cache
    from civbro_backend.config import SEARCH_CACHE_MAX

    cache.clear_caches()
    for i in range(SEARCH_CACHE_MAX + 5):
        key = cache.search_cache_key(query=f"item{i}", limit=1)
        cache.search_cache_put(key, {"items": [{"id": i, "baseModels": ["SD 1.5"]}]})
    # Should not crash and should have at most SEARCH_CACHE_MAX entries
    assert len(cache._SEARCH_CACHE) <= SEARCH_CACHE_MAX


def test_clear_caches_removes_all():
    from civbro_backend import cache
    from civbro_backend.trpc_extras import _COSMETIC_CACHE, _EXTRAS_ID_CACHE

    cache.search_cache_put(cache.search_cache_key(q="x", limit=1), {"items": [{"id": 1, "baseModels": ["P"]}]})
    _COSMETIC_CACHE["k"] = (time.time(), {"a": 1})
    _EXTRAS_ID_CACHE[1] = (time.time(), {})

    cache.clear_caches()
    assert len(cache._SEARCH_CACHE) == 0
    assert len(_COSMETIC_CACHE) == 0
    assert len(_EXTRAS_ID_CACHE) == 0
