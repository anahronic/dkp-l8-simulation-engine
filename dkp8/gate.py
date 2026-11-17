"""Fail-closed acceptance gate of DKP-8-SIMULATION-001 (§5 inputs, §6 invariants, §7 F1-F4, §8 acceptance, §12).

Input: a change dossier (schema ``dkp-l8-change-dossier/1``).  Output: a decision, deterministic and canonical, with
every reason and every piece of missing evidence:

* ``BLOCKED`` — an invariant violation, an F1/F2/F3 failure or a risk-envelope breach (§6, §7, §8);
* ``REDESIGN_REQUIRED`` — an F4 externality leak without any blocking failure (§7);
* ``NOT_ESTABLISHED`` — evidence required by §8 is missing or not evaluable (missing validation is never a pass);
* ``ELIGIBLE`` — every §8 condition is shown.  Eligibility permits, never mandates, deployment (§8).

There is no override: a dossier that asks for one (political, economic, emergency, human authority) or appeals a
failure is refused as input (§12).  Operational detector definitions for F2 (runaway, cascade, deadlock, collapse)
are not given by the corpus; the ones used are listed in the decision for author review.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

from dkp8 import invariants, reproduction
from dkp8.canonical import digest, is_decimal

SCHEMA = "dkp-l8-change-dossier/1"
DECISION_SCHEMA = "dkp-l8-gate-decision/1"
SCENARIO_KINDS = ("historical", "synthetic", "adversarial", "boundary")
FORBIDDEN_HANDLING = ("unphysical", "bypass_ptl", "smoothed", "normalized", "cherry_picked", "selective_sampling")
OVERRIDE_KEYS = ("override", "overrides", "appeal", "emergency_override", "waiver", "exception")
ORDER = {"BLOCKED": 3, "REDESIGN_REQUIRED": 2, "NOT_ESTABLISHED": 1, "ELIGIBLE": 0}
# Operational definitions (L8 engineering, not normative text) - reported with every decision.
OPERATIONAL = {
    "runaway": "a metric with a declared envelope exceeds it and its last three values strictly increase",
    "cascade": "failed components strictly increase over at least three consecutive steps and at least double",
    "deadlock": "pending work > 0 while the state does not change for at least `deadlock_steps` steps (declared)",
    "collapse": "a metric declared critical reaches zero",
}


class DossierError(ValueError):
    """The dossier is refused as input (e.g. it requests an override)."""


def _dec(v):
    try:
        return Decimal(v)
    except (InvalidOperation, TypeError, ValueError):
        return None


def admissibility(s: Dict[str, Any]) -> List[str]:
    """§5: declared, versioned, reproducible; no unphysical, PTL-bypassing, smoothed or selectively sampled input."""
    problems = []
    inp = s.get("inputs") or {}
    if not inp.get("declared"):
        problems.append("inputs not declared")
    if not inp.get("version"):
        problems.append("inputs not versioned")
    if not (isinstance(inp.get("sha256"), str) and len(inp["sha256"]) == 64):
        problems.append("inputs not reproducible (no content hash)")
    handling = s.get("input_handling") or {}
    for flag in FORBIDDEN_HANDLING:
        if handling.get(flag) is not False:
            problems.append(f"input handling '{flag}' not declared false")
    if s.get("kind") == "historical" and not str(inp.get("source", "")).startswith("ptl:"):
        problems.append("historical scenario without a PTL source")
    if s.get("kind") not in SCENARIO_KINDS:
        problems.append(f"scenario kind must be one of {SCENARIO_KINDS}")
    if not (s.get("run") or {}).get("result_id"):
        problems.append("no run result_id (deterministic re-execution impossible)")
    return problems


def _series(trace, name):
    return [_dec(v) for v in (trace.get("metrics") or {}).get(name, [])]


def instability(trace: Dict[str, Any], envelope: Dict[str, Any], params: Dict[str, Any]) -> List[str]:
    """F2 detectors over the trace (see OPERATIONAL)."""
    found = []
    for name, bounds in envelope.items():
        values = _series(trace, name)
        top = _dec((bounds or {}).get("max"))
        if values and top is not None and None not in values and max(values) > top:
            tail = values[-3:]
            if len(tail) == 3 and tail[0] < tail[1] < tail[2]:
                found.append(f"runaway: {name} exceeds {top} and keeps rising")
    failed = trace.get("components_failed") or []
    run = 1
    for i in range(1, len(failed)):
        run = run + 1 if failed[i] > failed[i - 1] else 1
        if run >= 3 and failed[i] >= 2 * max(failed[i - run + 1], 1):
            found.append(f"cascade: failed components {failed[i - run + 1]} -> {failed[i]}")
            break
    pending, changed = trace.get("pending_work") or [], trace.get("state_changed") or []
    k = params.get("deadlock_steps")
    if pending and changed and isinstance(k, int):
        still = 0
        for p, c in zip(pending, changed):
            still = still + 1 if (p > 0 and not c) else 0
            if still >= k:
                found.append(f"deadlock: no state change for {k} steps with pending work")
                break
    for name in trace.get("critical_metrics") or []:
        values = _series(trace, name)
        if values and None not in values and min(values) <= 0:
            found.append(f"collapse: critical metric {name} reaches zero")
    return found


def envelope_breaches(trace, envelope) -> List[str]:
    out = []
    for name, bounds in envelope.items():
        values = _series(trace, name)
        top, low = _dec((bounds or {}).get("max")), _dec((bounds or {}).get("min"))
        if not values:
            out.append(f"{name}: not reported (envelope cannot be checked)")
        elif None in values:
            out.append(f"{name}: non-decimal values")
        elif (top is not None and max(values) > top) or (low is not None and min(values) < low):
            out.append(f"{name}: outside [{low}, {top}]")
    return out


def externality(trace) -> List[str]:
    leaks = []
    for flow in trace.get("boundary_flows") or []:
        harm = _dec(flow.get("harm"))
        if harm is not None and harm > 0 and (flow.get("measured") is False or flow.get("displaced") is True):
            leaks.append(f"{'displaced' if flow.get('displaced') else 'unmeasured'} harm {harm} to {flow.get('to', 'outside')}")
    return leaks


def evaluate(dossier: Dict[str, Any], store: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(dossier, dict) or dossier.get("schema") != SCHEMA:
        raise DossierError(f"dossier schema must be {SCHEMA}")
    asked = [k for k in OVERRIDE_KEYS if k in dossier or k in (dossier.get("change") or {})]
    if asked:
        raise DossierError("SIMULATION §12: outcomes cannot be overridden or appealed; refused field(s): " + ", ".join(asked))
    change = dossier.get("change") or {}
    envelope = dossier.get("risk_envelope") or {}
    params = dossier.get("detector_parameters") or {}
    blocked, redesign, missing, notes = [], [], [], []
    if not envelope:
        missing.append("no declared risk envelope (§8 'risk envelopes within declared bounds')")
    elif not all(((b or {}).get("provenance") or {}).get("kind") for b in envelope.values()):
        missing.append("risk envelope bounds without provenance")
    scenarios, admitted = [], []
    for s in dossier.get("scenarios") or []:
        problems = admissibility(s)
        rec = {"name": s.get("name"), "kind": s.get("kind"), "admissible": not problems, "inadmissible_because": problems,
               "synthetic": bool((s.get("inputs") or {}).get("synthetic")), "classes": [], "invariants": [],
               "instability": [], "envelope": [], "externality": []}
        scenarios.append(rec)
        if problems:
            continue
        admitted.append(rec)
        trace = s.get("trace") or {}
        rec["invariants"] = invariants.evaluate(trace)
        for r in rec["invariants"]:
            if r["outcome"] == invariants.VIOLATION:
                blocked.append(f"{rec['name']}: invariant {r['invariant']} violated ({r['detail']})")
                if r["failure_class"]:
                    rec["classes"].append(r["failure_class"])
            elif r["outcome"] == invariants.NOT_EVALUABLE:
                missing.append(f"{rec['name']}: {r['invariant']} not evaluable ({r['detail']})")
        rec["instability"] = instability(trace, envelope, params)
        if rec["instability"]:
            rec["classes"].append("F2")
            blocked += [f"{rec['name']}: F2 {x}" for x in rec["instability"]]
        rec["envelope"] = envelope_breaches(trace, envelope) if envelope else []
        for b in rec["envelope"]:
            (missing if "not reported" in b or "non-decimal" in b else blocked).append(f"{rec['name']}: risk envelope {b}")
        rec["externality"] = externality(trace)
        if rec["externality"]:
            rec["classes"].append("F4")
            redesign += [f"{rec['name']}: F4 {x}" for x in rec["externality"]]
        if trace.get("live_effects"):
            blocked.append(f"{rec['name']}: the simulation produced live effects (§3 isolated environment)")
        rec["classes"] = sorted(set(rec["classes"]))
    if not admitted:
        missing.append("no admissible scenario (§5)")
    if not any(r["kind"] == "adversarial" for r in admitted):
        missing.append("no admissible adversarial scenario (§8 stability under adversarial scenarios)")
    if not any(r["kind"] == "historical" for r in admitted):
        notes.append("no historical PTL scenario (none exists; synthetic evidence only)")
    if admitted and all(r["synthetic"] for r in admitted):
        missing.append("all admitted scenarios are synthetic: no empirical evidence")
    rep = reproduction.assess(dossier.get("reproductions") or [], store,
                              [(s.get("run") or {}).get("result_id") for s in dossier.get("scenarios") or []
                               if not admissibility(s)])
    required = dossier.get("required_independent_nodes") or {}
    if not isinstance(required.get("value"), int) or ((required.get("provenance") or {}).get("kind") != "author_decision"):
        missing.append("required number of independent nodes is not defined by an author decision (§8; DKP8-Q-02)")
    elif rep["independent_nodes"] < required["value"]:
        missing.append(f"reproduced by {rep['independent_nodes']} independent node(s); {required['value']} required (§8)")
    if rep["mismatches"]:
        blocked.append("reproduction mismatch: " + "; ".join(rep["mismatches"]) + " (not deterministic, §11)")
    if change.get("kind") == "composite_index":
        from dkp8.bundle import composite_problems
        problems = composite_problems(change.get("index") or {}, "composite index")
        missing += problems
    decision = "ELIGIBLE"
    if missing:
        decision = "NOT_ESTABLISHED"
    if redesign:
        decision = "REDESIGN_REQUIRED"
    if blocked:
        decision = "BLOCKED"
    if any(c in ("F1", "F2", "F3") for r in admitted for c in r["classes"]):
        decision = "BLOCKED"
    out = {
        "schema": DECISION_SCHEMA,
        "change_id": change.get("id"),
        "change_kind": change.get("kind"),
        "target_protocol": change.get("target_protocol"),
        "dossier_sha256": digest(dossier),
        "decision": decision,
        "deployment_mandated": False,
        "override_possible": False,
        "blocking": sorted(set(blocked)),
        "redesign": sorted(set(redesign)),
        "missing_evidence": sorted(set(missing)),
        "notes": notes,
        "scenarios": scenarios,
        "failure_classes": sorted({c for r in admitted for c in r["classes"]}),
        "reproduction": rep,
        "test_identities_used": rep["test_identity_nodes"] > 0,
        "operational_definitions": OPERATIONAL,
        "author_review_required": True,
        "next_step": {"BLOCKED": "redesign and re-simulate (no appeal, §12)",
                      "REDESIGN_REQUIRED": "explicit redesign and re-simulation (§7 F4)",
                      "NOT_ESTABLISHED": "supply the missing evidence and re-run the gate",
                      "ELIGIBLE": "eligible only; produce and sign the Calibration Bundle (§9); deployment is a separate decision"}[decision],
    }
    if out["test_identities_used"]:
        out["notes"].append("TEST IDENTITIES: reproduction nodes are test-only; this decision is a demonstration")
    out["decision_sha256"] = digest({k: v for k, v in out.items() if k != "decision_sha256"})
    return out
