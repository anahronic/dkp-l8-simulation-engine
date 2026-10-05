"""Hand-calculated vectors for PREVENTION §3.3, §3.6, §5, §9.1, §9.4."""

import pytest

from simulation.core.oracles import readings_from
from simulation.modules.prevention.protocol_adapter import suppression_completeness
from simulation.modules.prevention.test_vectors import (
    BASIC_SPD, CONSISTENT_ORACLE, NO_COVERAGE, NO_MEASURED_REDUCTION, ORACLE_INCONSISTENCY,
    PARTIAL_SUPPRESSION, SELF_INDUCED_RISK, SINGLE_ORACLE_CLASS,
)
from tests.simulation.helpers import adapter_for, iv, ta_readings


def test_basic_spd():
    v = BASIC_SPD.inputs
    S = suppression_completeness(v["ta_intensity"], v["se_intensity"])
    assert S == pytest.approx(BASIC_SPD.expected["S_k"])
    spd = v["W_k"] * S * v["A_k"] * v["C_k"] * v["T_k"]
    assert spd == pytest.approx(BASIC_SPD.expected["SPD_k"])


def test_basic_spd_through_adapter():
    """Same vector end to end: W=0.9 (unauthorized_adult_proximity), full coverage C=1."""
    a = adapter_for()
    rec = a.evaluate_event("e", "zone-0001", "unauthorized_adult_proximity", ta_readings([0.8] * 4),
                           ta_readings([0.2] * 4, t=5.0), [iv("patrol_worker")])[0]
    assert rec["status"] == "POSITIVE"
    assert rec["factors"] == pytest.approx({"W": 0.9, "S": 0.75, "A": 1.0, "C": 1.0, "T": 1.0})
    assert rec["SPD"] == pytest.approx(0.9 * 0.75)


def test_no_measured_reduction():
    v = NO_MEASURED_REDUCTION.inputs
    assert suppression_completeness(v["ta_intensity"], v["se_intensity"]) == 0.0


def test_partial_suppression():
    v = PARTIAL_SUPPRESSION.inputs
    assert suppression_completeness(v["ta_intensity"], v["se_intensity"]) == pytest.approx(0.6)


def test_oracle_inconsistency():
    a = adapter_for()
    ta = a.assess_ta(readings_from(ORACLE_INCONSISTENCY.inputs["readings"]))
    assert ta.valid and not ta.consistent


def test_single_oracle_class():
    a = adapter_for()
    ta = a.assess_ta(readings_from(SINGLE_ORACLE_CLASS.inputs["readings"]))
    assert not ta.valid and ta.reason == "single_source"


def test_consistent_min_intensity():
    a = adapter_for()
    ta = a.assess_ta(readings_from(CONSISTENT_ORACLE.inputs["readings"]))
    assert ta.valid and ta.consistent
    assert ta.intensity == pytest.approx(0.48)
    assert ta.delta_oracle == pytest.approx(0.04)


def test_no_coverage():
    a = adapter_for()
    ta = a.assess_ta([])
    assert not ta.valid and ta.reason == NO_COVERAGE.expected["reason"]
    rec = a.evaluate_event("e", "zone-0001", "intrusion", [], None, [iv("patrol_worker")])[0]
    assert rec["status"] == "INVALID" and rec["SPD"] == 0.0 and rec["reason"] == "ta_no_data"


def test_self_induced_linkage():
    a = adapter_for()
    rec = a.evaluate_event("e", "zone-0001", "intrusion", ta_readings([0.8] * 4), ta_readings([0.2] * 4, t=5.0),
                           [iv("adversarial_actor", linkage=SELF_INDUCED_RISK.inputs["linkage_observed"])])[0]
    assert rec["factors"]["T"] == SELF_INDUCED_RISK.expected["T_k"]
    assert rec["status"] == SELF_INDUCED_RISK.expected["status"]
    assert rec["reason"] == SELF_INDUCED_RISK.expected["reason"]
