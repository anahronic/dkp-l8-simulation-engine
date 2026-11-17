"""Independent reproduction (DKP-8-SIMULATION-001 §8 "reproducible by independent nodes", §11 deterministic,
exposed, re-executable).

A reproduction package is a ZIP with everything needed to re-run one deterministic bench run: the resolved inputs,
the expected ``input_id``/``result_id``, the engine commit and code digest, instructions and SHA256SUMS.  Verifying
it re-runs the bench and writes a reproduction record ``dkp-l8-reproduction/1``.

Independence levels (only R3 and R4 count as an *independent node* for §8):

* R0 — same process (a re-run, proves nothing about independence);
* R1 — same host, fresh process;
* R2 — different host or OS, same operator (e.g. the CI matrix);
* R3 — a different operator registered as a node in the trust store, record signed with the node key;
* R4 — R3 with an independent implementation of the model.

The canonical trust store registers no node, so today no record reaches R3: §8 independence is NOT_ESTABLISHED.
"""
from __future__ import annotations

import hashlib
import io
import json
import platform
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from dkp8 import trust
from dkp8.canonical import canonical

PACKAGE_SCHEMA = "dkp-l8-repro-package/1"
RECORD_SCHEMA = "dkp-l8-reproduction/1"
LEVELS = {"R0": "same process", "R1": "same host, fresh process", "R2": "different host or OS, same operator",
          "R3": "different registered operator (signed node record)", "R4": "R3 with an independent implementation"}
ROOT = Path(__file__).resolve().parents[1]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def host_fingerprint() -> str:
    return _sha(("|".join((platform.node(), platform.system(), platform.machine()))).encode())[:16]


def _engine_commit() -> Optional[str]:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def _bench(cfg: Dict[str, Any]):
    from simulation.run_prevention_simulation import run_simulation
    return run_simulation(cfg, write=False)


def make_package(config_path: Optional[str], out_path: str) -> Dict[str, Any]:
    """Run the bench once and pack the reproduction package (``config_path`` None = the smoke scenario)."""
    from simulation.core.config import load_config, run_inputs
    from simulation.run_prevention_simulation import SMOKE_CONFIG
    cfg = load_config(config_path or SMOKE_CONFIG)
    cfg.setdefault("output", {"directory": "simulation/outputs/repro"})
    manifest = _bench(cfg).manifest
    inputs = json.dumps(run_inputs(cfg), sort_keys=True, indent=1).encode()
    package = {"schema": PACKAGE_SCHEMA, "expected": {"input_id": manifest["input_id"], "result_id": manifest["result_id"],
               "result_core": manifest["result_core"]}, "engine_commit": _engine_commit(),
               "engine": manifest["inputs"].get("engine"), "scenario": cfg["scenario"]["id"],
               "synthetic": cfg["scenario"].get("synthetic", True), "operational_use": False,
               "made_on_host": host_fingerprint(), "levels": LEVELS}
    files = {
        "config_resolved.json": inputs,
        "expected_manifest.json": json.dumps(manifest, sort_keys=True, indent=1).encode(),
        "package.json": json.dumps(package, sort_keys=True, indent=1).encode(),
        "REPRODUCE.md": (
            "# Reproduce this DKP L8 bench run\n\n"
            f"Scenario `{package['scenario']}` (synthetic: {package['synthetic']}). Engine commit "
            f"`{package['engine_commit']}`.\n\n"
            "1. Check out the engine repository at that commit (anahronic/dkp-l8-simulation-engine).\n"
            "2. `python -m dkp8 repro verify <this zip> --operator <name>` (add `--node-key <file>` if you are a "
            "registered node).\n"
            f"3. The run must give input_id `{manifest['input_id']}` and result_id `{manifest['result_id']}`.\n\n"
            "Any difference is a reproduction mismatch (DKP-8-SIMULATION-001 §11). Synthetic scenario: the result is "
            "research evidence, not an operational output.\n").encode(),
    }
    sums = "".join(f"{_sha(data)}  {name}\n" for name, data in sorted(files.items())).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted({**files, "SHA256SUMS": sums}.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))   # fixed time: byte-stable package
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    Path(out_path).write_bytes(buffer.getvalue())
    return {"package": out_path, "sha256": _sha(buffer.getvalue()), **package["expected"]}


def read_package(path: str) -> Dict[str, Any]:
    data = Path(path).read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        files = {n: z.read(n) for n in z.namelist()}
    expected_sums = {line.split("  ", 1)[1]: line.split("  ", 1)[0]
                     for line in files["SHA256SUMS"].decode().splitlines() if line}
    for name, digest_hex in expected_sums.items():
        if _sha(files[name]) != digest_hex:
            raise ValueError(f"package file {name} does not match SHA256SUMS")
    pkg = json.loads(files["package.json"])
    if pkg.get("schema") != PACKAGE_SCHEMA:
        raise ValueError("not a DKP L8 reproduction package")
    pkg["config"] = json.loads(files["config_resolved.json"])
    pkg["package_sha256"] = _sha(data)
    return pkg


def verify_package(path: str, operator: str, level: str = "R1", node_secret: Optional[bytes] = None,
                   at: str = "1970-01-01T00:00:00Z") -> Dict[str, Any]:
    """Re-run the packaged inputs and return a reproduction record (signed when ``node_secret`` is given)."""
    if level not in LEVELS:
        raise ValueError(f"level must be one of {list(LEVELS)}")
    if level in ("R3", "R4") and node_secret is None:
        raise ValueError("R3/R4 need a registered node key; the record must be signed")
    pkg = read_package(path)
    cfg = dict(pkg["config"])
    cfg["output"] = {"directory": "simulation/outputs/repro-verify"}
    manifest = _bench(cfg).manifest
    if level in ("R0", "R1", "R2"):
        level = "R1" if host_fingerprint() == pkg["made_on_host"] and level != "R0" else level
    body = {"result_id_expected": pkg["expected"]["result_id"], "result_id_observed": manifest["result_id"],
            "input_id_expected": pkg["expected"]["input_id"], "input_id_observed": manifest["input_id"],
            "package_sha256": pkg["package_sha256"], "engine_commit": _engine_commit(),
            "platform": {"system": platform.system(), "machine": platform.machine(), "python": platform.python_version(),
                         "host": host_fingerprint()},
            "operator": operator, "level": level, "at": at,
            "match": manifest["result_id"] == pkg["expected"]["result_id"] and manifest["input_id"] == pkg["expected"]["input_id"]}
    record = {"schema": RECORD_SCHEMA, "body": body, "signature": None}
    if node_secret is not None:
        record["signature"] = trust.sign_document(body, node_secret)
    return record


def assess(records: Iterable[Dict[str, Any]], store: Dict[str, Any], result_ids: Iterable[Optional[str]] = ()) -> Dict[str, Any]:
    """Count reproductions by level and independent nodes (§8); report mismatches (§11)."""
    wanted = {r for r in result_ids if r}
    levels: Dict[str, int] = {}
    nodes, test_nodes, mismatches, rejected = set(), set(), [], []
    for rec in records:
        body = (rec or {}).get("body") or {}
        if rec.get("schema") != RECORD_SCHEMA or body.get("level") not in LEVELS:
            rejected.append("malformed reproduction record")
            continue
        if wanted and body.get("result_id_expected") not in wanted:
            rejected.append(f"record for another run {str(body.get('result_id_expected'))[:12]}")
            continue
        levels[body["level"]] = levels.get(body["level"], 0) + 1
        if body.get("result_id_observed") != body.get("result_id_expected"):
            mismatches.append(f"{body.get('operator')}: {str(body.get('result_id_observed'))[:12]} != "
                              f"{str(body.get('result_id_expected'))[:12]}")
            continue
        if body["level"] in ("R3", "R4"):
            verdict = trust.verify_signature(body, rec.get("signature"), store)
            kid = (rec.get("signature") or {}).get("key_id")
            is_node = any(n["node_id"] == kid for n in store.get("nodes", []))
            if verdict == trust.VALID_AUTHORITY and is_node:
                nodes.add(kid)
            elif verdict == trust.VALID_TEST_ONLY and is_node and store.get("allow_test_identities"):
                test_nodes.add(kid)
            else:
                rejected.append(f"{body.get('operator')}: {body['level']} claim without a valid registered node signature ({verdict})")
    return {"levels": levels, "independent_nodes": len(nodes) + len(test_nodes), "authority_nodes": len(nodes),
            "test_identity_nodes": len(test_nodes), "mismatches": mismatches, "rejected": rejected}


def record_digest(record: Dict[str, Any]) -> str:
    return _sha(canonical(record))
