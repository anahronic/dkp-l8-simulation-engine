"""Lab core: strict inputs, check statuses, identity, packages and replay (TZ §3, §9, §11.2)."""

import io
import json
import zipfile

import pytest

from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult, summarize
from lab.core.export import ReplayMismatch, build_package, replay
from lab.core.report import html_page, markdown
from lab.core.run import run_request, validate_request
from lab.core.schema import LabInputError, resolve

SPEC = {"n": {"type": "int", "min": 0, "max": 9, "default": 1, "source": "user"},
        "x": {"type": "number", "default": 0.5, "source": "hypothesis"},
        "p": {"type": "pair", "default": [0, 1], "source": "text"}}


@pytest.mark.parametrize("bad", [{"x": float("nan")}, {"x": float("inf")}, {"x": True}, {"n": 1.5},
                                 {"n": 10}, {"p": [2, 1]}, {"extra": 1}])
def test_strict_inputs(bad):
    with pytest.raises(LabInputError):
        resolve(bad, SPEC)


def test_defaults_are_filled_visibly():
    assert resolve({}, SPEC) == {"n": 1, "x": 0.5, "p": [0, 1]}


def test_not_applicable_needs_a_reason():
    with pytest.raises(ValueError):
        CheckResult("X-1", "c", NOT_APPLICABLE, "why")


def test_unknown_and_uncovered_never_count_as_pass():
    s = summarize([CheckResult("A-1", "a", PASS, ""), CheckResult("A-2", "b", UNKNOWN, "")], ["A-1", "A-2", "A-3"])
    assert s["counts"]["PASS"] == 1 and s["uncovered"] == ["A-3"]
    assert s["all_document_requirements_passed"] is False
    s2 = summarize([CheckResult("A-1", "a", PASS, "")], ["A-1"])
    assert s2["all_document_requirements_passed"] is True
    s3 = summarize([CheckResult("A-1", "a", FAIL, "")], ["A-1"])
    assert s3["all_document_requirements_passed"] is False


def _req(module="time", variants=None):
    return {"schema": "dkp-lab-input/1", "module": module,
            "variants": variants or [{"name": "a", "input": {"dates": ["2026-01-01"]}}]}


@pytest.mark.parametrize("bad", [
    {"schema": "x", "module": "time", "variants": []},
    _req(module="python"),
    _req(variants=[{"name": "a", "input": {}}, {"name": "a", "input": {}}]),
    _req(variants=[{"name": "bad name!", "input": {}}]),
    _req(variants=[{"name": f"v{i}", "input": {}} for i in range(7)]),
    _req(variants=[{"name": "a", "input": {"dates": ["2026-13-01"]}}]),
])
def test_request_validation(bad):
    with pytest.raises(LabInputError):
        validate_request(bad)


def test_same_request_same_ids():
    a, b = run_request(_req()), run_request(_req())
    assert (a["input_id"], a["result_id"]) == (b["input_id"], b["result_id"])
    c = run_request(_req(variants=[{"name": "a", "input": {"dates": ["2026-01-02"]}}]))
    assert c["input_id"] != a["input_id"] and c["result_id"] != a["result_id"]


def test_adding_a_variant_does_not_change_another():
    """TZ §11.2: another computation must not shift the first one (no shared state or random stream)."""
    for module in ("work_cycle", "failure_chain", "prevention"):
        from lab import api
        ex = api.example_request(module)["variants"]
        alone = run_request({"schema": "dkp-lab-input/1", "module": module, "variants": ex[:1]})
        pair = run_request({"schema": "dkp-lab-input/1", "module": module, "variants": ex[1:2] + ex[:1]})
        name = ex[0]["name"]
        assert alone["variants"][name]["result_id"] == pair["variants"][name]["result_id"], module


def test_package_is_deterministic_and_replays():
    doc = run_request(_req())
    prov = {"fixed": True}
    p1, p2 = build_package(doc, {}, prov), build_package(doc, {}, prov)
    assert p1 == p2
    rep = replay(p1)
    assert rep["same_input"] and rep["same_result"]


def test_tampered_package_is_refused():
    doc = run_request(_req())
    data = build_package(doc, {}, {"fixed": True})
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for n in zin.namelist():
            body = zin.read(n)
            if n == "request.json":
                body = body.replace(b"2026-01-01", b"2026-01-02")
            zout.writestr(n, body)
    with pytest.raises(ReplayMismatch, match="request.json"):
        replay(buf.getvalue())


def test_report_escapes_markup():
    doc = run_request(_req())
    doc["variants"]["a"]["explain"].append({"en": "<script>alert(1)</script>", "ru": "<b>x</b>"})
    page = html_page(doc, "en")
    assert "<script>alert" not in page and "&lt;script&gt;" in page
    assert "<b>x</b>" in markdown(doc, "ru")      # Markdown stays plain text; HTML is escaped


def test_validation_is_idempotent_for_every_module_example():
    """A resolved input must validate to itself: packages store resolved inputs and replay them."""
    from lab.modules import MODULES
    for m in MODULES.values():
        for name, inp in m.examples().items():
            once = m.validate(inp)
            assert m.validate(once) == once, (m.id, name)


def test_every_module_example_package_replays():
    """End to end: the first two examples of each module -> package -> replay with the same ids."""
    from lab import api
    from lab.modules import MODULES
    for mid in sorted(MODULES):
        req = api.example_request(mid)
        req["variants"] = req["variants"][:2]
        doc = run_request(req)
        rep = replay(build_package(doc, {}, {"fixed": True}))
        assert rep["same_input"] and rep["same_result"], mid
