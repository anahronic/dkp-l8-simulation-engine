"""Review КТ5: provisions with a draft implementation_only open point are read before they count as resolvable."""

import json
import os

from lab.tools import reconcile

REG = os.path.join(os.path.dirname(__file__), "..", "..", "lab", "registry")


def _load(name):
    with open(os.path.join(REG, name), encoding="utf-8") as f:
        return json.load(f)


def test_reconciliations_are_current():
    assert _load("reconciliations.json") == reconcile.build()


def test_each_decision_matches_the_registry():
    reg = reconcile.registry()
    cls = _load("unresolved_classification.json")["items"]
    for it in _load("reconciliations.json")["items"]:
        r = reg[it["id"]]
        assert it["quote"] == r["quote"] and it["reason"]
        assert it["acceptance"] == {"agent_reading": True, "human_accepted": False}
        if it["verdict"] == "confirmed":
            assert r["coverage"] in ("IMPLEMENTED", "PARTIAL"), it["id"]
            assert it["check"] and it["check"].split(":")[0] == r["implementation"]["module"], it["id"]
            c = it["closure"]
            assert c["draft_need"] == r["hypotheses_needed"], it["id"]
            assert c["coverage_limit"] == (r["gap"] if r["coverage"] == "PARTIAL" else None), it["id"]
            assert r["decision_status"] == c["decision_status_after"], it["id"]
            if c["state"] == "closed":
                # review of checkpoint 6: the draft need is answered by the agent's reading; no open point remains
                assert c["answer"] and "open_point" not in r, it["id"]
                assert r["decision_basis"] == {"by": "agent_reading", "record": reconcile.RECORD, "human_accepted": False}
                assert cls[it["id"]]["primary"] == "implementation_only" and cls[it["id"]]["closed"] == reconcile.RECORD
            else:
                # what remains is not missing code: the open point keeps its own origin and the exact reason
                assert c["state"] == "open" and c["origin"] != "implementation_only" and c["reason"], it["id"]
                assert r["open_point"] == {"origin": c["origin"], "source": "lab_reconciled", "reason": c["reason"]}, it["id"]
                assert "decision_basis" not in r and cls[it["id"]]["primary"] == c["origin"], it["id"]
        else:
            assert it["verdict"] == "reclassified" and it["origin_after"] != "implementation_only", it["id"]
            assert cls[it["id"]]["primary"] == it["origin_after"], it["id"]
            # the open point stays: from the reconciliation, or from an open question of the same category
            src = "agent_verified" if it.get("questions") else "lab_reconciled"
            assert r["open_point"] == {"origin": it["origin_after"], "source": src}, it["id"]
            assert r["decision_status"] == "UNRESOLVED", it["id"]
            if it.get("check"):
                assert r["coverage"] == "PARTIAL" and it["check"].split(":")[0] == r["implementation"]["module"], it["id"]
        if "checkable" in it:
            assert r["checkable"] == it["checkable"]["to"], it["id"]


def test_closure_counts_and_no_other_basis():
    rec = _load("reconciliations.json")
    closed = {it["id"] for it in rec["items"] if (it.get("closure") or {}).get("state") == "closed"}
    assert rec["counts"]["confirmed_closed"] == len(closed)
    assert rec["counts"]["confirmed_closed"] + rec["counts"]["confirmed_open"] == rec["counts"]["confirmed"]
    assert rec["counts"]["human_accepted"] == 0
    # decision_basis comes only from a closed reconciliation
    assert {rid for rid, r in reconcile.registry().items() if r.get("decision_basis")} == closed


def test_an_open_question_reopens_a_provision_closed_by_reading():
    from lab.tools.sync_coverage import synced
    r = {"id": "X-1-01", "hypotheses_needed": ["a draft need"], "coverage": "PARTIAL", "implementation": None, "gap": "g",
         "checkable": "partial", "interpretation_status": "DRAFT_UNREVIEWED"}
    g = {"verified": set(), "question_origin": {},
         "draft": {"X-1-01": {"primary": "implementation_only", "reconciled": reconcile.RECORD, "closed": reconcile.RECORD}}}
    closed = synced({"requirements": [dict(r)]}, {}, {}, g)["requirements"][0]
    assert closed["decision_status"] == "NONE_IDENTIFIED" and "open_point" not in closed
    assert closed["decision_basis"]["human_accepted"] is False
    g["question_origin"] = {"X-1-01": "normative_ambiguity"}
    reopened = synced({"requirements": [dict(r)]}, {}, {"X-1-01": ["Q-999"]}, g)["requirements"][0]
    assert reopened["decision_status"] == "UNRESOLVED" and "decision_basis" not in reopened
    assert reopened["open_point"] == {"origin": "normative_ambiguity", "source": "agent_verified"}
