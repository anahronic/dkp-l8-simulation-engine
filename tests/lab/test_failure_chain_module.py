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
    assert fails == []
    if name == "long_divergence":                 # 24 days of disagreement: the window closes at 14, the next state is open
        assert statuses(res)["ORACLE-11-03"] == "PASS" and statuses(res)["ORACLE-11-04"] == "UNKNOWN"


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
    "arbitration_overrun": ("long_divergence", ["ORACLE-11-03"]),
    "deadline_rounded_up": ("coarse_grid_divergence", ["ORACLE-11-03"]),
}


def test_arbitration_deadline_is_not_rounded_up():
    """Review КТ4-GPT-01: with 1000-minute steps the window must close by 20160 minutes, not at 21000."""
    _, res = run(**M.examples()["coarse_grid_divergence"])
    ev = [e for e in res.outputs["events"] if e["type"] in ("arbitration_open", "arbitration_closed")]
    assert [e["type"] for e in ev] == ["arbitration_open", "arbitration_closed"]
    minutes = (ev[1]["step"] - ev[0]["step"]) * 1000
    assert minutes == 20000 <= 20160 and ev[1]["outcome"] == "window expired unresolved"
    st = statuses(res)
    assert st["ORACLE-11-03"] == "PASS" and st["ORACLE-11-04"] == "UNKNOWN"
    _, broken = run(**{**M.examples()["coarse_grid_divergence"], "faults": ["deadline_rounded_up"]})
    assert statuses(broken)["ORACLE-11-03"] == "FAIL"


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
    """New data at step 30 re-evaluate at once (EV-002); the dispute at 60 recomputes after the status quo delay
    (EV-003) with a comparative delta; every earlier record is kept unchanged."""
    _, res = run(dispute_at_step=60, value_change_at_step=30, changed_value=95)
    ev = res.outputs["evaluations"]
    assert [(e["id"], e["step"], e["value"], e["supersedes"]) for e in ev] == [
        ("EV-001", 0, 100.0, None), ("EV-002", 30, 95.0, "EV-001"), ("EV-003", 62, 95.0, "EV-002")]
    delta = [e for e in res.outputs["events"] if e["type"] == "delta"]
    assert delta == [{"step": 62, "type": "delta", "old": "EV-002", "new": "EV-003",
                      "old_value": 95.0, "new_value": 95.0, "delta": 0.0}]
    assert statuses(res)["EB-7.2-01"] == "PASS"


def test_ttl_above_the_text_maximum_fails():
    assert statuses(run(ttl_minutes=2000)[1])["ORACLE-17-01"] == "FAIL"
    assert statuses(run(ttl_minutes=1000)[1])["ORACLE-17-01"] == "PASS"
    st = statuses(run(data_type="land_use")[1])
    assert st["ORACLE-17-02"] == "PASS" and st["ORACLE-17-01"] == "NOT_APPLICABLE"


def test_value_drop_triggers_reevaluation():
    """New admissible data trigger re-evaluation (EB §7.1, ETRANS §4.2): a synchronous drop below the limit ends
    enforcement at once.  The lab's former reading ('declared_events') kept enforcing and is now a FAIL of
    ETRANS-4.2-01 (finding F-001 reclassified as IMPLEMENTATION_BUG)."""
    _, res = run(**M.examples()["value_drop_in_sync"])
    assert res.outputs["totals"]["final_mode"] == "INACTIVE"
    assert res.outputs["totals"]["steps_enforced_against_current_state"] == 0
    _, old = run(**{**M.examples()["value_drop_in_sync"], "reevaluation_policy": "declared_events"})
    assert statuses(old)["ETRANS-4.2-01"] == "FAIL"
    assert old.outputs["totals"]["steps_enforced_against_current_state"] == 192


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
