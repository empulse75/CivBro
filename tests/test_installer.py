from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("civbro_installer", Path(__file__).resolve().parents[1] / "install.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)



def test_fingerprint_ignores_checkout_line_endings_but_detects_source_changes(tmp_path):
    for name in ("Cargo.toml", "Cargo.lock", "pyproject.toml"):
        (tmp_path / name).write_bytes(b"header\nvalue\n")
    (tmp_path / "src").mkdir()
    source = tmp_path / "src/lib.rs"
    source.write_bytes(b"fn original() {}\n")
    original = installer.compute_source_fingerprint(tmp_path)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert installer.compute_source_fingerprint(tmp_path) == original
    source.write_bytes(b"fn changed() {}\n")
    assert installer.compute_source_fingerprint(tmp_path) != original


def test_incomplete_checkout_never_reports_ready(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(installer, "FRONTEND_DIST", tmp_path)
    with pytest.raises(RuntimeError, match="Missing frontend"):
        installer.install()
    assert "Ready" not in capsys.readouterr().out


def test_missing_referenced_frontend_asset_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(installer, "FRONTEND_DIST", tmp_path)
    (tmp_path / "index.html").write_text('<script src="./assets/missing.js"></script>')
    with pytest.raises(RuntimeError, match="Missing or invalid frontend asset"):
        installer._verify_frontend_assets()


def test_free_threaded_build_rejected_even_with_runtime_gil(monkeypatch):
    monkeypatch.setattr(installer.sysconfig, "get_config_var", lambda _: 1)
    with pytest.raises(RuntimeError, match="free-threaded"):
        installer._check_system_environment()


def test_old_python_rejected(monkeypatch):
    monkeypatch.setattr(installer.sys, "version_info", (3, 9, 0))
    with pytest.raises(RuntimeError, match="CPython >= 3.10"):
        installer._check_system_environment()


def test_source_asset_checksum_is_verified_before_fingerprint(monkeypatch, tmp_path):
    source = b"a" * 64 + b"\n"
    manifest = ("0" * 64 + "  SOURCE_SHA256\n").encode()
    monkeypatch.setattr(installer, "_fetch", lambda url: manifest if url.endswith("SHA256SUMS") else source)
    with pytest.raises(RuntimeError, match="source checksum mismatch"):
        installer._try_install_from_wheel(tmp_path / "civbro_core", "a" * 64)


def test_matching_source_asset_hash_does_not_replace_source_fingerprint(monkeypatch, tmp_path):
    source = b"a" * 64 + b"\n"
    manifest = (hashlib.sha256(source).hexdigest() + "  SOURCE_SHA256\n").encode()
    monkeypatch.setattr(installer, "_fetch", lambda url: manifest if url.endswith("SHA256SUMS") else source)
    assert installer._try_install_from_wheel(tmp_path / "civbro_core", "b" * 64) is False


def test_corrupt_native_wheel_is_never_activated(monkeypatch, tmp_path):
    from packaging.tags import sys_tags

    tag = next(sys_tags())
    name = f"civbro_core-1.0.0-{tag}.whl"
    source = b"a" * 64 + b"\n"
    manifest = (
        hashlib.sha256(source).hexdigest() + "  SOURCE_SHA256\n"
        + "0" * 64 + "  " + name + "\n"
    ).encode()
    assets = {"SHA256SUMS": manifest, "SOURCE_SHA256": source, name: b"corrupt wheel"}
    monkeypatch.setattr(installer, "_fetch", lambda url: assets[url.rsplit("/", 1)[1]])
    target = tmp_path / "civbro_core"
    with pytest.raises(RuntimeError, match="wheel checksum mismatch"):
        installer._try_install_from_wheel(target, "a" * 64)
    assert not target.exists()


def test_dependency_install_failure_propagates():
    with pytest.raises(subprocess.CalledProcessError):
        installer._pip(["--no-index", "not-a-valid-requirement>>>"])


def test_pip_command_is_accepted_after_forge_uv_rewrite(monkeypatch):
    # Forge Neo's --uv mode (modules_forge/uv_hook.py) rewrites every
    # "python -m pip <args>" call into "uv pip <args>". A pip-only flag
    # therefore aborts the install on those hosts with "unexpected argument".
    # Replay that exact rewrite against the real uv CLI: flag rejection is a
    # parse-time failure, so a zero exit proves the flags survived.
    if shutil.which("uv") is None:
        pytest.skip("uv not installed")
    real_run = subprocess.run

    def hooked(command, **kwargs):
        cmd = list(command)
        if "pip" in cmd:
            cmd = ["uv", "pip", *cmd[cmd.index("pip") + 1:], "--dry-run", "--offline"]
            kwargs["env"] = {**os.environ, "VIRTUAL_ENV": sys.prefix}
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(installer.subprocess, "run", hooked)
    installer._pip(["-r", str(Path(installer.BACKEND_DIR) / "requirements.txt")])


def test_pip_command_remains_valid_for_real_pip(monkeypatch):
    if subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True).returncode != 0:
        pytest.skip("pip unavailable in this interpreter")
    real_run = subprocess.run

    def dry_run(command, **kwargs):
        # All backend requirements are satisfied in the test interpreter, so
        # the dry run resolves locally without touching the network.
        return real_run([*command, "--dry-run"], check=True, capture_output=True)

    monkeypatch.setattr(installer.subprocess, "run", dry_run)
    installer._pip(["-r", str(Path(installer.BACKEND_DIR) / "requirements.txt")])


def test_uv_target_env_is_pinned_for_installer_subprocesses(monkeypatch):
    # Under the uv hook the child resolves its install target from VIRTUAL_ENV.
    # The source-build stage must therefore thread its build-venv env through;
    # losing it would silently install maturin into the host WebUI venv.
    seen = {}

    def capture(command, **kwargs):
        seen.update(command=list(command), env=kwargs.get("env"))
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(installer.subprocess, "run", capture)
    build_env = {"VIRTUAL_ENV": "/build-venv", "PATH": "/cargo-bin"}
    with pytest.raises(subprocess.CalledProcessError):
        installer._pip(["maturin==1.11.5"], python="build-python", protect_host=False, env=build_env)
    assert seen["command"][:3] == ["build-python", "-m", "pip"]
    assert seen["env"]["VIRTUAL_ENV"] == "/build-venv"
    assert seen["env"]["PATH"] == "/cargo-bin"
