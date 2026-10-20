#!/usr/bin/env python3
"""
Build the browser bundle: the lab and the PREVENTION engine as one deterministic zip.

    python -m lab.tools.build_web_bundle OUT_DIR

Writes OUT_DIR/lab-bundle.zip (fixed timestamps, sorted entries) and
OUT_DIR/lab-bundle.json (sha256 of the zip and of every file).  The web page
loads the zip into Pyodide (CPython compiled to WebAssembly) and runs the same
code as the CLI; the bundle digest is shown in every report made in a browser.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import zipfile
import platform
import zlib

ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INCLUDE = ["lab", "simulation", "requirements.txt"]
SKIP_DIRS = {"__pycache__", "outputs", "web"}
SKIP_SUFFIX = (".pyc", ".docx")


def files():
    out = []
    for top in INCLUDE:
        path = os.path.join(ENGINE_ROOT, top)
        if os.path.isfile(path):
            out.append(top)
            continue
        for dirpath, dirnames, names in os.walk(path):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for n in sorted(names):
                if not n.endswith(SKIP_SUFFIX):
                    out.append(os.path.relpath(os.path.join(dirpath, n), ENGINE_ROOT).replace(os.sep, "/"))
    return sorted(out)


def build(out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    buf = io.BytesIO()
    listing = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in files():
            with open(os.path.join(ENGINE_ROOT, rel), "rb") as f:
                data = f.read().replace(b"\r\n", b"\n")
            listing[rel] = hashlib.sha256(data).hexdigest()
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.internal_attr = 0
            z.writestr(info, data, compresslevel=9)
    data = buf.getvalue()
    meta = {"bundle_sha256": hashlib.sha256(data).hexdigest(), "files": len(listing), "listing": listing,
            "environment": {"python": platform.python_version(), "zlib": zlib.ZLIB_VERSION,
                            "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION, "compression_level": 9,
                            "create_system": 3, "external_attr": 0o100644 << 16}}
    with open(os.path.join(out_dir, "lab-bundle.zip"), "wb") as f:
        f.write(data)
    with open(os.path.join(out_dir, "lab-bundle.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(meta, indent=1, sort_keys=True) + "\n")
    return meta


if __name__ == "__main__":
    m = build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ENGINE_ROOT, "lab", "web", "dist"))
    print(f"bundle {m['bundle_sha256']} ({m['files']} files)")
