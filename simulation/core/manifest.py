"""
Run manifest — identifies what was computed, from what, and where.

Audit exchange of 2026-10-05 (L3, U2, R1): inputs, the reproducible result
core, provenance and diagnostics are kept apart.

    inputs       config digest (output path excluded), seed, scenario id,
                 engine version, engine code digest, *actual* digests of the
                 spec snapshot bytes                              → input_id
    result core  digests of metrics.jsonl, metrics.csv, cbf_baselines.json,
                 summary.json (the exact bytes written)           → result_id
    provenance   Python, platform, git commit (who/where; not in either id)
    diagnostics  run_log.json: elapsed time, output path (never digested)

Spec snapshots are pinned by specs/imports/MANIFEST.json.  A run whose
snapshot bytes differ from the pinned digests is refused before anything is
computed (SpecSnapshotError), with or without writing files.

Two executors who obtain the same result_id from the same input_id have
reproduced the computation, whatever their platform or name.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from typing import Any, Dict, List, Mapping, Optional

from simulation import __version__
from simulation.core.config import canonical_json, config_digest, sha256_text

ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM_ROOT = os.path.join(ENGINE_ROOT, "simulation")
SPECS_DIR = os.path.join(SIM_ROOT, "specs", "imports")

UNVERIFIED = [
    "independent reproduction by other executors (SIMULATION §8)",
    "platforms other than those recorded in README 'Verified environments'",
    "zero-knowledge proof verification (PREVENTION §8): placeholder only",
    "causal inference: attribution claims and linkage observations are scenario inputs",
    "any domain other than the synthetic childcare scenario",
    "use of outputs for operational decisions (EPISTEMIC-BOUNDARIES §5.x)",
]


class SpecSnapshotError(RuntimeError):
    """Spec snapshot bytes differ from the digests pinned in MANIFEST.json."""


def _normalized_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str, normalize_newlines: bool = False) -> str:
    if normalize_newlines:
        return hashlib.sha256(_normalized_bytes(path)).hexdigest()
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def engine_code_digest() -> Dict[str, Any]:
    """Digest of the engine source (simulation/**/*.py), newline-normalized."""
    files: List[str] = []
    for dirpath, dirnames, filenames in os.walk(SIM_ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in ("__pycache__", "outputs"))
        for name in sorted(filenames):
            if name.endswith(".py"):
                files.append(os.path.join(dirpath, name))
    h = hashlib.sha256()
    for path in sorted(files, key=lambda p: os.path.relpath(p, ENGINE_ROOT).replace(os.sep, "/")):
        rel = os.path.relpath(path, ENGINE_ROOT).replace(os.sep, "/")
        h.update(rel.encode("utf-8") + b"\0")
        h.update(hashlib.sha256(_normalized_bytes(path)).digest())
    return {"sha256": h.hexdigest(), "files": len(files)}


def spec_snapshots() -> Dict[str, Any]:
    """Actual digests of the snapshot files next to the digests pinned in MANIFEST.json."""
    with open(os.path.join(SPECS_DIR, "MANIFEST.json"), "r", encoding="utf-8") as f:
        manifest = json.load(f)
    out: Dict[str, Any] = {"source": manifest["source"], "files": {}}
    for name, meta in sorted(manifest["files"].items()):
        path = os.path.join(SPECS_DIR, name)
        actual = sha256_file(path, normalize_newlines=True) if os.path.isfile(path) else None
        out["files"][name] = {"sha256": actual, "pinned": meta["sha256"], "verified": actual == meta["sha256"]}
    return out


def verified_spec_digests() -> Dict[str, str]:
    """Actual snapshot digests; raise SpecSnapshotError if any differs from its pin."""
    specs = spec_snapshots()
    bad = sorted(name for name, v in specs["files"].items() if not v["verified"])
    if bad:
        raise SpecSnapshotError(
            "spec snapshot bytes differ from specs/imports/MANIFEST.json: " + ", ".join(bad)
            + ". The engine does not run on altered normative texts; express a different "
              "reading as a declared hypothesis in the config instead.")
    return {name: v["sha256"] for name, v in specs["files"].items()}


def git_provenance() -> Dict[str, Optional[Any]]:
    def git(*args: str) -> Optional[str]:
        try:
            res = subprocess.run(["git", "-C", ENGINE_ROOT, *args], capture_output=True,
                                 text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return res.stdout.strip() if res.returncode == 0 else None

    commit = git("rev-parse", "HEAD")
    # file-mode bits are not content: on a Windows checkout seen from WSL every file looks modified
    status = git("-c", "core.fileMode=false", "status", "--porcelain", "--", "simulation", "tests")
    return {"git_commit": commit, "git_dirty": None if status is None else bool(status)}


def platform_provenance() -> Dict[str, Any]:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "byteorder": sys.byteorder,
        **git_provenance(),
    }


def engine_identity(spec_digests: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """What code and which normative texts produced a result (part of every input)."""
    return {
        "engine_version": __version__,
        "engine_code_digest": engine_code_digest()["sha256"],
        "spec_digests": spec_digests if spec_digests is not None else verified_spec_digests(),
    }


def build_inputs(cfg: Dict[str, Any], identity: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "scenario_id": cfg["scenario"]["id"],
        "seed": cfg["simulation"]["seed"],
        "config_digest": config_digest(cfg),
        **(identity if identity is not None else engine_identity()),
    }


def build_manifest(cfg: Dict[str, Any], core_bytes: Mapping[str, bytes], hypotheses: List[Dict[str, Any]],
                   cli_overrides: Dict[str, Any], identity: Dict[str, Any]) -> Dict[str, Any]:
    inputs = build_inputs(cfg, identity)
    core = {name: sha256_bytes(data) for name, data in sorted(core_bytes.items())}
    specs = spec_snapshots()
    return {
        "schema": "dkp-l8-manifest/2",
        "input_id": sha256_text(canonical_json(inputs)),
        "inputs": inputs,
        "result_id": sha256_text(canonical_json(core)),
        "result_core": core,
        "provenance": {
            **platform_provenance(),
            "spec_source": specs["source"],
            "spec_snapshots_verified": all(v["verified"] for v in specs["files"].values()),
        },
        "cli_overrides": cli_overrides,
        "hypotheses": hypotheses,
        "epistemic": {
            "scope_ref": f"scenario:{cfg['scenario']['id']}",
            "synthetic": cfg["scenario"]["synthetic"],
            "operational_use": False,
            "note": "Research-bench output on a synthetic scenario. It is not an operational "
                    "output (EPISTEMIC-BOUNDARIES §5.x) and not an admission under "
                    "DKP-8-SIMULATION-001 §8.",
        },
        "unverified": UNVERIFIED,
    }


def seal(content: Dict[str, Any]) -> Dict[str, Any]:
    """Add ``content_sha256`` = SHA-256 of canonical_json(content) where content is the
    document *without* that field.  Verify by removing the field and recomputing."""
    if "content_sha256" in content:
        raise ValueError("content already sealed")
    return dict(content, content_sha256=sha256_text(canonical_json(content)))


def verify_seal(doc: Dict[str, Any]) -> bool:
    body = {k: v for k, v in doc.items() if k != "content_sha256"}
    return doc.get("content_sha256") == sha256_text(canonical_json(body))
