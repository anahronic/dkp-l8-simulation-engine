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
            assert r["open_point"] in (None, {"origin": "implementation_only", "source": "lab_reconciled"}), it["id"]
        else:
            assert it["verdict"] == "reclassified" and it["origin_after"] != "implementation_only", it["id"]
            assert cls[it["id"]]["primary"] == it["origin_after"], it["id"]
            assert r["open_point"] == {"origin": it["origin_after"], "source": "lab_reconciled"}, it["id"]
        if "checkable" in it:
            assert r["checkable"] == it["checkable"]["to"], it["id"]
