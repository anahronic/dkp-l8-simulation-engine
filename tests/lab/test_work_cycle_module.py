"""WORK-CYCLE module: Cycle6 rosters and 24/7 coverage (scenario S-LAB-08)."""

import pytest

from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN
from lab.core.schema import LabInputError
from lab.modules.work_cycle import MONITORED, WorkCycleModule

M = WorkCycleModule()


def run(**inp):
    r = M.evaluate(M.validate(inp))
    return {c.requirement_id: c.status for c in r.checks}, r.outputs


def checks(**inp):
    return {(c.requirement_id, c.check): c for c in M.evaluate(M.validate(inp)).checks}


def test_staffed_default_covers_every_hour():
    st, out = run()
    assert out["coverage"]["deficit_hours"] == 0
    assert st["WORKCYCLE-8.1-01"] == PASS and st["WORKCYCLE-7-01"] == PASS
    assert not [k for k, v in st.items() if v == FAIL]


def test_understaffed_shows_deficit():
    st, out = run(workers=10)
    assert out["coverage"]["deficit_hours"] > 0 and st["WORKCYCLE-8.1-01"] == FAIL
    assert out["workers_lower_bound_flat"] == 18         # 4 staff × 24 h / 8 h / (4/6)


def test_three_consecutive_workdays_is_a_planning_failure():
    st, _ = run(pattern=["W", "W", "W", "R", "W", "R"])
    assert st["WORKCYCLE-4.2-01"] == FAIL and st["WORKCYCLE-7-01"] == FAIL and st["WORKCYCLE-8.1-02"] == FAIL
    assert st["WORKCYCLE-7-02"] == PASS                  # reported against the roster, not a worker
    st2, _ = run(pattern=["W", "W", "W", "R", "W", "R"], compensation_declared=True)
    assert st2["WORKCYCLE-7-01"] == UNKNOWN


def test_aligned_phases_leave_rest_days_unstaffed():
    _, out = run(phase_offsets="aligned")
    assert out["coverage"]["deficit_hours"] > 0


def test_changed_text_values_fail_the_allocation_checks():
    st, _ = run(presence_hours=10, work_hours=7, recovery_hours=3, work_before_recovery=4)
    assert st["WORKCYCLE-5.1-01"] == FAIL and st["WORKCYCLE-5.2-01"] == NOT_APPLICABLE


def test_year_accounting_on_a_full_year():
    st, _ = run(horizon_days=360, workers=6, shift_starts=[0])
    assert st["WORKCYCLE-6-03"] == PASS


def test_invalid_inputs_refused():
    for inp in M.failure_examples().values():
        with pytest.raises(LabInputError):
            M.validate(inp)
    with pytest.raises(LabInputError):
        M.validate({"demand": [1] * 23})


def test_refusal_is_respected_and_not_punished():
    """LABOR §9.1: outside a declared crisis refusing workers are not scheduled and not penalised."""
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate({"refusing_workers": 6})).checks}
    assert (st["LABOR-9.1-01"], st["LABOR-9.1-02"], st["LABOR-6-01"]) == ("PASS", "PASS", "PASS")
    for fault, rid in (("assign_refusers", "LABOR-9.1-01"), ("penalize_refusal", "LABOR-9.1-02")):
        st = {c.requirement_id: c.status for c in M.evaluate(M.validate({"refusing_workers": 6, "faults": [fault]})).checks}
        assert st[rid] == "FAIL", fault


def test_roster_days_are_dti_labels():
    res = M.evaluate(M.validate({"start_dti_day": 2461042, "horizon_days": 6}))
    assert res.outputs["roster_days"][0] == "DY6836-083"
    assert {c.requirement_id: c.status for c in res.checks}["TIME-5.1-01"] == "PASS"


from lab.modules.work_cycle import FAULTS  # noqa: E402


@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_fault_is_detected(fault):
    base = {"refusing_workers": 6} if fault in ("assign_refusers", "penalize_refusal") else \
        {"refusing_workers": 6, "crisis_window": [3, 7]} if fault in ("permanent_obligation", "post_crisis_penalty", "exception_precedent",
                                                                      "untraced_exception", "crisis_withdraws_access",
                                                                      "no_recovery_compensation") else {}
    clean, broken = checks(**base), checks(**base, faults=[fault])
    assert any(broken[k].status == FAIL and clean[k].status == PASS for k in broken), fault


def test_one_year_recovery_and_cycles():
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate(M.examples()["one_year"])).checks}
    assert st["WORKCYCLE-6-03"] == st["WORKCYCLE-6-04"] == st["WORKCYCLE-4.2-03"] == "PASS"


def test_recovery_requests():
    d = {x["request"]: x for x in M.evaluate(M.validate({})).outputs["recovery_requests"]}
    assert not d["monetize"]["granted"] and not d["work_task"]["granted"]
    assert d["meal"]["granted"] and not d["meal"]["justification_required"]


def test_crisis_draft_is_time_limited():
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate(M.examples()["crisis_draft"])).checks}
    assert st["LABOR-9.1-01"] == st["LABOR-9.2-03"] == "PASS"
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate(M.examples()["crisis_draft_faulty"])).checks}
    assert st["LABOR-9.2-03"] == "FAIL"


def test_kt5_recovery_week_and_exceptions():
    """Review КТ5 reading of WORK-CYCLE §3, §4.2, §10: each fault breaks only its own provision."""
    crisis = {"refusing_workers": 6, "crisis_window": [3, 7]}
    cases = {"work_in_recovery": ({}, "WORKCYCLE-3-07"), "week_authority": ({}, "WORKCYCLE-4.2-04"),
             "permanent_obligation": (crisis, "WORKCYCLE-10-02"), "exception_precedent": (crisis, "WORKCYCLE-10-05")}
    for fault, (base, rid) in cases.items():
        st = {c.requirement_id: c.status for c in M.evaluate(M.validate(dict(base, faults=[fault]))).checks}
        assert st[rid] == "FAIL", fault
        assert all(st[x] in ("PASS", "NOT_APPLICABLE") for _, x in cases.values() if x != rid), fault


def test_kt5_restricted_participation():
    """LABOR §10: under Restriction or Isolation, those who decline are not scheduled; those who take part are not exploited."""
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate({})).checks}
    assert st["LABOR-10-03"] == "PASS"
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate({"faults": ["coerce_restricted"]})).checks}
    assert st["LABOR-10-03"] == "FAIL"
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate({"restricted_participants": 0})).checks}
    assert st["LABOR-10-03"] == "NOT_APPLICABLE"


def test_returned_day_index_and_exception_scope():
    """WORK-CYCLE §3 and §10 (returned provisions): days indexed by TIME; exceptions only inside a declared crisis, traced."""
    crisis = {"refusing_workers": 6, "crisis_window": [3, 7]}
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate(crisis)).checks}
    assert st["WORKCYCLE-3-01"] == st["WORKCYCLE-10-01"] == st["WORKCYCLE-10-04"] == "PASS"
    for fault, rid in (("civil_day_index", "WORKCYCLE-3-01"), ("assign_refusers", "WORKCYCLE-10-01"),
                       ("permanent_obligation", "WORKCYCLE-10-01"), ("untraced_exception", "WORKCYCLE-10-04")):
        st = {c.requirement_id: c.status for c in M.evaluate(M.validate(dict(crisis, faults=[fault]))).checks}
        assert st[rid] == "FAIL", fault


def test_labor_allocation_and_isolation():
    """LABOR §7 and §12 (returned provisions): the roster follows its published rule; cross-layer requests are refused."""
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate({})).checks}
    assert st["LABOR-7-03"] == st["LABOR-12-01"] == "PASS"
    for fault, rid in (("manual_assignment", "LABOR-7-03"), ("labor_as_punishment", "LABOR-12-01")):
        st = {c.requirement_id: c.status for c in M.evaluate(M.validate({"faults": [fault]})).checks}
        assert st[rid] == "FAIL", fault


REFUSALS, CRISIS = {"refusing_workers": 6}, {"refusing_workers": 6, "crisis_window": [3, 7]}
CORE_FAULTS = {          # checkable cores of provisions whose open point remains (review КТ7-GPT-01)
    "bar_restricted": ({}, ["LABOR-10-01"]),
    "no_recovery_pathway": ({}, ["LABOR-10-02", "LABOR-5.1-01"]),
    "compulsory_pathway": ({}, ["LABOR-5.1-01"]),
    "single_opportunity": ({}, ["LABOR-5.1-02"]),
    "no_consent_record": ({}, ["LABOR-3.2-01", "LABOR-7-01"]),
    "coerce_restricted": ({}, ["LABOR-3.2-01", "LABOR-7-01"]),
    "assign_refusers": (REFUSALS, ["LABOR-3.2-01", "LABOR-7-01", "LABOR-9.2-01"]),
    "access_requires_work": ({}, ["LABOR-4.1-01", "LABOR-5.1-01"]),
    "crisis_withdraws_access": (CRISIS, ["LABOR-4.1-01", "LABOR-9.2-02"]),
    "permanent_obligation": (CRISIS, ["LABOR-9.2-01", "LABOR-9.2-02"]),
    "restore_without_contribution": ({}, ["LABOR-4.2-02"]),
    "no_recovery_compensation": (CRISIS, ["WORKCYCLE-10-03"]),
    "week_authority": ({}, ["WORKCYCLE-2-02"]),
    "work_in_recovery": ({}, ["WORKCYCLE-5.3-02"]),
    "justify_recovery": ({}, ["WORKCYCLE-5.3-02"]),
    "unmonitored_category": ({}, ["WORKCYCLE-9-01"]),
    "wrong_recovery_compliance": ({}, ["WORKCYCLE-9-01"]),
}


@pytest.mark.parametrize("fault", sorted(CORE_FAULTS))
def test_core_fault_hits_its_provision(fault):
    base, rids = CORE_FAULTS[fault]
    clean, broken = checks(**base), checks(**base, faults=[fault])
    for rid in rids:
        assert any(clean[k].status == PASS and broken[k].status == FAIL for k in clean if k[0] == rid), (fault, rid)


def test_restricted_subjects_keep_access_pathways_and_consent():
    """LABOR §4.1, §5.1, §10 clear parts: the Subject who declines keeps baseline access and a voluntary offer; the
    participants are scheduled with explicit consent; a restoration cites the participant's contribution record."""
    st, out = run()
    rp = {x["subject"]: x for x in out["restricted_participation"]}
    assert rp["x1"]["declines"] and not rp["x1"]["scheduled"] and rp["x1"]["recovery_pathway"]["voluntary"]
    assert {x["subject"]: x["access"] for x in out["baseline_access"]}["x1"] == "kept"
    assert out["restorations"] == [{"subject": "x2", "restored": "full participation and access", "basis": "CR-x2"}]
    assert st["WORKCYCLE-2-02"] == PASS and st["LABOR-9.2-01"] == NOT_APPLICABLE
    st, _ = run(pattern=["W", "W", "W", "R", "W", "R"], compensation_declared=True)
    assert st["WORKCYCLE-2-02"] == UNKNOWN


def monitoring_series(value=1):
    return {c: [{"period": 0, "value": value, "source": f"operational log {i}"}] for i, c in enumerate(MONITORED[:-1])}


def test_monitoring_default_separates_declaration_data_and_recomputation():
    result = checks()
    declared = result["WORKCYCLE-9-01", "five_categories_declared"]
    records = result["WORKCYCLE-9-01", "monitoring_records_present"]
    assert declared.status == PASS and "not evidence that monitoring runs" in declared.explanation
    assert records.status == UNKNOWN
    assert all(c in records.explanation for c in MONITORED[:-1])
    assert records.evidence == {c: "no data" for c in MONITORED[:-1]}
    assert result["WORKCYCLE-9-01", "recovery_compliance_recomputed"].status == PASS


@pytest.mark.parametrize("series", [{}, {c: [] for c in MONITORED[:-1]}, monitoring_series(None)])
def test_monitoring_without_measurements_is_unknown(series):
    check = checks(monitoring_series=series)["WORKCYCLE-9-01", "monitoring_records_present"]
    assert check.status == UNKNOWN
    assert all(c in check.explanation for c in MONITORED[:-1])
    assert check.evidence == {c: "no data" for c in MONITORED[:-1]}


@pytest.mark.parametrize("value", [0, 1.5])
def test_monitoring_present_records_leave_metric_rules_open(value):
    series = monitoring_series(value)
    for records in series.values():
        records.append({"period": 11, "value": None, "source": "missing measurement log"})
    check = checks(monitoring_series=series)["WORKCYCLE-9-01", "monitoring_records_present"]
    assert check.status == PASS
    assert check.evidence == {c: "1 measurements" for c in MONITORED[:-1]}
    assert "2 records" in check.explanation
    assert all(record["source"] in check.explanation for records in series.values() for record in records)
    assert all(word in check.explanation for word in ("definitions", "cadence", "sustained degradation", "stay open", "not checked"))


def test_monitoring_one_category_without_data_is_named():
    series = monitoring_series()
    del series[MONITORED[0]]
    check = checks(monitoring_series=series)["WORKCYCLE-9-01", "monitoring_records_present"]
    assert check.status == UNKNOWN and MONITORED[0] in check.explanation
    assert "no operational data presented; the lab does not measure it" in check.explanation
    assert all(c not in check.explanation for c in MONITORED[1:-1])


@pytest.mark.parametrize("change, reason", [({"value": -1}, "value"), ({"period": 12}, "period"),
    ({"period": -1}, "period"), ({"period": 1.5}, "period"), ({"period": True}, "period"),
    ({"value": "1"}, "value"), ({"value": True}, "value"), ({"value": float("nan")}, "value"),
    ({"value": float("inf")}, "value"), ({"source": " "}, "source"), ({"source": None}, "source")])
def test_malformed_monitoring_record_fails(change, reason):
    series = monitoring_series()
    series[MONITORED[0]][0].update(change)
    check = checks(monitoring_series=series)["WORKCYCLE-9-01", "monitoring_records_present"]
    assert check.status == FAIL and reason in check.explanation and MONITORED[0] in check.explanation


@pytest.mark.parametrize("record", [None, [], {}, {"period": 0, "source": "log"}])
def test_missing_monitoring_record_fields_fail(record):
    check = checks(monitoring_series={MONITORED[0]: [record]})["WORKCYCLE-9-01", "monitoring_records_present"]
    assert check.status == FAIL


@pytest.mark.parametrize("series", [None, [], {"unknown": []}, {MONITORED[-1]: []}, {MONITORED[0]: {}}])
def test_invalid_monitoring_series_container_or_category_is_rejected(series):
    with pytest.raises(LabInputError, match="monitoring_series"):
        M.validate({"monitoring_series": series})


@pytest.mark.parametrize("fault, check", [("unmonitored_category", "five_categories_declared"),
                                        ("wrong_recovery_compliance", "recovery_compliance_recomputed")])
def test_monitoring_fault_hits_its_check(fault, check):
    result = checks(faults=[fault])["WORKCYCLE-9-01", check]
    assert result.status == FAIL
    if fault == "unmonitored_category":
        assert "sick leave frequency" in result.explanation


def test_recovery_recomputation_without_workdays_is_not_applicable():
    assert checks(pattern=["R"])["WORKCYCLE-9-01", "recovery_compliance_recomputed"].status == NOT_APPLICABLE


@pytest.mark.parametrize("inp, rate", [({"faults": ["work_in_recovery"]}, 0),
                                     ({"work_hours": 7, "recovery_hours": 2.1}, 0),
                                     ({"refusing_workers": 6}, 1)])
def test_recovery_recomputation_uses_workdays_and_ceil_recovery(inp, rate):
    result = M.evaluate(M.validate(inp))
    assert result.outputs["monitoring"]["recovery compliance rate"] == rate
    check = next(c for c in result.checks if (c.requirement_id, c.check) ==
                 ("WORKCYCLE-9-01", "recovery_compliance_recomputed"))
    assert check.status == PASS
