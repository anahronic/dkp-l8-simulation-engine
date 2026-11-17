"""L8 Calibration Bundle: schema, signing, verification, validity and expiry (DKP-8-SIMULATION-001 §3, §4, §9, §10).

A bundle is ``{"schema", "body", "signatures"}``; ``bundle_id`` is the SHA-256 of the canonical ``body``; each
signature covers the canonical ``body``.  The body holds what §9 lists — thresholds, model specifications,
aggregation logic, confidence bounds, a time-bounded validity window, environmental assumptions — plus what makes the
bundle checkable: the target, the simulation runs and gate decision it rests on, recalibration triggers (§10), the
bundle it supersedes, and a ``data_status``.

Fail-closed rules (no fabricated values):
* every value carries ``provenance``: ``ptl_dataset``, ``author_decision``, ``simulation_output`` or
  ``synthetic_fixture``; a value without provenance makes the bundle invalid;
* any ``synthetic_fixture`` provenance forces ``data_status: SYNTHETIC``; a SYNTHETIC bundle is never enforceable;
* non-integer quantities are decimal strings (see :mod:`dkp8.canonical`);
* enforceability needs a VALID_AUTHORITY signature; development and test keys never qualify.

Expiry (§10 "Calibration Expiration Epistemic Handling"): outside the validity window outputs carry
``validity_state: INVALID``, ``reason: "Calibration expired"``, ``remediation: "Awaiting recalibration"``, and
:func:`apply_to_output` removes every calibrated value (no legacy values persist).  A successful recalibration is a
new bundle that ``supersedes`` the old one; it restores VALID for new evaluations.  Whether a recalibration trigger
suspends a bundle before its window ends is author question Q-034: the state is then INDETERMINATE and enforcement
is refused (fail-closed) without choosing a reading.
"""
from __future__ import annotations

import copy
import datetime as dt
import re
from typing import Any, Dict, Iterable, List, Optional

from dkp8 import trust
from dkp8.canonical import CanonicalError, canonical, digest, is_decimal

SCHEMA = "dkp-l8-calibration-bundle/1"
KINDS = ("protocol_modification", "parameter", "composite_index", "activation_condition", "enforcement_condition",
         "onboarding", "exit", "integration", "interop", "cross_layer_dependency")
PROVENANCE = ("ptl_dataset", "author_decision", "simulation_output", "synthetic_fixture")
TRIGGERS = ("environmental_drift", "regime_change", "sensor_class_change", "audit_divergence", "dependency_update")
SECTIONS = ("thresholds", "models", "aggregation", "confidence_bounds", "environmental_assumptions")
EXPIRED = {"validity_state": "INVALID", "reason": "Calibration expired", "remediation": "Awaiting recalibration"}
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
HEX64 = re.compile(r"[0-9a-f]{64}")
PROTOCOL = re.compile(r"(DKP-[0-9]-[A-Z-]+-[0-9]{3}(-PATCH)?|CODE-OF-PLANETARY-SYNERGY)")


def parse_utc(text: str) -> dt.datetime:
    if not isinstance(text, str) or not UTC.fullmatch(text):
        raise ValueError(f"not a UTC timestamp YYYY-MM-DDTHH:MM:SSZ: {text!r}")
    return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def bundle_id(bundle: Dict[str, Any]) -> str:
    return digest(bundle["body"])


def _provenance_problems(item: Dict[str, Any], where: str) -> List[str]:
    prov = item.get("provenance")
    if not isinstance(prov, dict) or prov.get("kind") not in PROVENANCE or not prov.get("ref"):
        return [f"{where}: provenance with kind in {PROVENANCE} and ref is required (no value without a source)"]
    if prov["kind"] in ("ptl_dataset", "simulation_output") and not HEX64.fullmatch(str(prov.get("sha256", ""))):
        return [f"{where}: {prov['kind']} provenance needs the sha256 of the referenced artifact"]
    return []


def validate(bundle: Dict[str, Any]) -> List[str]:
    """Structural problems (empty list = well-formed).  Does not check signatures or time."""
    problems: List[str] = []
    if not isinstance(bundle, dict) or bundle.get("schema") != SCHEMA:
        return [f"schema must be {SCHEMA}"]
    body = bundle.get("body")
    if not isinstance(body, dict):
        return ["body must be an object"]
    try:
        canonical(body)
    except CanonicalError as exc:
        problems.append(f"body has no canonical form: {exc}")
    target = body.get("target") or {}
    if target.get("kind") not in KINDS:
        problems.append(f"target.kind must be one of {KINDS}")
    if not isinstance(target.get("protocol_id"), str) or not PROTOCOL.fullmatch(target["protocol_id"]):
        problems.append("target.protocol_id must name a DKP protocol or the Code")
    if not HEX64.fullmatch(str(target.get("source_sha256", ""))):
        problems.append("target.source_sha256 (canonical source of the targeted edition) is required")
    for field in ("issued_at",):
        try:
            parse_utc(body.get(field))
        except ValueError as exc:
            problems.append(f"{field}: {exc}")
    window = body.get("validity_window") or {}
    try:
        if parse_utc(window.get("not_before")) >= parse_utc(window.get("not_after")):
            problems.append("validity_window must be non-empty (not_before < not_after)")
    except ValueError as exc:
        problems.append(f"validity_window (time-bounded, §9): {exc}")
    for section in SECTIONS:
        items = body.get(section)
        if not isinstance(items, list) or not items:
            problems.append(f"{section}: required non-empty list (§9)")
            continue
        for i, item in enumerate(items):
            where = f"{section}[{i}]"
            if not isinstance(item, dict) or not item.get("name"):
                problems.append(f"{where}: object with a name required")
                continue
            problems += _provenance_problems(item, where)
            if section == "thresholds" and not is_decimal(item.get("value")):
                problems.append(f"{where}: value must be a decimal string")
            if section == "confidence_bounds":
                if not (is_decimal(item.get("lower")) and is_decimal(item.get("upper")) and is_decimal(item.get("level"))):
                    problems.append(f"{where}: lower, upper and level must be decimal strings")
                elif float(item["lower"]) > float(item["upper"]):
                    problems.append(f"{where}: lower > upper")
            if section == "aggregation":
                problems += composite_problems(item, where)
    triggers = body.get("recalibration_triggers")
    if not isinstance(triggers, list) or set(triggers) != set(TRIGGERS):
        problems.append(f"recalibration_triggers must list all §10 triggers {TRIGGERS}")
    sim = body.get("simulation") or {}
    runs = sim.get("runs")
    if not isinstance(runs, list) or not runs or not all(HEX64.fullmatch(str(r.get("result_id", ""))) for r in runs):
        problems.append("simulation.runs: the result_id of every simulation the bundle rests on is required")
    if not HEX64.fullmatch(str(sim.get("gate_decision_sha256", ""))):
        problems.append("simulation.gate_decision_sha256: the acceptance-gate decision is required")
    synthetic = any((it.get("provenance") or {}).get("kind") == "synthetic_fixture"
                    for s in SECTIONS for it in (body.get(s) or []) if isinstance(it, dict))
    if body.get("data_status") not in ("SYNTHETIC", "EMPIRICAL"):
        problems.append("data_status must be SYNTHETIC or EMPIRICAL")
    elif synthetic and body["data_status"] != "SYNTHETIC":
        problems.append("data_status must be SYNTHETIC when any value comes from a synthetic fixture")
    if body.get("supersedes") is not None and not HEX64.fullmatch(str(body["supersedes"])):
        problems.append("supersedes must be null or a bundle_id")
    if body.get("operational_use") is not False and body.get("data_status") == "SYNTHETIC":
        problems.append("a SYNTHETIC bundle must declare operational_use: false")
    return problems


def composite_problems(spec: Dict[str, Any], where: str = "index") -> List[str]:
    """§9 composite indices: model fully specified in L8, all inputs and weights declared, uncertainty propagated."""
    out = []
    inputs = spec.get("inputs")
    weights = spec.get("weights")
    if not isinstance(spec.get("formula"), str) or not spec["formula"].strip():
        out.append(f"{where}: formula (the full model) is required")
    if not isinstance(inputs, list) or not inputs or not all(isinstance(i, dict) and i.get("name") and i.get("ptl_output")
                                                              for i in inputs):
        out.append(f"{where}: every input must be declared with its raw PTL output")
    if not isinstance(weights, dict) or not all(is_decimal(v) for v in weights.values()):
        out.append(f"{where}: weights must be declared as decimal strings")
    elif isinstance(inputs, list) and {i.get("name") for i in inputs if isinstance(i, dict)} != set(weights):
        out.append(f"{where}: weights must be declared for exactly the declared inputs")
    if not isinstance(spec.get("uncertainty_propagation"), str) or not spec["uncertainty_propagation"].strip():
        out.append(f"{where}: uncertainty propagation method is required")
    if spec.get("defined_in") not in (None, "L8"):
        out.append(f"{where}: composite index models are defined only in L8 (SHALL NOT be modified outside L8)")
    return out


def sign(bundle: Dict[str, Any], secret: bytes) -> Dict[str, Any]:
    out = copy.deepcopy(bundle)
    out.setdefault("signatures", []).append(trust.sign_document(out["body"], secret))
    return out


def signature_verdicts(bundle: Dict[str, Any], store: Dict[str, Any]) -> List[str]:
    sigs = bundle.get("signatures") or []
    return [trust.verify_signature(bundle["body"], s, store) for s in sigs] or [trust.UNSIGNED]


def status(bundle: Dict[str, Any], at: str, store: Dict[str, Any], events: Iterable[Dict[str, Any]] = (),
           superseded_by: Optional[str] = None) -> Dict[str, Any]:
    """Validity of ``bundle`` at UTC time ``at`` and whether it may support enforcement (§4, §9, §10).

    ``events``: recorded recalibration triggers ``{"trigger": <§10 trigger>, "at": UTC, "ref": ...}``.
    Never returns enforceable=True unless: well-formed, EMPIRICAL, signed by a designated authority, not revoked,
    not superseded, inside the window and no unresolved trigger.
    """
    problems = validate(bundle)
    result: Dict[str, Any] = {"bundle_id": None, "problems": problems, "signatures": [], "enforceable": False}
    if problems:
        result.update(validity_state="INVALID", reason="Malformed calibration bundle", remediation="Awaiting recalibration")
        return result
    bid = bundle_id(bundle)
    body = bundle["body"]
    result["bundle_id"] = bid
    verdicts = signature_verdicts(bundle, store)
    result["signatures"] = verdicts
    now = parse_utc(at)
    start, end = parse_utc(body["validity_window"]["not_before"]), parse_utc(body["validity_window"]["not_after"])
    fired = sorted({e["trigger"] for e in events if e.get("trigger") in TRIGGERS and parse_utc(e["at"]) >= parse_utc(body["issued_at"])
                    and parse_utc(e["at"]) <= now})
    if bid in store.get("revoked_bundles", []) or trust.REVOKED_KEY in verdicts:
        state = {"validity_state": "INVALID", "reason": "Calibration bundle revoked", "remediation": "Awaiting recalibration"}
    elif not any(v in (trust.VALID_AUTHORITY, trust.VALID_DEVELOPMENT_ONLY, trust.VALID_TEST_ONLY) for v in verdicts):
        state = {"validity_state": "INVALID", "reason": "Calibration bundle not validly signed", "remediation": "Awaiting recalibration"}
    elif superseded_by:
        state = {"validity_state": "INVALID", "reason": "Superseded by recalibration", "remediation": f"Use bundle {superseded_by}"}
    elif now >= end:
        state = dict(EXPIRED)
    elif now < start:
        state = {"validity_state": "INVALID", "reason": "Calibration not yet valid", "remediation": "Awaiting validity window"}
    elif fired:
        state = {"validity_state": "INDETERMINATE", "reason": "Recalibration trigger recorded: " + ", ".join(fired),
                 "remediation": "Recalibration required; whether the bundle is suspended meanwhile is author question Q-034"}
    else:
        state = {"validity_state": "VALID"}
    result.update(state)
    blockers = []
    if result["validity_state"] != "VALID":
        blockers.append(result["reason"])
    if trust.VALID_AUTHORITY not in verdicts:
        blockers.append("no signature by a designated L8 authority (none is designated in the corpus)")
    if body["data_status"] != "EMPIRICAL":
        blockers.append("synthetic calibration values (data_status SYNTHETIC)")
    result["enforcement_blockers"] = blockers
    result["enforceable"] = not blockers
    result["development_or_test_signature"] = any(v in (trust.VALID_DEVELOPMENT_ONLY, trust.VALID_TEST_ONLY) for v in verdicts)
    return result


def calibrated_names(bundle: Dict[str, Any]) -> List[str]:
    body = bundle.get("body", {})
    return sorted({it["name"] for s in SECTIONS for it in body.get(s, []) if isinstance(it, dict) and "name" in it})


def apply_to_output(output: Dict[str, Any], bundle: Optional[Dict[str, Any]], bundle_status: Optional[Dict[str, Any]]):
    """Attach epistemic metadata to one L8-dependent output; strip calibrated values unless the bundle is VALID.

    ``output["calibrated"]`` maps calibrated quantity names to the values computed with the bundle.  When the bundle
    is missing or not VALID these values are removed (no legacy calibration values persist past expiry) and the
    output is marked not enforceable.
    """
    out = copy.deepcopy(output)
    if bundle is None or bundle_status is None:
        out["epistemic"] = {"validity_state": "INVALID", "reason": "No calibration bundle",
                            "remediation": "Awaiting calibration"}
        out["calibrated"] = {}
        out["enforceable"] = False
        return out
    if bundle_status.get("validity_state") == "VALID":
        out["epistemic"] = {"validity_state": "VALID", "bundle_id": bundle_status["bundle_id"]}
        out["enforceable"] = bool(bundle_status.get("enforceable"))
        return out
    out["epistemic"] = {k: bundle_status[k] for k in ("validity_state", "reason", "remediation") if k in bundle_status}
    out["epistemic"]["bundle_id"] = bundle_status.get("bundle_id")
    out["removed_calibrated_values"] = sorted(out.get("calibrated", {}))
    out["calibrated"] = {}
    out["enforceable"] = False
    return out


def template(target: Dict[str, Any]) -> Dict[str, Any]:
    """An unsigned bundle skeleton with every §9 section present and every value missing (for the workbench)."""
    missing = {"kind": None, "ref": None}
    return {"schema": SCHEMA, "body": {
        "target": target, "issued_at": None, "validity_window": {"not_before": None, "not_after": None},
        "thresholds": [{"name": None, "value": None, "unit": None, "provenance": dict(missing)}],
        "models": [{"name": None, "specification": None, "version": None, "provenance": dict(missing)}],
        "aggregation": [{"name": None, "formula": None, "inputs": [], "weights": {}, "uncertainty_propagation": None,
                         "defined_in": "L8", "provenance": dict(missing)}],
        "confidence_bounds": [{"name": None, "lower": None, "upper": None, "level": None, "method": None,
                               "provenance": dict(missing)}],
        "environmental_assumptions": [{"name": None, "statement": None, "provenance": dict(missing)}],
        "recalibration_triggers": list(TRIGGERS),
        "simulation": {"runs": [], "gate_decision_sha256": None},
        "supersedes": None, "data_status": None, "operational_use": False}, "signatures": []}
