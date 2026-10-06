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
