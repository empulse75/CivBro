"""License ingestion endpoint tests."""
from __future__ import annotations


VALID_LICENSE_KEY = (
    "CIVBRO-eyJpc3N1ZWRfYXQiOjE3ODU3NTg0MDAsImxpY2Vuc2VfaWQiOiJ0ZXN0LWZpeHR1cmUifQ."
    "E0ZCyZJTbKl9WFIiUJ1Rhm544GmNfyGnX7h7wwbl3iTnW_63ou_P7kUmkch2rpNqZp_jENgdzFzFjpqej1xcDg"
)


def test_ingest_valid_license(client):
    resp = client.post("/civbro/api/license/ingest", json={"key": VALID_LICENSE_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_ingest_empty_key_rejected(client):
    resp = client.post("/civbro/api/license/ingest", json={"key": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "empty" in data["message"].lower()


def test_ingest_invalid_key_rejected(client):
    resp = client.post(
        "/civbro/api/license/ingest",
        json={"key": "CIVBRO-ABCD1234EFGH-000000000000-QRST9012UVWX-123456789012"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "invalid"


def test_ingest_missing_key_field(client):
    resp = client.post("/civbro/api/license/ingest", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"


def test_ingest_non_civbro_key_rejected(client):
    resp = client.post(
        "/civbro/api/license/ingest",
        json={"key": "NOT-CIVBRO-ABCD1234EFGH-5678IJKLMNOP-QRST9012UVWX-123456789012"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "invalid"
