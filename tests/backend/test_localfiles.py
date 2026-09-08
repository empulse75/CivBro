"""Local-file domain logic: delete base-name reconstruction (1.2) and the
Rust-optional file-status builder (1.3)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest


def test_model_base_from_info_strips_both_suffixes():
    from civbro_backend.localfiles import model_base_from_info

    info = Path("/models/Lora/mymodel.civitai.info")
    assert model_base_from_info(info) == Path("/models/Lora/mymodel")


def test_model_base_from_info_matches_sidecar_writer():
    """The base derived for deletion must equal the base the sidecar writer used:
    Path('mymodel.safetensors').with_suffix('') -> 'mymodel'."""
    from civbro_backend.localfiles import model_base_from_info

    download_path = Path("/models/Lora/mymodel.safetensors")
    written_sidecar = str(download_path.with_suffix("")) + ".civitai.info"
    assert model_base_from_info(Path(written_sidecar)) == download_path.with_suffix("")


def test_delete_removes_model_and_sidecars(client, models_root):
    target = models_root / "Lora" / "mymodel"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = b"weights"
    (target.with_suffix(".safetensors")).write_bytes(payload)
    (target.with_suffix(".civitai.info")).write_text(
        json.dumps({"id": 123, "modelId": 456}), encoding="utf-8"
    )
    (target.with_suffix(".json")).write_text("{}", encoding="utf-8")
    preview = target.parent / "mymodel.preview.png"
    preview.write_bytes(b"png")

    resp = client.delete("/civbro/api/local/delete", params={"model_id": 456})
    assert resp.status_code == 200, resp.text
    assert resp.json()["removed"] >= 3
    assert not target.with_suffix(".safetensors").exists()
    assert not target.with_suffix(".civitai.info").exists()
    assert not preview.exists()


def test_delete_ignores_other_models(client, models_root):
    keep = models_root / "Lora" / "keepme.safetensors"
    keep.parent.mkdir(parents=True, exist_ok=True)
    keep.write_bytes(b"weights")
    (models_root / "Lora" / "keepme.civitai.info").write_text(
        json.dumps({"id": 1, "modelId": 999}), encoding="utf-8"
    )

    resp = client.delete("/civbro/api/local/delete", params={"model_id": 456})
    assert resp.status_code == 200
    assert keep.exists()


def _version_payload(name: str, size: int, sha256: str) -> dict:
    return {
        "model": {"type": "LORA"},
        "files": [
            {
                "id": 42,
                "name": name,
                "sizeKB": size // 1024,
                "type": "Model",
                "hashes": {"SHA256": sha256},
            }
        ],
    }


def test_build_file_status_marks_installed(models_root):
    from civbro_backend.localfiles import build_file_status

    payload = b"x" * 2048
    digest = hashlib.sha256(payload).hexdigest()
    f = models_root / "Lora" / "mylora.safetensors"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(payload)

    out = build_file_status(
        _version_payload("mylora.safetensors", len(payload), digest),
        trpc={},
        models_root=str(models_root),
        verify=1,
        rust_available=False,  # must NOT crash without civbro_core (finding 1.3)
    )
    assert out[0]["status"] == "installed"
    assert out[0]["hashOk"] is None  # hash verify skipped without Rust


def test_build_file_status_detects_missing_and_incomplete(models_root):
    from civbro_backend.localfiles import build_file_status

    out = build_file_status(
        _version_payload("ghost.safetensors", 4096, ""),
        trpc={},
        models_root=str(models_root),
        verify=0,
        rust_available=False,
    )
    assert out[0]["status"] == "missing"

    small = models_root / "Lora" / "ghost.safetensors"
    small.parent.mkdir(parents=True, exist_ok=True)
    small.write_bytes(b"tiny")
    out = build_file_status(
        _version_payload("ghost.safetensors", 10 * 1024 * 1024, ""),
        trpc={},
        models_root=str(models_root),
        verify=0,
        rust_available=False,
    )
    assert out[0]["status"] == "incomplete"


def test_filestatus_route_works_without_rust(client, monkeypatch):
    """End-to-end: route must not raise ImportError when civbro_core is absent."""
    import civbro_backend.routes_local as routes_local
    import civbro_backend.localfiles as localfiles

    monkeypatch.setattr(routes_local, "RUST_AVAILABLE", False)
    monkeypatch.setattr(localfiles, "RUST_AVAILABLE", False, raising=False)

    class _Resp:
        status_code = 200

        def json(self):
            return _version_payload("routecheck.safetensors", 2048, "")

    async def _fake_get(url, **kw):
        return _Resp()

    monkeypatch.setattr(routes_local, "http_get_with_retry", _fake_get)

    async def _fake_trpc(version_id, api_key=""):
        return {}

    monkeypatch.setattr(routes_local, "fetch_trpc_version_detail", _fake_trpc)

    resp = client.get("/civbro/api/local/filestatus", params={"version_id": 1})
    assert resp.status_code == 200, resp.text
    assert resp.json()["files"][0]["name"] == "routecheck.safetensors"
    assert resp.json()["files"][0]["status"] == "missing"


def test_installed_scan_reflects_a_rewritten_sidecar(models_root):
    """Sidecar reads are memoized on mtime+size, so an edited sidecar must not
    keep reporting the version it used to name. The models root is shared by
    the whole session, so assertions are relative to the current library."""
    from civbro_backend.localfiles import scan_installed

    before = scan_installed(str(models_root))
    sidecar = models_root / "Lora" / "swapped.civitai.info"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps({"id": 111, "modelId": 222}), encoding="utf-8")
    after_create = scan_installed(str(models_root))
    assert 111 in after_create[0] and 222 in after_create[1]
    assert 111 not in before[0] and 222 not in before[1]

    # Different byte length as well as new ids: the memo key is mtime+size.
    sidecar.write_text(
        json.dumps({"id": 333, "modelId": 444, "note": "rewritten"}), encoding="utf-8"
    )
    after_rewrite = scan_installed(str(models_root))
    assert 111 not in after_rewrite[0] and 333 in after_rewrite[0]
    assert 444 in after_rewrite[1]

    sidecar.unlink()
    after_delete = scan_installed(str(models_root))
    assert 333 not in after_delete[0] and 444 not in after_delete[1]


def test_local_models_types_each_directory_independently(models_root):
    """The directory -> type lookup is cached per directory; a cache that leaked
    across sibling directories would mislabel every category after the first."""
    from civbro_backend.config import TYPE_BY_DIR
    from civbro_backend.localfiles import scan_local_models

    for category, filename in (
        ("Lora", "a_lora.safetensors"),
        ("Stable-diffusion", "b_ckpt.safetensors"),
        ("VAE", "c_vae.safetensors"),
    ):
        path = models_root / category / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"w")
    nested = models_root / "Lora" / "styles" / "d_nested.safetensors"
    nested.parent.mkdir(parents=True, exist_ok=True)
    nested.write_bytes(b"w")


    by_name = {m["name"]: m for m in scan_local_models(str(models_root), TYPE_BY_DIR)}
    assert by_name["a_lora"]["type"] == "LORA"
    assert by_name["b_ckpt"]["type"] == "Checkpoint"
    assert by_name["c_vae"]["type"] == "VAE"
    assert by_name["d_nested"]["type"] == "LORA"
    assert by_name["a_lora"]["size"] == 1


def test_local_models_lists_a_hardlinked_file_once(models_root):
    """Deduplication keys on (device, inode), so one file reachable under two
    names must be listed once. The models root is shared by the whole session,
    so only this test's own basenames are inspected."""
    from civbro_backend.config import TYPE_BY_DIR
    from civbro_backend.localfiles import scan_local_models

    original = models_root / "Lora" / "once.safetensors"
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b"weights")
    link = models_root / "Lora" / "styles" / "alias.safetensors"
    link.parent.mkdir(parents=True, exist_ok=True)
    os.link(original, link)

    listed = {
        Path(m["path"]).name
        for m in scan_local_models(str(models_root), TYPE_BY_DIR)
        if Path(m["path"]).name in ("once.safetensors", "alias.safetensors")
    }
    assert len(listed) == 1