"""Settings endpoint hardening (review finding 1.4): sensitive values are
write-only and unknown keys are rejected."""
from __future__ import annotations

import json


def test_api_key_is_never_returned_by_get_all(client):
    resp = client.post(
        "/civbro/api/settings/_all",
        json={"value": json.dumps({"civitaiRedApiKey": "secret-key-123"})},
    )
    assert resp.status_code == 200, resp.text

    resp = client.get("/civbro/api/settings/_all")
    assert resp.status_code == 200
    settings = resp.json()["settings"]
    assert "civitaiRedApiKey" not in settings
    assert "secret-key-123" not in json.dumps(settings)



def test_get_all_reports_api_key_presence_without_disclosing_value(client):
    client.post(
        "/civbro/api/settings/_all",
        json={"value": json.dumps({"civitaiRedApiKey": "secret-key-123"})},
    )

    data = client.get("/civbro/api/settings/_all").json()

    assert data["capabilities"]["hasCivitaiRedApiKey"] is True
    assert "secret-key-123" not in json.dumps(data)


def test_get_all_reports_false_capability_without_rust(monkeypatch, models_root):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import civbro_backend.routes_settings as routes_settings

    monkeypatch.setattr(routes_settings, "DB", None)
    app = FastAPI()
    routes_settings.register_settings_routes(app)

    data = TestClient(app).get("/civbro/api/settings/_all").json()

    assert data == {
        "settings": {},
        "capabilities": {"hasCivitaiRedApiKey": False},
    }



def test_api_key_is_never_returned_by_get_single(client):
    client.post(
        "/civbro/api/settings/_all",
        json={"value": json.dumps({"civitaiRedApiKey": "secret-key-123"})},
    )
    resp = client.get("/civbro/api/settings/civitaiRedApiKey")
    assert resp.status_code == 200
    assert "secret-key-123" not in resp.text


def test_unknown_keys_are_rejected(client):
    resp = client.post(
        "/civbro/api/settings/_all",
        json={"value": json.dumps({"evilKey": "payload"})},
    )
    assert resp.status_code == 200
    resp = client.get("/civbro/api/settings/evilKey")
    assert resp.json()["value"] is None


def test_allowed_keys_roundtrip(client):
    resp = client.post(
        "/civbro/api/settings/_all",
        json={
            "value": json.dumps(
                {"showNsfw": True, "defaultSort": "Newest", "nsfwBlur": False}
            )
        },
    )
    assert resp.status_code == 200
    settings = client.get("/civbro/api/settings/_all").json()["settings"]
    assert settings["showNsfw"] is True
    assert settings["defaultSort"] == "Newest"
    assert settings["nsfwBlur"] is False


def test_stored_api_key_still_usable_internally(client):
    """Redaction is a presentation concern only — the backend must still read it."""
    from civbro_backend.client import get_civitai_key

    client.post(
        "/civbro/api/settings/_all",
        json={"value": json.dumps({"civitaiRedApiKey": "secret-key-123"})},
    )
    assert get_civitai_key() == "secret-key-123"
