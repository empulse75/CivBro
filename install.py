from __future__ import annotations

import importlib.util
import platform
import shutil
import subprocess
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path

from packaging.version import parse

import_name = {"py-cpuinfo": "cpuinfo", "protobuf": "google.protobuf"}

EXTENSION_DIR = Path(__file__).parent.resolve()
BACKEND_DIR = EXTENSION_DIR / "backend"
RUST_DIR = EXTENSION_DIR / "core_rust"


def is_installed(
    package: str,
    min_version: str | None = None,
    max_version: str | None = None,
) -> bool:
    name = import_name.get(package, package)
    try:
        spec = importlib.util.find_spec(name)
    except ModuleNotFoundError:
        return False

    if spec is None:
        return False

    if not min_version and not max_version:
        return True

    if not min_version:
        min_version = "0.0.0"
    if not max_version:
        max_version = "99999999.99999999.99999999"

    try:
        installed = pkg_version(package)
        return parse(min_version) <= parse(installed) <= parse(max_version)
    except Exception:
        return False


def run_pip(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", *args],
        check=True,
    )


def install_pip_deps() -> None:
    requirements_txt = BACKEND_DIR / "requirements.txt"
    if not requirements_txt.exists():
        print("[CivBro] requirements.txt not found, skipping pip install")
        return

    pkgs = []
    with open(requirements_txt) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pkg = line
            try:
                parts = pkg.split(">=", 1)
                if len(parts) == 2:
                    name = parts[0]
                    min_ver = parts[1]
                    if not is_installed(name, min_ver):
                        pkgs.append(pkg)
                    continue
                parts = pkg.split("==", 1)
                if len(parts) == 2:
                    name = parts[0]
                    ver = parts[1]
                    if not is_installed(name, ver, ver):
                        pkgs.append(pkg)
                    continue
                parts = pkg.split("<=", 1)
                if len(parts) == 2:
                    name = parts[0]
                    max_ver = parts[1]
                    if not is_installed(name, None, max_ver):
                        pkgs.append(pkg)
                    continue
                if not is_installed(pkg):
                    pkgs.append(pkg)
            except Exception:
                pkgs.append(pkg)

    if pkgs:
        run_pip(*pkgs)


def build_rust_core() -> None:
    if not RUST_DIR.exists():
        print("[CivBro] Rust core directory not found, skipping build")
        return

    cargo_toml = RUST_DIR / "Cargo.toml"
    if not cargo_toml.exists():
        print("[CivBro] Cargo.toml not found, skipping Rust build")
        return

    cargo = shutil.which("cargo")
    if cargo is None:
        print("[CivBro] cargo not found on PATH, skipping Rust build")
        return

    ext = ".so"
    if platform.system() == "Windows":
        ext = ".pyd"
    elif platform.system() == "Darwin":
        ext = ".dylib"

    lib_name = f"civbro_core{ext}"
    dest_lib = BACKEND_DIR / "src" / lib_name

    if dest_lib.exists():
        try:
            sys.path.insert(0, str(BACKEND_DIR / "src"))
            import civbro_core
            civbro_core.Database()
            print(f"[CivBro] Rust core already built and working, skipping build")
            return
        except Exception:
            print("[CivBro] Existing .so not compatible, rebuilding...")

    env = {}
    env.update(subprocess.os.environ)
    python_path = Path(sys.executable).resolve()
    env["PYO3_PYTHON"] = str(python_path)
    print(f"[CivBro] Building with Python: {python_path}")

    print("[CivBro] Building Rust core with cargo...")
    try:
        subprocess.run(
            [cargo, "build", "--release"],
            cwd=str(RUST_DIR),
            env=env,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"[CivBro] Rust build failed: {e}")
        return

    target_dir = RUST_DIR / "target" / "release"
    src_lib = target_dir / lib_name

    if not src_lib.exists():
        possible = list(target_dir.glob(f"*civbro_core*{ext}*"))
        if possible:
            src_lib = possible[0]
        else:
            print(f"[CivBro] Built library not found at {src_lib}")
            return

    dest_dir = BACKEND_DIR / "src"
    dest_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(str(src_lib), str(dest_lib))
    print(f"[CivBro] Rust core built and copied to {dest_lib}")


def install() -> None:
    print("[CivBro] Installing dependencies...")
    install_pip_deps()
    build_rust_core()
    print("[CivBro] Installation complete.")


try:
    import launch

    skip_install = launch.args.skip_install
except Exception:
    skip_install = False

if not skip_install:
    install()
