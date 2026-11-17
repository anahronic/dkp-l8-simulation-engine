"""Catalogue of SYNTHETIC change dossiers that exercise every path of the L8 gate (DKP-8-SIMULATION-001 §5-§8, §12).

Every scenario here is a labelled synthetic fixture: its traces are written by hand to trigger one rule, carry
``synthetic: true`` and ``provenance.kind: synthetic_fixture``, and are not evidence about any real system.  Historical
(PTL) scenarios cannot be built: no PTL dataset exists (BLOCKED_BY_EMPIRICAL_DATA).

Each entry: ``{"id", "purpose", "dossier", "expect"}`` where ``expect`` is the decision under the canonical trust
store (no authority, no node) - or ``"REFUSED"`` for dossiers the gate must reject as input.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

from dkp8.canonical import digest

LABEL = "SYNTHETIC FIXTURE - not empirical evidence, not an operational output"
SYN = {"kind": "synthetic_fixture", "ref": "dkp8/scenarios.py"}
STATE = "a" * 64


def _trace(**over) -> Dict[str, Any]:
    t = {
        "label": LABEL,
        "axioms": {a: {"outcome": "respected", "provenance": dict(SYN)} for a in ("A1", "A2", "A3", "A4", "A5", "A6", "A7")},
        "scope": {"touched": ["L5"], "permitted": ["L5"], "provenance": dict(SYN)},
        "loss_of_life": {"baseline": 0, "change": 0},
        "authority": {"initial": ["schedule_shifts"], "held": [["schedule_shifts"]] * 4},
        "rollback": {"tested": True, "pre_change_state_sha256": STATE, "restored_state_sha256": STATE, "steps": 2,
                     "allowed_steps": 5},
        "metrics": {"deficit_hours": ["0", "1", "1", "0"]},
        "components_failed": [0, 0, 0, 0],
        "pending_work": [1, 1, 0, 0], "state_changed": [True, True, True, True],
        "boundary_flows": [{"to": "neighbouring district", "harm": "0", "measured": True, "displaced": False}],
        "live_effects": False,
    }
    t.update(over)
    return t


def _scenario(name, kind, trace, **over):
    inputs = {"declared": True, "version": "1", "sha256": digest(trace), "source": "synthetic:" + name, "synthetic": True}
    s = {"name": name, "kind": kind, "inputs": inputs,
         "input_handling": {f: False for f in ("unphysical", "bypass_ptl", "smoothed", "normalized", "cherry_picked",
                                               "selective_sampling")},
         "run": {"result_id": digest({"trace": trace, "name": name}), "deterministic": True}, "trace": trace}
    for key, value in over.items():
        s[key] = value
    return s


def _dossier(cid, scenarios, **over):
    d = {"schema": "dkp-l8-change-dossier/1", "label": LABEL,
         "change": {"id": cid, "kind": "parameter", "target_protocol": "DKP-5-WORK-CYCLE-001",
                    "description": "synthetic parameter change used to exercise the gate"},
         "risk_envelope": {"deficit_hours": {"max": "2", "provenance": dict(SYN)}},
         "detector_parameters": {"deadlock_steps": 3},
         "scenarios": scenarios, "reproductions": [],
         "required_independent_nodes": {"value": 2, "provenance": {"kind": "synthetic_fixture", "ref": "fixture"}}}
    d.update(over)
    return d


def _base():
    return [_scenario("syn-normal", "synthetic", _trace()),
            _scenario("adv-surge", "adversarial", _trace(metrics={"deficit_hours": ["0", "2", "1", "1"]})),
            _scenario("bnd-minimum-staff", "boundary", _trace(metrics={"deficit_hours": ["1", "2", "2", "1"]}))]


def catalog() -> List[Dict[str, Any]]:
    out = []

    def add(cid, purpose, dossier, expect):
        out.append({"id": cid, "purpose": purpose, "dossier": dossier, "expect": expect, "label": LABEL})

    add("clean-synthetic", "all checks pass on synthetic data; still NOT_ESTABLISHED (synthetic only, no author-"
        "defined node count, no independent node)", _dossier("clean", _base()), "NOT_ESTABLISHED")
    s = _base(); s[0] = _scenario("syn-authority", "synthetic", _trace(authority={"initial": ["schedule_shifts"],
        "held": [["schedule_shifts"], ["schedule_shifts", "override_rest_days"]]}))
    add("authority-expansion", "non-expansion of authority violated (§6) -> invalidates the change", _dossier("auth", s), "BLOCKED")
    s = _base(); s[0] = _scenario("syn-axiom", "synthetic", _trace(axioms={**_trace()["axioms"],
        "A1": {"outcome": "violated", "provenance": dict(SYN)}}))
    add("axiom-violation-f1", "declared A1 violation -> F1 (§7)", _dossier("f1", s), "BLOCKED")
    s = _base(); s[0] = _scenario("syn-scope", "synthetic", _trace(scope={"touched": ["L5", "L3"], "permitted": ["L5"],
        "provenance": dict(SYN)}))
    add("scope-violation-f1", "touches a layer outside the permitted scope -> F1", _dossier("scope", s), "BLOCKED")
    s = _base(); s[1] = _scenario("adv-cascade", "adversarial", _trace(components_failed=[1, 2, 4, 8]))
    add("cascade-f2", "cascading failure under an adversarial scenario -> F2", _dossier("f2c", s), "BLOCKED")
    s = _base(); s[1] = _scenario("adv-runaway", "adversarial", _trace(metrics={"deficit_hours": ["1", "3", "4", "6"]}))
    add("runaway-f2", "runaway beyond the envelope -> F2 and envelope breach", _dossier("f2r", s), "BLOCKED")
    s = _base(); s[1] = _scenario("adv-deadlock", "adversarial", _trace(pending_work=[2, 2, 2, 2],
        state_changed=[True, False, False, False]))
    add("deadlock-f2", "pending work with a frozen state for 3 steps -> F2", _dossier("f2d", s), "BLOCKED")
    s = _base(); s[2] = _scenario("bnd-irreversible", "boundary", _trace(rollback={"tested": True,
        "pre_change_state_sha256": STATE, "restored_state_sha256": "b" * 64, "steps": 2, "allowed_steps": 5}))
    add("irreversible-f3", "rollback does not restore the state -> F3", _dossier("f3", s), "BLOCKED")
    s = _base(); s[0] = _scenario("syn-leak", "synthetic", _trace(boundary_flows=[{"to": "downstream river basin",
        "harm": "3", "measured": False, "displaced": True}]))
    add("externality-f4", "unmeasured displaced harm -> F4 redesign", _dossier("f4", s), "REDESIGN_REQUIRED")
    s = _base(); s[0] = _scenario("syn-life", "synthetic", _trace(loss_of_life={"baseline": 0, "change": 1}))
    add("life-violation", "loss of life rises against baseline -> invariant violation", _dossier("life", s), "BLOCKED")
    s = _base(); s[0]["input_handling"]["smoothed"] = True
    add("smoothed-input", "smoothed input is inadmissible (§5); the rest stays NOT_ESTABLISHED", _dossier("smooth", s), "NOT_ESTABLISHED")
    s = _base(); del s[1]
    add("no-adversarial", "no adversarial scenario -> §8 not shown", _dossier("noadv", s), "NOT_ESTABLISHED")
    s = _base(); s[0] = _scenario("syn-no-rollback", "synthetic", _trace(rollback={"tested": False}))
    add("rollback-untested", "reversibility not simulated -> not evaluable, never a pass", _dossier("norb", s), "NOT_ESTABLISHED")
    d = _dossier("index", _base()); d["change"] = {**d["change"], "kind": "composite_index",
        "index": {"name": "B(t)", "formula": "", "inputs": [], "weights": {}}}
    add("composite-unspecified", "composite index without model, inputs, weights, uncertainty (§9)", d, "NOT_ESTABLISHED")
    d = _dossier("emergency", _base()); d["override"] = {"by": "emergency", "reason": "urgent"}
    add("override-refused", "an emergency override is refused as input (§12)", d, "REFUSED")
    d = _dossier("appeal", _base()); d["appeal"] = {"of": "f2c"}
    add("appeal-refused", "a failed simulation cannot be appealed (§12)", d, "REFUSED")
    h = _scenario("hist-ptl", "historical", _trace())
    h["inputs"]["source"] = "synthetic:no-ptl-dataset-exists"
    add("historical-without-ptl", "a 'historical' scenario without a PTL source is inadmissible (no PTL data exists)",
        _dossier("hist", _base() + [h]), "NOT_ESTABLISHED")
    return out


def get(cid: str) -> Dict[str, Any]:
    return copy.deepcopy(next(c for c in catalog() if c["id"] == cid))
