"""HTTP/2 must stay an accelerator, never a hard dependency.

httpx raises ImportError from AsyncClient(http2=True) when h2 is missing, and it
raises it lazily on the first request — which surfaced to users as
"Failed to fetch models from Civitai: Using http2=True, but the 'h2' package is
not installed" for every browse, on a WebUI whose CivBro install had aborted
before it could add h2. The probe happens once at import; these tests pin the
construction behaviour for both probe outcomes.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def adapter(monkeypatch):
    import civbro_backend.http_adapter as http_adapter

    return http_adapter


def test_client_builds_without_http2_when_h2_is_missing(adapter, monkeypatch):
    monkeypatch.setattr(adapter, "_HTTP2", False)
    monkeypatch.setattr(adapter, "_HTTP_CLIENT", None)

    # The regression: with h2 absent this constructor used to raise ImportError.
    client = adapter.get_http_client()
    assert client.is_closed is False
    assert adapter._make_fresh_client() is not None


def test_client_uses_http2_when_probe_passes(adapter, monkeypatch):
    monkeypatch.setattr(adapter, "_HTTP2", True)
    monkeypatch.setattr(adapter, "_HTTP_CLIENT", None)

    assert adapter.http2_enabled() is True
    client = adapter.get_http_client()
    assert client.is_closed is False


def test_health_reports_http2_state(client):
    body = client.get("/civbro/api/health").json()
    assert body["status"] == "ok"
    assert isinstance(body["http2"], bool)
