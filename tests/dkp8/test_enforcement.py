"""§4 enforceability, §13 audit divergence, §14 dependents, composite index inventory."""
from dkp8 import composite, enforcement


def test_without_bundles_nothing_is_enforceable():
    rows = enforcement.enforceability()
    assert rows and all(r["state"] in ("NON-ENFORCEABLE", "UNCALIBRATED") for r in rows)
    assert {"DKP-5-HABITAT-001", "DKP-0-ORACLE-001", "DKP-5-INFO-001"} <= {r["doc"] for r in rows}


def test_valid_authoritative_bundle_covers_its_target_only():
    b = {"body": {"target": {"protocol_id": "DKP-5-HABITAT-001"}}}
    rows = enforcement.enforceability([{"enforceable": True}], [b])
    habitat = [r for r in rows if r["doc"] == "DKP-5-HABITAT-001"]
    assert habitat and all(r["state"] == "ENFORCEABLE" for r in habitat)
    assert all(r["state"] != "ENFORCEABLE" for r in rows if r["doc"] != "DKP-5-HABITAT-001")
    assert enforcement.enforceability([{"enforceable": False}], [b]) == enforcement.enforceability()


def test_audit_divergence_actions_and_missing_tolerance():
    tol = {"m": {"value": "0.5", "provenance": {"kind": "author_decision", "ref": "TEST"}}}
    ok = enforcement.audit_divergence({"m": ["1", "2"]}, {"m": ["1.2", "2.1"]}, tol, True)
    assert ok["state"] == "CONSISTENT" and ok["action"] is None
    roll = enforcement.audit_divergence({"m": ["1", "3"]}, {"m": ["1", "2"]}, tol, True)
    assert roll["state"] == "DIVERGENCE" and roll["action"] == "ROLLBACK"
    assert enforcement.audit_divergence({"m": ["1", "3"]}, {"m": ["1", "2"]}, tol, False)["action"] == "HALT"
    none = enforcement.audit_divergence({"m": ["1"]}, {"m": ["1"]}, {}, True)
    assert none["state"] == "NOT_ESTABLISHED" and "tolerance" in none["missing"][0]
    assert enforcement.audit_divergence({"m": ["1"]}, {"m": ["1", "2"]}, tol, True)["state"] == "NOT_ESTABLISHED"


def test_dependents_include_upstream_users_of_simulation():
    deps = enforcement.dependents("DKP-8-SIMULATION-001")
    assert "DKP-5-HABITAT-001" in deps and "DKP-8-SIMULATION-001" not in deps
    assert set(enforcement.dependents("DKP-0-ORACLE-001")) and all(d in enforcement.documents() for d in deps)


def test_composite_inventory_invents_nothing():
    inv = composite.inventory()
    names = " ".join(i["index"] for i in inv)
    assert all(x in names for x in ("B(t)", "SPDI", "PPDI", "Credit risk", "Fatigue"))
    assert all(i["status"] == "BLOCKED_BY_NORMATIVE_DECISION" and i["questions"] for i in inv)
    assert not any("weights" in i["given"] for i in inv)
