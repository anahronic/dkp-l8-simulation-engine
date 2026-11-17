"""Invariant registry for DKP-8-SIMULATION-001 §6 and the checks that can be computed from a simulation trace.

§6 lists six invariant groups.  Each entry records how far it can be checked by software today:

* COMPUTABLE — a structural property of the declared trace (authority sets, rollback test);
* PARTIAL — computable once an author confirms the machine form of the rule (scope map);
* BLOCKED_BY_NORMATIVE_DECISION — the corpus names the constraint but not its metric/threshold (life);
* BLOCKED_BY_EMPIRICAL_DATA — the metric needs a calibrated model and PTL data (biosphere / B(t));
* NOT_COMPUTABLE — normative statements without a machine model (axioms A1-A7): only declared evaluations with
  provenance are accepted, and they are reported as declared evidence, not as computed results.

A check returns VIOLATION, NO_VIOLATION or NOT_EVALUABLE.  NOT_EVALUABLE is never treated as a pass: the gate
reports the change as NOT_ESTABLISHED.  A VIOLATION always invalidates the change (§6 last sentence).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

from dkp8.canonical import is_decimal

VIOLATION, NO_VIOLATION, NOT_EVALUABLE = "VIOLATION", "NO_VIOLATION", "NOT_EVALUABLE"
AXIOMS = {"A1": "Preservation of Life", "A2": "Systemic Sustainability", "A3": "Physical Reality Supremacy",
          "A4": "Irreversibility Aversion", "A5": "Externality Accountability", "A6": "Truth Priority",
          "A7": "Minimum Suffering Constraint"}
EVIDENCE_KINDS = ("ptl_dataset", "simulation_output", "author_decision", "synthetic_fixture")

REGISTRY: List[Dict[str, Any]] = [
    {"id": "INV-AXIOMS", "text": "all axioms (DKP-1-AXIOMS-001)", "failure_class": "F1",
     "computability": "NOT_COMPUTABLE",
     "how": "one declared evaluation per axiom A1-A7 with provenance; any missing axiom -> NOT_EVALUABLE",
     "open": "Axioms are normative statements; no machine model of A1-A7 exists in the corpus."},
    {"id": "INV-SCOPE", "text": "scope and conflict rules (DKP-7-SCOPE-001)", "failure_class": "F1",
     "computability": "PARTIAL",
     "how": "layers/domains touched by the change must be a subset of those the change is permitted to touch",
     "open": "The permitted-layer map is declared by the dossier; its derivation from SCOPE needs author review."},
    {"id": "INV-LIFE", "text": "life-preservation constraints", "failure_class": None,
     "computability": "BLOCKED_BY_NORMATIVE_DECISION",
     "how": "any increase of loss of life against the baseline scenario is a violation; equality is not a pass",
     "open": "The corpus does not define the life-preservation metric or tolerance used in simulation."},
    {"id": "INV-BIOSPHERE", "text": "biosphere integrity constraints", "failure_class": None,
     "computability": "BLOCKED_BY_EMPIRICAL_DATA",
     "how": "B(t) series against B_min with provenance; without a calibrated B(t) model -> NOT_EVALUABLE",
     "open": "B(t) model, aggregation and weights are undefined (ORACLE §12, Q-017); no PTL data exists."},
    {"id": "INV-AUTHORITY", "text": "non-expansion of authority", "failure_class": None,
     "computability": "COMPUTABLE",
     "how": "the set of powers held at any step must be a subset of the powers held before the change"},
    {"id": "INV-REVERSIBILITY", "text": "reversibility and rollback requirements", "failure_class": "F3",
     "computability": "COMPUTABLE",
     "how": "a simulated rollback must restore the pre-change state digest within the declared step budget"},
]


def _result(inv_id, outcome, detail, computed=True):
    entry = next(i for i in REGISTRY if i["id"] == inv_id)
    return {"invariant": inv_id, "outcome": outcome, "detail": detail, "failure_class": entry["failure_class"],
            "computability": entry["computability"], "computed": computed}


def _evidence_ok(record) -> bool:
    prov = (record or {}).get("provenance") or {}
    return prov.get("kind") in EVIDENCE_KINDS and bool(prov.get("ref"))


def check_axioms(trace: Dict[str, Any]) -> Dict[str, Any]:
    evals = trace.get("axioms") or {}
    missing = [a for a in AXIOMS if a not in evals or not _evidence_ok(evals[a])]
    violated = [a for a in AXIOMS if a in evals and evals[a].get("outcome") == "violated" and _evidence_ok(evals[a])]
    if violated:
        return _result("INV-AXIOMS", VIOLATION, "declared violation of " + ", ".join(violated), computed=False)
    if missing or any(evals[a].get("outcome") != "respected" for a in AXIOMS):
        return _result("INV-AXIOMS", NOT_EVALUABLE, "no evaluation with provenance for " + ", ".join(missing or
                       [a for a in AXIOMS if evals[a].get("outcome") != "respected"]), computed=False)
    return _result("INV-AXIOMS", NO_VIOLATION, "declared evaluations for A1-A7 (not computed by L8)", computed=False)


def check_scope(trace: Dict[str, Any]) -> Dict[str, Any]:
    scope = trace.get("scope")
    if not scope or not isinstance(scope.get("touched"), list) or not isinstance(scope.get("permitted"), list):
        return _result("INV-SCOPE", NOT_EVALUABLE, "touched/permitted scope not declared")
    outside = sorted(set(scope["touched"]) - set(scope["permitted"]))
    if outside:
        return _result("INV-SCOPE", VIOLATION, "touches outside the permitted scope: " + ", ".join(outside))
    if not _evidence_ok(scope):
        return _result("INV-SCOPE", NOT_EVALUABLE, "permitted scope has no provenance")
    return _result("INV-SCOPE", NO_VIOLATION, "touched scope within the declared permitted scope")


def check_life(trace: Dict[str, Any]) -> Dict[str, Any]:
    life = trace.get("loss_of_life")
    if not life or not isinstance(life.get("baseline"), int) or not isinstance(life.get("change"), int):
        return _result("INV-LIFE", NOT_EVALUABLE, "loss of life (baseline and change) not reported")
    if life["change"] > life["baseline"]:
        return _result("INV-LIFE", VIOLATION, f"loss of life rises from {life['baseline']} to {life['change']}")
    definition = life.get("metric_definition") or {}
    if (definition.get("provenance") or {}).get("kind") == "author_decision" and (definition.get("provenance") or {}).get("ref"):
        return _result("INV-LIFE", NO_VIOLATION, "no increase under the author-defined life-preservation metric "
                       + str(definition["provenance"]["ref"]))
    return _result("INV-LIFE", NOT_EVALUABLE, "no increase in loss of life; the full life-preservation metric is "
                   "undefined in the corpus, so this is not a pass")


def check_biosphere(trace: Dict[str, Any]) -> Dict[str, Any]:
    bio = trace.get("biosphere")
    if not bio or not isinstance(bio.get("values"), list) or not is_decimal(bio.get("minimum")):
        return _result("INV-BIOSPHERE", NOT_EVALUABLE, "no calibrated biosphere series and minimum")
    if not _evidence_ok(bio) or (bio.get("provenance") or {}).get("kind") == "synthetic_fixture":
        return _result("INV-BIOSPHERE", NOT_EVALUABLE, "biosphere series lacks empirical provenance")
    try:
        low = min(Decimal(v) for v in bio["values"])
    except (InvalidOperation, TypeError, ValueError):
        return _result("INV-BIOSPHERE", NOT_EVALUABLE, "biosphere values are not decimal strings")
    if low < Decimal(bio["minimum"]):
        return _result("INV-BIOSPHERE", VIOLATION, f"{bio.get('metric', 'index')} falls to {low} < {bio['minimum']}")
    return _result("INV-BIOSPHERE", NO_VIOLATION, f"{bio.get('metric', 'index')} stays at or above {bio['minimum']}")


def check_authority(trace: Dict[str, Any]) -> Dict[str, Any]:
    auth = trace.get("authority")
    if not auth or not isinstance(auth.get("initial"), list) or not isinstance(auth.get("held"), list):
        return _result("INV-AUTHORITY", NOT_EVALUABLE, "authority sets not reported")
    gained = sorted({p for step in auth["held"] for p in step} - set(auth["initial"]))
    if gained:
        return _result("INV-AUTHORITY", VIOLATION, "powers gained during the run: " + ", ".join(gained))
    return _result("INV-AUTHORITY", NO_VIOLATION, f"no power beyond the initial set across {len(auth['held'])} steps")


def check_reversibility(trace: Dict[str, Any]) -> Dict[str, Any]:
    rb = trace.get("rollback")
    if not rb or not rb.get("tested"):
        return _result("INV-REVERSIBILITY", NOT_EVALUABLE, "rollback was not simulated")
    if rb.get("restored_state_sha256") != rb.get("pre_change_state_sha256") or not rb.get("pre_change_state_sha256"):
        return _result("INV-REVERSIBILITY", VIOLATION, "rollback does not restore the pre-change state")
    budget = rb.get("allowed_steps")
    if not isinstance(budget, int):
        return _result("INV-REVERSIBILITY", NOT_EVALUABLE, "no declared rollback constraint (step budget)")
    if rb.get("steps", budget + 1) > budget:
        return _result("INV-REVERSIBILITY", VIOLATION, f"rollback needs {rb.get('steps')} steps > declared {budget}")
    return _result("INV-REVERSIBILITY", NO_VIOLATION, f"state restored in {rb['steps']} of {budget} allowed steps")


CHECKS = (check_axioms, check_scope, check_life, check_biosphere, check_authority, check_reversibility)


def evaluate(trace: Dict[str, Any]) -> List[Dict[str, Any]]:
    """All six §6 invariant groups for one scenario trace."""
    return [check(trace or {}) for check in CHECKS]
