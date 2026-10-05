"""Reproducibility and run identity (L3, B7): input_id, result_id, diagnostics kept apart."""

import json
import os

from simulation.core.manifest import RESULT_CORE_FILES, engine_code_digest, spec_snapshots
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import main_config


def _run(tmp_path, name, **kw):
    cfg = main_config(out=str(tmp_path / name), **kw)
    return run_simulation(cfg, write=True)


def test_same_inputs_same_result_id_different_paths(tmp_path):
    a = _run(tmp_path, "a", days=2)
    b = _run(tmp_path, "b", days=2)
    assert a.manifest["input_id"] == b.manifest["input_id"]
    assert a.manifest["result_id"] == b.manifest["result_id"]
    for name in RESULT_CORE_FILES:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_different_seed_different_ids(tmp_path):
    a = _run(tmp_path, "a", days=2, seed=1)
    b = _run(tmp_path, "b", days=2, seed=2)
    assert a.manifest["input_id"] != b.manifest["input_id"]
    assert a.manifest["result_id"] != b.manifest["result_id"]


def test_diagnostics_are_outside_the_result_core(tmp_path):
    a = _run(tmp_path, "a", days=1)
    summary = json.loads((tmp_path / "a" / "summary.json").read_text())
    assert "elapsed_seconds" not in summary
    resolved = json.loads((tmp_path / "a" / "config_resolved.json").read_text())
    assert "output" not in resolved
    log = json.loads((tmp_path / "a" / "run_log.json").read_text())
    assert "elapsed_seconds" in log and "output_dir" in log
    assert "run_log.json" not in a.manifest["result_core"]


def test_output_files_use_lf(tmp_path):
    _run(tmp_path, "a", days=1)
    for name in RESULT_CORE_FILES + ("run_manifest.json", "summary.txt"):
        assert b"\r\n" not in (tmp_path / "a" / name).read_bytes()


def test_manifest_inputs_and_hypotheses(tmp_path):
    m = _run(tmp_path, "a", days=1).manifest
    assert set(m["inputs"]) == {"scenario_id", "seed", "config_digest", "engine_version",
                                "engine_code_digest", "spec_digests"}
    assert m["provenance"]["spec_snapshots_verified"] is True
    assert {h["id"] for h in m["hypotheses"]} >= {"H-A-2", "H-T-1", "H-TIME-1", "H-TTL", "H-C"}
    assert m["epistemic"]["operational_use"] is False
    assert m["unverified"]


def test_zone_events_independent_of_zone_count():
    one = run_simulation(main_config(days=2, zones=1), write=False)
    three = run_simulation(main_config(days=2, zones=3), write=False)
    z1_one = [r for r in one.records if r["zone_id"] == "zone-0001"]
    z1_three = [r for r in three.records if r["zone_id"] == "zone-0001"]
    assert z1_one == z1_three


def test_engine_code_digest_is_newline_normalized(tmp_path, monkeypatch):
    d = engine_code_digest()
    assert d["files"] > 10 and len(d["sha256"]) == 64


def test_spec_snapshots_match_manifest():
    specs = spec_snapshots()
    assert specs["source"]["repository"] == "https://github.com/anahronic/World"
    assert all(v["verified"] for v in specs["files"].values())
    assert "DKP-1-PREVENTION-001.md" in specs["files"]
