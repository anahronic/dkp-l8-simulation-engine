"""PREVENTION module: the v2.1.1 bench unchanged behind the lab contract (TZ §6.1, §11.1)."""

import copy

import pytest

from lab.core.checks import FAIL, PASS
from lab.modules.prevention import PreventionModule, recheck
from simulation.run_prevention_simulation import run_simulation

# v2.1.1 pinned results (README, tests/simulation/test_golden.py, CI run 37487157576)
SMOKE_RESULT_ID = "77d06a9bcae3916123d1c5b61fb8cda4d83c682c99f6153edf006b2ec9912186"
MAIN_RESULT_ID = "e84c3979862842c8b39030dd45809bfcda491fe76753e8093428e0cf41181161"

M = PreventionModule()


def test_smoke_through_the_lab_equals_v2_1_1():
    r = M.evaluate(M.validate({}))
    assert r.outputs["bench_manifest"]["result_id"] == SMOKE_RESULT_ID


def test_main_through_the_lab_equals_v2_1_1():
    r = M.evaluate(M.validate({"base": "main", "num_days": 30, "num_zones": 3}))
    assert r.outputs["bench_manifest"]["result_id"] == MAIN_RESULT_ID


@pytest.mark.parametrize("name", ["smoke_default", "freshness_at_signal", "freshness_at_decision", "farming_undetected"])
def test_examples_have_no_failed_check(name):
    r = M.evaluate(M.validate(M.examples()[name]))
    assert not [c.requirement_id for c in r.checks if c.status == FAIL]


def test_decision_mode_loses_recognitions():
    a = M.evaluate(M.validate(M.examples()["freshness_at_signal"])).outputs["summary"]
    b = M.evaluate(M.validate(M.examples()["freshness_at_decision"])).outputs["summary"]
    assert b["by_status"]["POSITIVE"] < a["by_status"]["POSITIVE"]
    assert b["by_reason"].get("ta_stale_data_at_decision", 0) > 0


def _run():
    cfg = M.build_config(M.validate({"num_days": 5}))
    res = run_simulation(cfg, write=False)
    return res, cfg


def _status(checks, rid):
    return next(c.status for c in checks if c.requirement_id == rid)


@pytest.mark.parametrize("rid,mutate", [
    ("PREV-5-01", lambda r: r.__setitem__("SPD", r["SPD"] * 2)),
    ("PREV-3.6-02", lambda r: r["factors"].__setitem__("S", 0.123)),
    ("PREV-3.3-01", lambda r: r["ta"].__setitem__("fresh_classes", ["optical"])),
    ("PREV-3.8-01", lambda r: r["factors"].__setitem__("A", 1.5)),
])
def test_rechecks_detect_counterexamples(rid, mutate):
    """Each re-check really looks at the records: a corrupted record makes it FAIL."""
    res, cfg = _run()
    assert _status(recheck(res.records, cfg, res.summary), rid) == PASS
    records = copy.deepcopy(res.records)
    target = next(r for r in records if r["status"] == "POSITIVE")
    mutate(target)
    assert _status(recheck(records, cfg, res.summary), rid) == FAIL


def test_failure_examples_are_refused():
    from lab.core.schema import LabInputError
    for inp in M.failure_examples().values():
        with pytest.raises(LabInputError):
            M.validate(inp)
