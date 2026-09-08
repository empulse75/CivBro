"""Route-level integration tests: model, version, tag, config, extras endpoints."""
from __future__ import annotations

from fastapi import HTTPException


# ---- search_models ----------------------------------------------------------

def test_search_models_rest_source_returns_200(client, monkeypatch):
    import civbro_backend.routes_models as routes_models

    async def _fake(**kw):
        return {"items": [{"id": 1, "name": "Test"}], "nextCursor": None, "source": "rest"}

    monkeypatch.setattr(routes_models, "fetch_from_rest", _fake)

    resp = client.get("/civbro/api/models", params={"source": "rest"})
    assert resp.status_code == 200
    assert resp.json()["items"][0]["id"] == 1


def test_red_source_preserves_401(client, monkeypatch):
    import civbro_backend.routes_models as routes_models

    async def _raise_401(**kw):
        raise HTTPException(status_code=401, detail="civitai.red API key not configured")

    monkeypatch.setattr(routes_models, "fetch_from_red", _raise_401)

    resp = client.get("/civbro/api/models", params={"source": "red"})
    assert resp.status_code == 401
    assert "key" in resp.json()["detail"].lower()


def test_search_models_trpc_falls_back_to_rest(client, monkeypatch):
    import civbro_backend.routes_models as routes_models
    from civbro_backend.cache import clear_caches

    clear_caches()

    async def _fail_trpc(*a, **kw):
        raise ConnectionError("boom")

    async def _ok_rest(*a, **kw):
        return {"items": [{"id": 2, "name": "RestModel"}], "nextCursor": None, "source": "rest"}

    monkeypatch.setattr(routes_models, "fetch_from_trpc", _fail_trpc)
    monkeypatch.setattr(routes_models, "fetch_from_rest", _ok_rest)

    resp = client.get("/civbro/api/models", params={"source": "auto"})
    assert resp.status_code == 200
    assert resp.json()["items"][0]["id"] == 2


# ---- get_model --------------------------------------------------------------

def test_get_model_404_is_passthrough(client, monkeypatch):
    from civbro_backend.client import get_http_client

    client_obj = get_http_client()

    class _Resp404:
        status_code = 404

        def raise_for_status(self):
            raise HTTPException(404, "Model not found")

    original_get = client_obj.get

    async def _fake_get(*a, **kw):
        if "/models/" in str(a[0]):
            return _Resp404()
        return await original_get(*a, **kw)

    monkeypatch.setattr(client_obj, "get", _fake_get)

    resp = client.get("/civbro/api/models/999999")
    assert resp.status_code == 404


# ---- search_tags ------------------------------------------------------------

def _mock_http_client_with(monkeypatch, json_data):
    """Replace get_http_client() with a mock whose .get() returns json_data."""
    from civbro_backend.client import get_http_client

    class _MockClient:
        async def get(self, *a, **kw):
            return _Resp(json_data)

        @property
        def timeout(self):
            return None

        @property
        def limits(self):
            return None

        @property
        def headers(self):
            return {}

    class _Resp:
        def __init__(self, data):
            self.status_code = 200
            self._data = data

        def json(self):
            return self._data

        def raise_for_status(self):
            pass

    monkeypatch.setattr("civbro_backend.http_adapter.get_http_client", lambda: _MockClient())
    monkeypatch.setattr("civbro_backend.http_adapter._HTTP_CLIENT", _MockClient())


def test_search_tags_returns_items(client, monkeypatch):
    _mock_http_client_with(monkeypatch, {"items": [{"name": "anime"}, {"name": "portrait"}]})

    resp = client.get("/civbro/api/tags", params={"query": "ani"})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


def test_search_suggestions_returns_list(client, monkeypatch):
    _mock_http_client_with(
        monkeypatch,
        {"items": [{"id": 1, "name": "Best Model", "type": "Checkpoint", "nsfw": False}]},
    )

    resp = client.get("/civbro/api/search/suggestions", params={"query": "best"})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


# ---- config -----------------------------------------------------------------

def test_get_frontend_config(client):
    resp = client.get("/civbro/api/config")
    assert resp.status_code == 200
    cfg = resp.json()
    assert "modelsRoot" in cfg
    assert "dirMap" in cfg
    assert "frontendDirMap" in cfg


# ---- model_extras ----------------------------------------------------------

def test_model_extras_by_ids(client, monkeypatch):
    import civbro_backend.routes_models as routes_models

    async def _fake(ids):
        return {str(i): {"name": f"model{i}"} for i in ids}

    monkeypatch.setattr(routes_models, "fetch_extras_by_ids", _fake)

    resp = client.get("/civbro/api/models/extras", params=[("id", 1), ("id", 2)])
    assert resp.status_code == 200
    extras = resp.json()["extras"]
    assert "1" in extras
    assert "2" in extras


# ---- health endpoint --------------------------------------------------------

def test_health_endpoint(client):
    resp = client.get("/civbro/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
