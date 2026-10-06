"""FAILURE CHAIN module (S-LAB-02): reference adapter, independent checks, counterexamples."""

import pytest

from lab import api
from lab.core.schema import LabInputError
from lab.modules.failure_chain import (FAULTS, TTL_TEXT, FailureChainModule, generate, run_adapter)

M = FailureChainModule()


def run(**inp):
    r = M.validate(inp)
    return r, M.evaluate(r)


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


def test_ttl_registry_is_read_from_the_pinned_text():
    assert TTL_TEXT == {"co2": 60, "surface_temperature": 1440, "active_fire": 10,
                        "biodiversity": 43200, "land_use": 10080}


@pytest.mark.parametrize("name", [n for n, v in M.examples().items() if not v.get("faults")])
def test_reference_adapter_breaks_no_rule(name):
    _, res = run(**M.examples()[name])
    fails = sorted(k for k, s in statuses(res).items() if s == "FAIL")
    if name == "long_divergence":
        assert fails == ["ORACLE-11-03"]          # 24 days unresolved; the scenario, not the adapter
    else:
        assert fails == []


# each deliberate fault, alone, on a scenario that exercises the rule it breaks
FAULT_CASES = {
    "stale_weight_kept": ("stale_ground", ["ORACLE-4.6-01", "ORACLE-9-01", "ORACLE-9-02", "ORACLE-9-03",
                                           "ETRANS-4.1-02"]),
    "divergence_ignored": ("divergence_resolved", ["ORACLE-11-01", "ORACLE-11-02", "ETRANS-4.1-02"]),
    "no_propagation": ("divergence_resolved", ["ETRANS-4.1-01", "ETRANS-4.1-02", "ETRANS-3-02", "ORACLE-11-02",
                                               "ETRANS-4.3-03", "ASSETS-2-02"]),
    "accrue_during_suspension": ("divergence_resolved", ["ETRANS-4.3-03", "FINANCE-11.2-03", "ORACLE-11-02"]),
    "escalate_during_suspension": ("divergence_resolved", ["ETRANS-4.1-03", "ETRANS-4.3-02", "ETRANS-4.3-01"]),
    "auto_reactivate": ("stale_ground", ["ETRANS-4.4-01", "ETRANS-4.4-02", "ETRANS-4.2-01", "ETRANS-4.3-04"]),
    "mutate_on_dispute": ("dispute_recompute", ["EB-7.2-01", "EB-7.2-02", "EB-7.2-04"]),
    "execute_incomplete": ("incomplete_order", ["EB-5.x-02", "EB-5.x-03", "EB-8-02", "ASSETS-8.3-07"]),
    "repair_metadata": ("incomplete_order", ["EB-5.x-06", "EB-5.x-03"]),
}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    scenario, expected = FAULT_CASES[fault]
    _, clean = run(**M.examples()[scenario])
    _, broken = run(**{**M.examples()[scenario], "faults": [fault]})
    st = statuses(broken)
    for rid in expected:
        assert statuses(clean)[rid] == "PASS", (rid, statuses(clean)[rid])
        assert st[rid] == "FAIL", (fault, rid, st[rid])


def test_adapter_never_reads_future_readings():
    r = M.validate(M.examples()["divergence_resolved"])
    readings = generate(r)
    cut = 100 * r["step_minutes"]
    changed = {c: [(t, v if t <= cut else v * 3) for t, v in rows] for c, rows in readings.items()}
    rows_a, _, _ = run_adapter(r, readings, 1440)
    rows_b, _, _ = run_adapter(r, changed, 1440)
    assert rows_a[:101] == rows_b[:101]
    assert rows_a[101:] != rows_b[101:]


def test_dispute_keeps_the_original_and_reports_a_delta():
    _, res = run(dispute_at_step=60, value_change_at_step=30, changed_value=95)
    ev = res.outputs["evaluations"]
    assert [e["id"] for e in ev] == ["EV-001", "EV-002"]
    assert ev[0]["value"] == 100 and ev[0]["step"] == 0
    assert ev[1]["supersedes"] == "EV-001" and ev[1]["value"] == 95
    delta = [e for e in res.outputs["events"] if e["type"] == "delta"]
    assert delta == [{"step": 62, "type": "delta", "old": "EV-001", "new": "EV-002",
                      "old_value": 100.0, "new_value": 95.0, "delta": -5.0}]


def test_ttl_above_the_text_maximum_fails():
    assert statuses(run(ttl_minutes=2000)[1])["ORACLE-17-01"] == "FAIL"
    assert statuses(run(ttl_minutes=1000)[1])["ORACLE-17-01"] == "PASS"
    st = statuses(run(data_type="land_use")[1])
    assert st["ORACLE-17-02"] == "PASS" and st["ORACLE-17-01"] == "NOT_APPLICABLE"


def test_value_drop_without_divergence_keeps_enforcement():
    """Documented gap (MODEL_GAPS §11): under H-FC-5 a synchronous drop below the limit
    is not a trigger, so enforcement continues on the old evaluation and no rule fails."""
    _, res = run(**M.examples()["value_drop_in_sync"])
    assert res.outputs["totals"]["final_mode"] == "ACTIVE"
    assert res.outputs["totals"]["evaluations"] == 1
    assert "FAIL" not in statuses(res).values()
    _, res = run(**M.examples()["value_drop"])                   # asynchronous sampling: spurious divergence
    assert res.outputs["totals"]["final_mode"] == "INACTIVE"


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])


def test_run_is_deterministic_and_records_are_exported():
    req = api.example_request("failure_chain")
    req["variants"] = req["variants"][:2]
    a = api.run_payload(req)
    b = api.run_payload(req)
    assert a["result_id"] == b["result_id"] and a["input_id"] == b["input_id"]
    assert a["variants"]["divergence_resolved"]["summary"]["counts"]["FAIL"] == 0
    assert a["variants"]["divergence_faulty_adapter"]["summary"]["counts"]["FAIL"] > 0
