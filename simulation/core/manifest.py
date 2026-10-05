"""
Run manifest — identifies what was computed, from what, and where.

GPT/Claude audit exchange (2026-10-05, L3): inputs, the reproducible result
core, provenance and diagnostics are kept apart.

    inputs       config digest (output path excluded), seed, scenario id,
                 engine version, engine code digest, spec snapshot digests
                 → input_id
    result core  digests of metrics.jsonl, metrics.csv, cbf_baselines.json,
                 summary.json → result_id
    provenance   Python, platform, git commit (who/where; not in either id)
    diagnostics  run_log.json: elapsed time, output path (never digested)

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
from typing import Any, Dict, List, Optional

from simulation import __version__
from simulation.core.config import canonical_json, config_digest, sha256_text

ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM_ROOT = os.path.join(ENGINE_ROOT, "simulation")
SPECS_DIR = os.path.join(SIM_ROOT, "specs", "imports")
RESULT_CORE_FILES = ("metrics.jsonl", "metrics.csv", "cbf_baselines.json", "summary.json")

UNVERIFIED = [
    "independent reproduction by other executors (SIMULATION §8)",
    "platforms other than those recorded in README 'Verified environments'",
    "zero-knowledge proof verification (PREVENTION §8): placeholder only",
    "causal inference: attribution claims and linkage observations are scenario inputs",
    "any domain other than the synthetic childcare scenario",
    "use of outputs for operational decisions (EPISTEMIC-BOUNDARIES §5.x)",
]


def _normalized_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


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
    """Spec snapshots pinned by MANIFEST.json; each digest re-verified now."""
    with open(os.path.join(SPECS_DIR, "MANIFEST.json"), "r", encoding="utf-8") as f:
        manifest = json.load(f)
    out: Dict[str, Any] = {"source": manifest["source"], "files": {}}
    for name, meta in sorted(manifest["files"].items()):
        actual = sha256_file(os.path.join(SPECS_DIR, name), normalize_newlines=True)
        out["files"][name] = {"sha256": meta["sha256"], "verified": actual == meta["sha256"]}
    return out


def git_provenance() -> Dict[str, Optional[Any]]:
    def git(*args: str) -> Optional[str]:
        try:
            res = subprocess.run(["git", "-C", ENGINE_ROOT, *args], capture_output=True,
                                 text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return res.stdout.strip() if res.returncode == 0 else None

    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain", "--", "simulation", "tests")
    return {"git_commit": commit, "git_dirty": None if status is None else bool(status)}


def build_inputs(cfg: Dict[str, Any]) -> Dict[str, Any]:
    specs = spec_snapshots()
    return {
        "scenario_id": cfg["scenario"]["id"],
        "seed": cfg["simulation"]["seed"],
        "config_digest": config_digest(cfg),
        "engine_version": __version__,
        "engine_code_digest": engine_code_digest()["sha256"],
        "spec_digests": {k: v["sha256"] for k, v in specs["files"].items()},
    }


def build_manifest(cfg: Dict[str, Any], output_dir: str, hypotheses: List[Dict[str, Any]],
                   cli_overrides: Dict[str, Any]) -> Dict[str, Any]:
    inputs = build_inputs(cfg)
    specs = spec_snapshots()
    core = {name: sha256_file(os.path.join(output_dir, name)) for name in RESULT_CORE_FILES}
    return {
        "schema": "dkp-l8-manifest/1",
        "input_id": sha256_text(canonical_json(inputs)),
        "inputs": inputs,
        "result_id": sha256_text(canonical_json(core)),
        "result_core": core,
        "provenance": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "byteorder": sys.byteorder,
            **git_provenance(),
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
