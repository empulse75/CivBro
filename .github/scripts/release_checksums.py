"""Generate source provenance and wheel checksums for a versioned GitHub release."""
from __future__ import annotations

import hashlib
import os
import runpy
import sys
from pathlib import Path


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    output = Path(sys.argv[1])
    wheels = sorted(output.glob("*.whl"))
    if not wheels:
        raise SystemExit("No wheels to publish")
    # Loading installer helpers must never install into the release runner.
    os.environ["CIVBRO_SKIP_INSTALL"] = "1"
    installer = runpy.run_path(str(root / "install.py"))
    fingerprint = installer["compute_source_fingerprint"](root / "core_rust")
    source_file = output / "SOURCE_SHA256"
    source_file.write_text(fingerprint + "\n", encoding="ascii", newline="\n")
    files = sorted([*wheels, source_file])
    sums = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files)
    (output / "SHA256SUMS").write_text(sums, encoding="ascii", newline="\n")
    print(f"Prepared {len(wheels)} wheel checksums; source SHA256 {fingerprint}")
