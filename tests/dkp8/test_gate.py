"""Acceptance gate: synthetic catalogue, fail-closed behaviour, no override, reproducibility of decisions."""
import copy

import pytest

from dkp8 import gate, reproduction, scenarios, trust
from dkp8.canonical import digest

STORE = trust.canonical_store()


@pytest.mark.parametrize("case", scenarios.catalog(), ids=lambda c: c["id"])
def test_catalogue_decisions(case):
    if case["expect"] == "REFUSED":
        with pytest.raises(gate.DossierError):
            gate.evaluate(case["dossier"], STORE)
        return
    decision = gate.evaluate(case["dossier"], STORE)
    assert decision["decision"] == case["expect"], decision
    assert decision["deployment_mandated"] is False and decision["override_possible"] is False


def test_decision_is_deterministic_and_hash_bound():
    a = gate.evaluate(scenarios.get("cascade-f2")["dossier"], STORE)
    b = gate.evaluate(scenarios.get("cascade-f2")["dossier"], STORE)
    assert a == b and a["decision_sha256"] == digest({k: v for k, v in a.items() if k != "decision_sha256"})
    assert a["failure_classes"] == ["F2"]


def test_blocking_dominates_redesign():
    d = scenarios.get("externality-f4")["dossier"]
    d["scenarios"][1] = scenarios.get("cascade-f2")["dossier"]["scenarios"][1]
    out = gate.evaluate(d, STORE)
    assert out["decision"] == "BLOCKED" and out["redesign"]


def test_every_canonical_case_lacks_independent_reproduction():
    for case in scenarios.catalog():
        if case["expect"] != "REFUSED":
            assert gate.evaluate(case["dossier"], STORE)["reproduction"]["independent_nodes"] == 0


def eligible_test_dossier():
    """TEST ONLY: author decisions, empirical provenance and nodes are test fixtures that exercise the positive path."""
    d = scenarios.get("clean-synthetic")["dossier"]
    author = {"kind": "author_decision", "ref": "TEST FIXTURE - not an author decision"}
    for s in d["scenarios"]:
        s["inputs"]["synthetic"] = False
        s["trace"]["loss_of_life"]["metric_definition"] = {"provenance": dict(author)}
        s["trace"]["biosphere"] = {"metric": "B(t)", "values": ["0.80", "0.79"], "minimum": "0.68",
                                   "provenance": {"kind": "ptl_dataset", "ref": "TEST FIXTURE", "sha256": "f" * 64}}
    d["required_independent_nodes"] = {"value": 2, "provenance": dict(author)}
    return d


def test_positive_path_is_reachable_only_with_test_identities(tmp_path):
    nodes = [bytes.fromhex("31" * 32), bytes.fromhex("32" * 32)]
    store = trust.with_test_identities(STORE, bytes.fromhex("30" * 32), nodes)
    d = eligible_test_dossier()
    rid = d["scenarios"][0]["run"]["result_id"]
    records = []
    for i, seed in enumerate(nodes):
        body = {"result_id_expected": rid, "result_id_observed": rid, "input_id_expected": "0" * 64,
                "input_id_observed": "0" * 64, "level": "R3", "operator": f"test-node-{i}", "at": "2026-11-17T00:00:00Z"}
        records.append({"schema": reproduction.RECORD_SCHEMA, "body": body, "signature": trust.sign_document(body, seed)})
    d["reproductions"] = records
    out = gate.evaluate(d, store)
    assert out["decision"] == "ELIGIBLE", out["missing_evidence"]
    assert out["test_identities_used"] and out["deployment_mandated"] is False
    assert gate.evaluate(d, STORE)["decision"] == "NOT_ESTABLISHED"          # canonical store: no node exists


def test_reproduction_mismatch_blocks():
    d = eligible_test_dossier()
    rid = d["scenarios"][0]["run"]["result_id"]
    body = {"result_id_expected": rid, "result_id_observed": "9" * 64, "level": "R1", "operator": "me"}
    d["reproductions"] = [{"schema": reproduction.RECORD_SCHEMA, "body": body, "signature": None}]
    out = gate.evaluate(d, STORE)
    assert out["decision"] == "BLOCKED" and "reproduction mismatch" in " ".join(out["blocking"])


def test_unsigned_r3_claim_is_rejected():
    rep = reproduction.assess([{"schema": reproduction.RECORD_SCHEMA, "body": {"level": "R3", "operator": "x",
                                "result_id_expected": "a", "result_id_observed": "a"}, "signature": None}], STORE)
    assert rep["independent_nodes"] == 0 and rep["rejected"]


def test_unknown_schema_refused():
    with pytest.raises(gate.DossierError):
        gate.evaluate({"schema": "other"}, STORE)
    d = copy.deepcopy(scenarios.get("clean-synthetic")["dossier"])
    d["change"]["waiver"] = True
    with pytest.raises(gate.DossierError):
        gate.evaluate(d, STORE)
