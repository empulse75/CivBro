"""Exercise the installed native wheel on each release OS, without a WebUI or GPU."""
from __future__ import annotations

import gc
import hashlib
import json
import runpy
import sys
import tempfile
from pathlib import Path


def exercise_core() -> None:
    import civbro_core as core

    with tempfile.TemporaryDirectory(prefix="CivBro user's unicode-") as tmp:
        root = Path(tmp)
        model = root / "modèle.SAFETENSORS"
        data = b"CivBro portable native core\n"
        model.write_bytes(data)
        assert core.compute_file_hash(str(model), "sha256") == hashlib.sha256(data).hexdigest()
        scanned = json.loads(core.scan_model_dir(str(root), ["safetensors"]))
        assert [(row["name"], row["size"]) for row in scanned] == [(model.name, len(data))]
        assert json.loads(core.parse_json_fast('{"unicode":"é","value":42}')) == {
            "unicode": "é", "value": 42,
        }
        try:
            core.parse_json_fast("not JSON")
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed JSON must raise ValueError")
        db_path = str(root / "settings.db")
        db = core.Database(db_path)
        assert db.set_setting("portable", "persisted") is True
        del db
        gc.collect()
        reopened = core.Database(db_path)
        assert reopened.get_setting("portable") == "persisted"
        del reopened
        gc.collect()
    print(f"PASS native hashing, Unicode paths, scanning, parsing and SQLite persistence: {sys.version}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        wheels = sorted(Path(sys.argv[1]).glob("*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"Expected one wheel for this platform, found {len(wheels)}")
        root = Path(__file__).resolve().parents[2]
        installer = runpy.run_path(str(root / "install.py"))
        installer["install_pip_deps"]()
        fingerprint = installer["compute_source_fingerprint"](root / "core_rust")
        package = installer["BACKEND_SRC"] / "civbro_core"
        installer["_activate_wheel"](wheels[0].resolve(), fingerprint, package)
        # The second pass must be a verified no-op, without cargo or a release.
        installer["install"]()
        sys.path.insert(0, str(package.parent))
    exercise_core()
