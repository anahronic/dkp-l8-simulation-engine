"""U2 (spec identity), U4 (finite numbers), write modes, R1 (self-contained reports)."""

import json
import os
import shutil

import pytest
import yaml

from simulation.core import manifest
from simulation.core.config import ConfigError, deep_merge, load_config, validate_config
from simulation.core.manifest import SpecSnapshotError, verify_seal
from simulation.modules.prevention.protocol_adapter import NonFiniteResultError
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import MAIN, main_config


@pytest.fixture
def tampered_specs(tmp_path, monkeypatch):
    copy_dir = tmp_path / "imports"
    shutil.copytree(manifest.SPECS_DIR, copy_dir)
    p = copy_dir / "DKP-1-PREVENTION-001.md"
    p.write_bytes(p.read_bytes() + b"\nmodified snapshot bytes\n")
    monkeypatch.setattr(manifest, "SPECS_DIR", str(copy_dir))
    return copy_dir


@pytest.mark.parametrize("write", [False, True])
def test_altered_spec_snapshot_stops_the_run(tampered_specs, tmp_path, write):
    out = tmp_path / "out"
    with pytest.raises(SpecSnapshotError, match="DKP-1-PREVENTION-001.md"):
        run_simulation(main_config(days=1, out=str(out)), write=write)
    assert not out.exists()          # nothing computed, nothing written


def test_input_uses_actual_snapshot_digests():
    specs = manifest.spec_snapshots()
    inputs = manifest.build_inputs(main_config(days=1))
    assert inputs["spec_digests"] == {k: v["sha256"] for k, v in specs["files"].items()}
    assert all(v["sha256"] == v["pinned"] for v in specs["files"].values())


def test_write_false_and_true_give_the_same_ids(tmp_path):
    a = run_simulation(main_config(days=2), write=False)
    b = run_simulation(main_config(days=2, out=str(tmp_path / "w")), write=True)
    assert a.manifest["input_id"] == b.manifest["input_id"]
    assert a.manifest["result_id"] == b.manifest["result_id"]


@pytest.mark.parametrize("text", [".nan", ".inf", "-.inf", "true"])
def test_non_finite_or_non_numeric_weight_is_rejected(text):
    cfg = load_config(MAIN)
    cfg["domain"]["channels"]["intrusion"]["weight"] = yaml.safe_load(text)
    with pytest.raises(ConfigError, match=r"intrusion\.weight: expected finite number"):
        validate_config(cfg)


def test_non_finite_pair_element_is_rejected():
    cfg = load_config(MAIN)
    cfg["oracles"]["arrival_delay_seconds"] = [0.1, float("inf")]
    with pytest.raises(ConfigError, match="arrival_delay_seconds"):
        validate_config(cfg)


def test_large_weight_without_upper_bound_still_runs():
    res = run_simulation(main_config({"domain": {"channels": {"intrusion": {"weight": 2.5}}}}, days=2), write=False)
    assert res.summary["total_spd"] > 0


def test_overflowing_aggregate_is_an_error_not_a_status():
    cfg = main_config({"domain": {"channels": {c: {"weight": 1e308} for c in load_config(MAIN)["domain"]["channels"]}},
                       "protocol": {"attribution_rule": "proportional"}}, days=2)
    with pytest.raises(NonFiniteResultError):
        run_simulation(cfg, write=False)


def test_schema_2_is_refused_with_an_explanation():
    cfg = load_config(MAIN)
    cfg["schema_version"] = 2
    with pytest.raises(ConfigError, match="tag v2.0.0"):
        validate_config(cfg)


def test_phase3_report_is_self_contained(tmp_path):
    from simulation.phase3_report import main as phase3_main
    assert phase3_main(["--days", "1", "--output-dir", str(tmp_path / "p3")]) == 0
    doc = json.loads((tmp_path / "p3" / "phase3_results.json").read_text())
    assert verify_seal(doc)
    assert set(doc["package"]) >= {"engine_version", "engine_code_digest", "spec_digests", "arguments"}
    variant = doc["scenarios"]["S11_ttl_reference"]["decision"]
    cfg = deep_merge(variant["inputs"], {"output": {"directory": str(tmp_path / "replay")}})
    replay = run_simulation(cfg, write=False)
    assert replay.manifest["input_id"] == variant["input_id"]
    assert replay.manifest["result_id"] == variant["result_id"]
    prov = json.loads((tmp_path / "p3" / "phase3_provenance.json").read_text())
    assert "elapsed_seconds" in prov and "elapsed_seconds" not in json.dumps(doc)
    doc["scenarios"]["S9_linkage_threshold"]["spd_by_linkage"]["0.5"] = 0.0
    assert not verify_seal(doc)


def test_comparison_report_is_self_contained():
    from simulation.compare_candidates import compare
    rep = compare(main_config(days=1), {"prop": {"protocol": {"attribution_rule": "proportional"}}}, [3])
    assert verify_seal(rep)
    row = next(iter(rep["candidates"].values()))
    seed = rep["seeds"][0]
    cfg = deep_merge(row["config"], {"simulation": {"seed": seed}, "output": {"directory": "unused"}})
    replay = run_simulation(cfg, write=False)
    assert replay.manifest["result_id"] == row["per_seed"][str(seed)]["result_id"]
