"""Path-traversal jail for the download endpoint (review finding 1.1)."""
from __future__ import annotations


def _post(client, **overrides):
    body = {
        "modelId": 1,
        "versionId": 2,
        "fileId": 3,
        "fileName": "model.safetensors",
        "downloadUrl": "http://127.0.0.1:9/unreachable",
        "downloadDir": overrides.pop("downloadDir"),
        "sizeKB": 1,
        "modelType": "Checkpoint",
    }
    body.update(overrides)
    return client.post("/civbro/api/download", json=body)


def test_valid_download_inside_models_root_is_accepted(client, models_root):
    resp = _post(client, downloadDir=str(models_root / "Lora"))
    assert resp.status_code == 200, resp.text
    entry = resp.json()
    assert entry["downloadPath"].startswith(str(models_root))


def test_download_route_uses_authoritative_type_directory(client, models_root):
    resp = _post(
        client,
        downloadDir=str(models_root / "Stable-diffusion"),
        fileName="aesthetic.pt",
        fileType="Model",
        modelType="AestheticGradient",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["downloadPath"] == str(models_root / "aesthetic_embeddings" / "aesthetic.pt")


def test_download_dir_outside_models_root_is_rejected(client):
    resp = _post(client, downloadDir="/etc")
    assert resp.status_code == 400


def test_download_dir_traversal_is_rejected(client, models_root):
    resp = _post(client, downloadDir=str(models_root / ".." / ".."))
    assert resp.status_code == 400


def test_filename_with_parent_traversal_is_rejected(client, models_root):
    resp = _post(client, downloadDir=str(models_root), fileName="../../evil.safetensors")
    assert resp.status_code == 400


def test_filename_with_subdirectory_is_rejected(client, models_root):
    resp = _post(client, downloadDir=str(models_root), fileName="sub/dir/model.safetensors")
    assert resp.status_code == 400


def test_absolute_filename_is_rejected(client, models_root):
    resp = _post(client, downloadDir=str(models_root), fileName="/tmp/evil.safetensors")
    assert resp.status_code == 400


def test_backslash_filename_is_rejected(client, models_root):
    resp = _post(client, downloadDir=str(models_root), fileName="..\\evil.safetensors")
    assert resp.status_code == 400
