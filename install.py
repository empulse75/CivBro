"""Install CivBro into the active WebUI interpreter without changing its framework.

Release wheels avoid compiler requirements on supported systems. Other systems
build the same source locally; failures propagate to the host extension loader
and never print a misleading readiness message.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import urllib.error
import urllib.request
import venv
from pathlib import Path

EXTENSION_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EXTENSION_DIR / "backend"
BACKEND_SRC = BACKEND_DIR / "civbro_backend"
RUST_DIR = EXTENSION_DIR / "core_rust"
FRONTEND_DIST = EXTENSION_DIR / "frontend" / "dist"
RELEASE_TAG = "v1.0.0"
RELEASE_BASE_URL = f"https://github.com/empulse75/CivBro/releases/download/{RELEASE_TAG}"
PROTECTED_HOST_PACKAGES = (
    "fastapi", "starlette", "gradio", "gradio-client", "torch", "torchvision",
    "torchaudio", "pydantic", "pydantic-core", "uvicorn", "numpy",
)
IMPORT_NAME = {"python-multipart": "multipart", "protobuf": "google.protobuf"}


def _launch_module():
    try:
        import launch
    except ImportError:
        return None
    return launch


def _skip_install() -> bool:
    launch = _launch_module()
    return (
        os.environ.get("CIVBRO_SKIP_INSTALL", "").lower() in ("1", "true")
        or "--skip-install" in sys.argv
        or bool(getattr(getattr(launch, "args", None), "skip_install", False))
    )


def _check_system_environment() -> None:
    if sys.version_info < (3, 10) or sys.implementation.name != "cpython":
        raise RuntimeError("CivBro requires CPython >= 3.10.")
    # A free-threaded binary with its GIL temporarily enabled still cannot load abi3.
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        raise RuntimeError("CivBro requires a GIL-enabled CPython build, not free-threaded Python.")
    if platform.system() not in ("Linux", "Darwin", "Windows"):
        raise RuntimeError(f"Unsupported operating system: {platform.system()}")


def _pip(
    args: list[str],
    *,
    python: str = sys.executable,
    protect_host: bool = True,
    env: dict[str, str] | None = None,
) -> None:
    # Never feed requirement specifiers or paths into the host's shell-based
    # run_pip helper: markers, '<', spaces and apostrophes must remain literal.
    #
    # Every flag here must be valid for BOTH pip and uv: Forge Neo's --uv mode
    # patches subprocess.run (modules_forge/uv_hook.py) to rewrite
    # "python -m pip <args>" into "uv pip <args>" verbatim, stripping only its
    # own BAD_FLAGS list. pip-only options such as --no-input or
    # --disable-pip-version-check therefore reach uv untouched and abort the
    # install with "unexpected argument".
    with tempfile.TemporaryDirectory(prefix="civbro-pip-") as tmp:
        cmd = [python, "-m", "pip", "install"]
        if protect_host:
            constraints = []
            for name in PROTECTED_HOST_PACKAGES:
                try:
                    constraints.append(f"{name}=={importlib.metadata.version(name)}")
                except importlib.metadata.PackageNotFoundError:
                    continue
            path = Path(tmp) / "host-constraints.txt"
            path.write_text("\n".join(constraints), encoding="utf-8")
            cmd.extend(["--constraint", str(path)])
        launch = _launch_module()
        index = getattr(launch, "index_url", None)
        if index:
            cmd.extend(["--index-url", str(index)])
        # pip honors its native config, PIP_INDEX_URL and proxy environment;
        # uv the UV_* equivalents and VIRTUAL_ENV for target discovery.
        subprocess.run([*cmd, *args], check=True, env=env)


def install_pip_deps() -> None:
    requirements_file = BACKEND_DIR / "requirements.txt"
    if not requirements_file.is_file():
        raise RuntimeError(f"Missing required dependency manifest: {requirements_file}")
    if importlib.util.find_spec("packaging") is None:
        _pip(["packaging"])
        importlib.invalidate_caches()
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    requirements = [
        Requirement(line.split("#", 1)[0].strip())
        for line in requirements_file.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]
    active = [r for r in requirements if not r.marker or r.marker.evaluate()]
    missing = False
    for req in active:
        try:
            installed = importlib.metadata.version(req.name)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        satisfied = installed is not None and req.specifier.contains(installed, prereleases=True)
        if installed is not None and not satisfied and canonicalize_name(req.name) in PROTECTED_HOST_PACKAGES:
            raise RuntimeError(f"Requirement {req} conflicts with host {req.name}=={installed}; refusing to change the WebUI framework.")
        missing |= not satisfied or bool(req.extras)
    if missing:
        print("[CivBro] Installing dependencies into the active WebUI interpreter...", flush=True)
        _pip(["-r", str(requirements_file)])
    # Import, not find_spec: present-but-broken transitive dependencies must fail.
    modules = [IMPORT_NAME.get(r.name, r.name.replace("-", "_")) for r in active]
    code = "import importlib,sys; [importlib.import_module(name) for name in sys.argv[1:]]"
    subprocess.run([sys.executable, "-I", "-c", code, *modules], check=True)
    for req in active:
        if not req.specifier.contains(importlib.metadata.version(req.name), prereleases=True):
            raise RuntimeError(f"Dependency remains unsatisfied after pip: {req}")


def compute_source_fingerprint(rust_dir: Path) -> str:
    """Hash sorted relative POSIX names, NUL, LF-normalized bytes, NUL."""
    files = [rust_dir / name for name in ("Cargo.toml", "Cargo.lock", "pyproject.toml")]
    if any(not p.is_file() for p in files):
        raise RuntimeError("Incomplete native source tree: Cargo manifests or pyproject.toml missing")
    if (rust_dir / "build.rs").is_file():
        files.append(rust_dir / "build.rs")
    files.extend((rust_dir / "src").rglob("*.rs"))
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda p: p.relative_to(rust_dir).as_posix()):
        digest.update(path.relative_to(rust_dir).as_posix().encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


def _subprocess_smoke_test(pkg_dir: Path) -> None:
    # argv preserves Unicode, quotes and Windows backslashes; -I excludes cwd
    # and PYTHONPATH so an old globally installed core cannot mask a broken wheel.
    code = (
        "import sys,json; sys.path.insert(0,sys.argv[1]); import civbro_core as c; "
        "assert json.loads(c.parse_json_fast('{\"n\":42}')) == {'n':42}; "
        "db=c.Database(':memory:'); db.set_setting('smoke','ok'); "
        "assert db.get_setting('smoke') == 'ok'"
    )
    subprocess.run([sys.executable, "-I", "-c", code, str(pkg_dir.parent)], check=True)


def _is_existing_core_valid(dest_pkg: Path, source_fp: str) -> bool:
    try:
        metadata = json.loads((dest_pkg / ".metadata.json").read_text(encoding="utf-8"))
        if metadata.get("fingerprint") != source_fp:
            return False
        _subprocess_smoke_test(dest_pkg)
        return True
    except (OSError, ValueError, subprocess.CalledProcessError):
        return False


def _activate_wheel(wheel: Path, source_fp: str, dest_pkg: Path) -> None:
    BACKEND_SRC.mkdir(parents=True, exist_ok=True)
    # Stage on the destination filesystem, retaining the package's actual name.
    with tempfile.TemporaryDirectory(prefix=".civbro-stage-", dir=BACKEND_SRC) as tmp:
        stage = Path(tmp)
        _pip(["--no-deps", "--target", str(stage), str(wheel)], protect_host=False)
        candidate = stage / "civbro_core"
        if not candidate.is_dir():
            raise RuntimeError("Wheel did not contain the civbro_core package")
        # Keep the legal metadata shipped by maturin, not just its native binary.
        for entry in stage.iterdir():
            if entry.name.endswith(".dist-info"):
                shutil.copytree(entry, candidate / entry.name)
            elif entry.name == "THIRD_PARTY_NOTICES.txt":
                shutil.copy2(entry, candidate / entry.name)
            elif entry.name.endswith(".libs"):
                raise RuntimeError("Unexpected external shared-library layout; this wheel must bundle dependencies within civbro_core")
        (candidate / ".metadata.json").write_text(json.dumps({"fingerprint": source_fp}), encoding="utf-8")
        _subprocess_smoke_test(candidate)
        previous = stage / "previous"
        if dest_pkg.exists():
            dest_pkg.rename(previous)
        try:
            candidate.rename(dest_pkg)
            _subprocess_smoke_test(dest_pkg)
        except BaseException:
            if dest_pkg.exists():
                dest_pkg.rename(stage / "failed")
            if previous.exists():
                previous.rename(dest_pkg)
            raise
        # A package directory takes precedence over the legacy flat .so/.pyd.
        # Leave legacy binaries untouched for recovery; never unlink a loaded DLL.
    print("[CivBro] Native core installed and verified.", flush=True)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "CivBro-Installer"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def _try_install_from_wheel(dest_pkg: Path, source_fp: str) -> bool:
    from packaging.tags import sys_tags
    from packaging.utils import parse_wheel_filename

    print(f"[CivBro] Checking portable native wheels for {RELEASE_TAG}...", flush=True)
    try:
        manifest = _fetch(f"{RELEASE_BASE_URL}/SHA256SUMS").decode("ascii")
        source_bytes = _fetch(f"{RELEASE_BASE_URL}/SOURCE_SHA256")
    except (OSError, urllib.error.URLError) as exc:
        print(f"[CivBro] Release unavailable ({exc}); using a local source build.", flush=True)
        return False
    checksums = {}
    for line in manifest.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.+-]+)", line)
        if not match:
            raise RuntimeError("Malformed release checksum manifest")
        checksums[match[2]] = match[1]
    if hashlib.sha256(source_bytes).hexdigest() != checksums.get("SOURCE_SHA256"):
        raise RuntimeError("Release source checksum mismatch; refusing unverified binaries")
    if source_bytes.decode("ascii").strip() != source_fp:
        print("[CivBro] Checkout differs from release; building this checkout's source.", flush=True)
        return False
    ranks = {tag: rank for rank, tag in enumerate(sys_tags())}
    candidates = []
    for name in checksums:
        if not name.endswith(".whl"):
            continue
        distribution, version, _, tags = parse_wheel_filename(name)
        if distribution != "civbro-core" or str(version) != RELEASE_TAG.removeprefix("v"):
            continue
        compatible = [ranks[t] for t in tags if t in ranks]
        if compatible:
            candidates.append((min(compatible), name))
    if not candidates:
        print("[CivBro] No matching wheel for this OS/architecture; building locally.", flush=True)
        return False
    name = min(candidates)[1]
    print(f"[CivBro] Downloading {name}...", flush=True)
    payload = _fetch(f"{RELEASE_BASE_URL}/{name}")
    if hashlib.sha256(payload).hexdigest() != checksums[name]:
        raise RuntimeError("Native wheel checksum mismatch; refusing installation")
    with tempfile.TemporaryDirectory(prefix="civbro-wheel-") as tmp:
        wheel = Path(tmp) / name
        wheel.write_bytes(payload)
        _activate_wheel(wheel, source_fp, dest_pkg)
    return True


def _find_cargo() -> str | None:
    executable = "cargo.exe" if os.name == "nt" else "cargo"
    found = shutil.which(executable)
    if found:
        return found
    homes = [Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")), Path("/usr/local/cargo")]
    for home in homes:
        path = home / "bin" / executable
        if path.is_file():
            return str(path)
    return None


def _bootstrap_rust() -> str:
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(machine)
    system = platform.system()
    if not arch:
        raise RuntimeError(f"Install a Rust toolchain for {machine} from https://rustup.rs before retrying")
    suffix = {"Linux": "unknown-linux-gnu", "Darwin": "apple-darwin", "Windows": "pc-windows-msvc"}[system]
    binary = "rustup-init.exe" if system == "Windows" else "rustup-init"
    url = f"https://static.rust-lang.org/rustup/dist/{arch}-{suffix}/{binary}"
    print("[CivBro] Downloading the official Rust installer; installing a minimal user-local toolchain.", flush=True)
    payload = _fetch(url)
    expected = _fetch(url + ".sha256").decode("ascii").split()[0]
    if hashlib.sha256(payload).hexdigest() != expected:
        raise RuntimeError("Rust installer checksum mismatch")
    with tempfile.TemporaryDirectory(prefix="civbro-rustup-") as tmp:
        path = Path(tmp) / binary
        path.write_bytes(payload)
        path.chmod(0o700)
        subprocess.run([str(path), "-y", "--profile", "minimal", "--no-modify-path"], check=True)
    cargo = _find_cargo()
    if not cargo:
        raise RuntimeError("Rust installation completed but cargo is unavailable")
    return cargo


def _build_rust_core_source(dest_pkg: Path, source_fp: str) -> None:
    system = platform.system()
    if system != "Windows" and not any(shutil.which(c) for c in ("cc", "clang", "gcc")):
        hint = "xcode-select --install" if system == "Darwin" else "Install build-essential (Debian/Ubuntu), gcc (Fedora), or base-devel (Arch)."
        raise RuntimeError(f"A C toolchain is required when no wheel is available. {hint}")
    # MSVC is normally found by rustc/cc through the VS registry, not PATH.
    cargo = _find_cargo() or _bootstrap_rust()
    env = os.environ.copy()
    env["PATH"] = str(Path(cargo).parent) + os.pathsep + env.get("PATH", "")
    env["PYO3_PYTHON"] = sys.executable
    for key in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_TARGET"):
        env.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="civbro-build-") as tmp:
        build_root = Path(tmp)
        venv.EnvBuilder(with_pip=True).create(build_root / "venv")
        python = build_root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        # Under the uv hook the installer subprocess resolves its target
        # environment from VIRTUAL_ENV; without this pin maturin would land in
        # the host WebUI venv instead of the throwaway build venv. Real pip
        # ignores VIRTUAL_ENV, so setting it is safe for both.
        build_env = {**env, "VIRTUAL_ENV": str(build_root / "venv")}
        _pip(["maturin==1.11.5"], python=str(python), protect_host=False, env=build_env)
        output = build_root / "wheels"
        print("[CivBro] Building optimized native core (at most two parallel jobs)...", flush=True)
        try:
            subprocess.run([
                str(python), "-m", "maturin", "build", "--release", "--locked",
                "--interpreter", sys.executable, "--compatibility", "off",
                "--jobs", str(min(2, os.cpu_count() or 1)), "--out", str(output),
            ], cwd=RUST_DIR, env=env, check=True)
        except subprocess.CalledProcessError as exc:
            hint = " Install Visual Studio C++ Build Tools (MSVC and Windows SDK) if the linker is missing." if system == "Windows" else " Check the compiler diagnostics above."
            raise RuntimeError("Native core source build failed." + hint) from exc
        wheels = list(output.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("Native build did not produce exactly one wheel")
        _activate_wheel(wheels[0], source_fp, dest_pkg)


def _verify_frontend_assets() -> None:
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise RuntimeError("Missing frontend/dist/index.html; reinstall a complete CivBro checkout")
    refs = re.findall(r'(?:src|href)=["\']([^"\']+)["\']', index.read_text(encoding="utf-8"))
    local = [r for r in refs if not r.startswith(("https:", "http:", "//", "data:"))]
    if not local:
        raise RuntimeError("Frontend index contains no bundled assets")
    for ref in local:
        relative = ref.split("?", 1)[0].lstrip("/").removeprefix("civbro/")
        asset = (FRONTEND_DIST / relative).resolve()
        if not asset.is_relative_to(FRONTEND_DIST.resolve()) or not asset.is_file() or not asset.stat().st_size:
            raise RuntimeError(f"Missing or invalid frontend asset: {ref}")


def install() -> None:
    _check_system_environment()
    _verify_frontend_assets()
    install_pip_deps()
    fingerprint = compute_source_fingerprint(RUST_DIR)
    package = BACKEND_SRC / "civbro_core"
    if not _is_existing_core_valid(package, fingerprint):
        if not _try_install_from_wheel(package, fingerprint):
            _build_rust_core_source(package, fingerprint)
    print("[CivBro] Ready: Python dependencies, frontend and native core verified.", flush=True)


if __name__ == "__main__" and not _skip_install():
    install()
