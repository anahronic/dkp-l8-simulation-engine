"""TIME module: independent implementation vs §9 vectors and the §10 reference code."""

import pytest

from lab.core.checks import FAIL, PASS
from lab.core.schema import LabInputError
from lab.modules.time import TimeModule, canonical, dy_doy, from_dy_doy, gregorian_to_jdn, reference_namespace

M = TimeModule()


def _checks(dates):
    r = M.evaluate(M.validate({"dates": dates}))
    return {c.requirement_id: c for c in r.checks}, r


def test_vectors_and_the_known_inconsistency():
    checks, r = _checks(["2026-01-01"])
    for rid in ("TIME-9-01", "TIME-9-02", "TIME-9-03"):
        assert checks[rid].status == PASS
    v4 = checks["TIME-9-04"]
    assert v4.status == FAIL and v4.evidence["tag"] == "corpus_inconsistency"
    assert v4.evidence["computed"][3] == "DY6809-306" and v4.evidence["table"][3] == "DY6815-026"


def test_reference_implementation_agrees_on_many_dates():
    ref = reference_namespace()
    for y in (1, 1582, 1970, 2000, 2026, 9999):
        for m, d in ((1, 1), (2, 28), (12, 31)):
            jdn = gregorian_to_jdn(y, m, d)
            assert jdn == ref["gregorian_to_jdn"](y, m, d)
            assert canonical(*dy_doy(jdn)) == ref["gregorian_to_dikenocratic"](y, m, d).canonical()


def test_all_checks_pass_except_the_inconsistent_row():
    checks, _ = _checks(["2025-12-31", "2026-01-01", "2026-12-31"])
    assert [rid for rid, c in checks.items() if c.status != PASS] == ["TIME-9-04"]


@pytest.mark.parametrize("bad", ["2026-02-30", "26-01-01", "2026-1-1x", "0000-01-01"])
def test_invalid_dates_refused(bad):
    with pytest.raises(LabInputError):
        M.validate({"dates": [bad]})


@pytest.mark.parametrize("doy", [0, 361])
def test_invalid_doy_rejected(doy):
    with pytest.raises(ValueError):
        from_dy_doy(6836, doy)


from lab.modules.time import FAULTS, parse_canonical, store  # noqa: E402


@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_fault_is_detected(fault):
    clean = {c.requirement_id: c.status for c in M.evaluate(M.validate({})).checks}
    broken = {c.requirement_id: c.status for c in M.evaluate(M.validate({"faults": [fault]})).checks}
    assert any(broken[k] == "FAIL" and clean[k] == "PASS" for k in broken), fault


def test_store_keeps_dti_day_and_refuses_gregorian_only():
    out = {x["id"]: x for x in M.evaluate(M.validate({})).outputs["records"]}
    assert out["conflicting"]["dti_day"] == 2461042 and out["conflicting"]["conflicts"] == ["dy_doy", "gregorian"]
    assert not out["gregorian_only"]["accepted"]
    assert out["audit_of_conflict"]["reference"] == "DTI-Day 2461042"
    assert out["by_dy_doy"]["gregorian_display"] == "2026-01-02"


@pytest.mark.parametrize("s", ["DY6836-84", "DY06836-084", "DY+6836-084", "DY6836-361", "DY-0-001", "DY6836-000"])
def test_non_canonical_strings_rejected(s):
    with pytest.raises(ValueError):
        parse_canonical(s)


def test_year_table_has_leap_years_and_360_days():
    years = M.evaluate(M.validate({})).outputs["years"]
    assert all(y["last"] - y["first"] + 1 == 360 and y["first"] == y["dy"] * 360 for y in years)
    assert {6810, 6834} <= {y["dy"] for y in years}          # the DTI-Years containing 2000-02-29 and 2024-02-29


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])


def test_store_without_records():
    assert store([]) == []
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate({"records": []})).checks}
    assert st["TIME-7-02"] == "NOT_APPLICABLE" and st["TIME-8-02"] == "NOT_APPLICABLE"
