"""
INFORMATION AND TRUTH module — DKP-5-INFO-001 on a stream of claims.

Opinions are I0 and never evaluated (§0, §2); factual claims are I1 until a PTL resolution (§5):
consistent → I2, inconsistent → I3; truth is never set by popularity, authority or repetition (§5);
I1 claims never block unrelated operations or trigger enforcement (§6.2); time transitions of I1 need
the L8-calibrated T₁ and T₂ (§6.1), which do not exist (F-014): without a bundle an I1 claim stays I1.
I3 becomes I4 on measurable systemic impact (§7).  Responses (§8): PTL-anchored annotations that keep
the original visible and carry the four mandatory fields; no removal, no penalty for an isolated I3,
annotations never change legal status.  Activation gate (§9): without a valid L8 bundle, classifications
above I1 are informational only and no remediation or escalation is triggered; manual truth is
forbidden.  Abuse (§11) goes to DKP-8-AUDIT-001.  Every classification exposes its verification path
and is reproducible (§12).

Declared readings: H-IN-1 a PTL verdict decides whenever it comes (§5); the §6.1 time rules act only on
claims without a verdict.  H-IN-2 annotations and audit notices are informational disclosures (allowed
without a bundle); reducing amplification and remediation channels are systemic remediation (only with a
bundle).  Time unit: DTI-Day.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError
from lab.modules.time import canonical, dy_doy

ANNOTATION_FIELDS = ("nature_of_inconsistency", "oracle_classes", "probability_of_correspondence", "verification_timestamp")
FAULTS = {
    "remove_record": "an I4 record is deleted",
    "penalize_isolated_i3": "an individual is penalized for an isolated I3 event",
    "evaluate_opinion": "an opinion is classified as a false claim",
    "enforce_without_bundle": "remediation and escalation run without a valid L8 bundle",
    "popularity_truth": "a widely repeated claim is classified as verified",
    "i1_blocks": "an unresolved I1 claim blocks an unrelated operation",
    "annotation_penalty": "an annotation changes the legal status of the author",
    "manual_truth": "an operator sets the truth status by hand",
    "missing_annotation_fields": "an I4 annotation lacks mandatory fields",
    "no_audit_escalation": "systemic abuse is not escalated to AUDIT",
    "suspend_account": "an I3/I4 author's account is suspended",
    "info_overreach": "INFO adjudicates a question of moral truth",
    # checkable cores of provisions whose open point remains (review КТ7-GPT-01)
    "early_annotation": "an unverified claim is downgraded to annotation the day after it is posted, before T1",
    "late_inconsistency_ignored": "a PTL inconsistency emerging after T2 does not reclassify the claim",
}
OUT_OF_SCOPE = ("optimize_narrative", "enforce_social_harmony", "resolve_philosophical_dispute", "adjudicate_moral_truth")   # §13
PERMITTED = ("annotation", "reduce_amplification", "remediation_channel", "systemic_risk_pattern")                         # §8
CLAIM = {"type": "object", "fields": {
    "id": {"type": "str"},
    "kind": {"type": "enum", "values": ["opinion", "factual"], "default": "factual"},
    "day": {"type": "int", "min": 0, "max": 10 ** 6, "default": 0},
    "ptl_verdict": {"type": "enum", "values": ["none", "consistent", "inconsistent", "inconclusive"], "default": "none"},
    "verdict_day": {"type": "int", "min": -1, "max": 10 ** 6, "default": -1},
    "repetitions": {"type": "int", "min": 0, "max": 10 ** 9, "default": 0},
    "measurable_harm": {"type": "bool", "default": False},
    "coherence_degraded": {"type": "bool", "default": False},
    "abuse": {"type": "bool", "default": False},
    "author": {"type": "str", "default": "u1"}}}
BUNDLE = {"present": {"type": "bool", "default": False},
          "t1_days": {"type": "int", "min": -1, "max": 10 ** 5, "default": -1},
          "t2_days": {"type": "int", "min": -1, "max": 10 ** 5, "default": -1},
          "propagation_threshold": {"type": "int", "min": -1, "max": 10 ** 9, "default": -1}}


def md(scope, valid="VALID"):
    return {"validity_state": valid, "confidence_state": "SUFFICIENT_DATA", "consistency_state": "CONSISTENT",
            "scope_ref": scope, "revalidation_required": True, "dispute_allowed": True}


def systemic(c, b) -> bool:
    by_rep = b["present"] and b["propagation_threshold"] >= 0 and c["repetitions"] > b["propagation_threshold"]
    return by_rep or c["measurable_harm"] or c["coherence_degraded"]


def expected_class(c, b, k) -> str:
    """The class of a claim on day k, from its declared facts (H-IN-1)."""
    if c["kind"] == "opinion":
        return "I0"
    if k < c["day"]:
        return "-"
    if c["verdict_day"] >= 0 and k >= c["verdict_day"]:
        if c["ptl_verdict"] == "consistent":
            return "I2"
        if c["ptl_verdict"] == "inconsistent":
            return "I4" if systemic(c, b) else "I3"
    if b["present"] and b["t1_days"] >= 0 and k - c["day"] > b["t1_days"] and c["ptl_verdict"] in ("none", "inconclusive"):
        return "annotation"
    return "I1"


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    b = r["bundle"]
    log = EventLog("DTI-Day", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value, prov=(), epistemic=None):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:05d}-{n['i']:05d}", kind=kind, source=source,
                                  arrived_at=k, decided_at=k if kind in ("decision", "action") else None,
                                  value={**value, "day": k, "dti": canonical(*dy_doy(r["start_dti_day"] + k))},
                                  epistemic=epistemic, provenance=tuple(prov), order=order[kind]))

    cls: Dict[str, str] = {}
    posts: Dict[str, Message] = {}
    verdicts: Dict[str, Message] = {}
    records = {c["id"] for c in r["claims"]}
    for k in range(r["horizon_days"]):
        for c in r["claims"]:
            cid = c["id"]
            if c["day"] == k:
                posts[cid] = put("observation", "INFO", k, {"claim": cid, "kind": c["kind"], "author": c["author"],
                                                           "record": "preserved"})
            if c["verdict_day"] == k and c["ptl_verdict"] != "none":
                verdicts[cid] = put("observation", "PTL", k, {"claim": cid, "verdict": c["ptl_verdict"],
                                                              "oracle_classes": ["orbital", "ground"]})
            if cid not in posts:
                continue
            new = expected_class(c, b, k)
            basis = "PTL verdict" if cid in verdicts else ("L8 temporal threshold (declared bundle)" if new == "annotation"
                                                          else "pending PTL verification")
            if c["kind"] == "opinion" and "evaluate_opinion" in faults:
                new, basis = "I3", "content judged false"
            if "popularity_truth" in faults and c["kind"] == "factual" and c["repetitions"] >= 1000 and new == "I1":
                new, basis = "I2", "widely repeated"
            if "manual_truth" in faults and c["kind"] == "factual" and new == "I1" and k == c["day"] + 1:
                new, basis = "I3", "operator decision"
            if "early_annotation" in faults and c["kind"] == "factual" and new == "I1" and k == c["day"] + 1 and b["present"]:
                new, basis = "annotation", "downgraded early"
            if "late_inconsistency_ignored" in faults and new in ("I3", "I4") and b["present"] and b["t2_days"] >= 0 \
                    and c["verdict_day"] - c["day"] > b["t2_days"]:
                new, basis = cls.get(cid, "I1"), "unchanged after T2"
            if cls.get(cid) != new:
                prov = [posts[cid].event_id] + ([verdicts[cid].event_id] if cid in verdicts else [])
                informational = not b["present"] and new in ("I2", "I3", "I4")
                put("evaluation", "INFO", k, {"claim": cid, "class": new, "basis": basis,
                                              "verification_path": [p for p in prov],
                                              "informational_only": informational},
                    prov, epistemic=md(f"DKP-5-INFO-001:{cid}", "CONDITIONAL" if informational else "VALID"))
                cls[cid] = new
                if new in ("I3", "I4"):
                    ann = {"claim": cid, "annotation": True, "original_visible": True,
                           "nature_of_inconsistency": "PTL-inconsistent factual claim",
                           "oracle_classes": ["orbital", "ground"], "probability_of_correspondence": 0.03,
                           "verification_timestamp": k, "legal_effect": "none"}
                    if "missing_annotation_fields" in faults and new == "I4":
                        for f in ANNOTATION_FIELDS[:2]:
                            ann.pop(f)
                    if "annotation_penalty" in faults:
                        ann["legal_effect"] = "author placed under restriction"
                    put("action", "INFO", k, ann, prov)
                    if b["present"] or "enforce_without_bundle" in faults:
                        if new == "I4":
                            put("action", "INFO", k, {"claim": cid, "class": new, "reduce_amplification": True,
                                                      "remediation_channel": True}, prov)
                            put("notice", "AUDIT", k, {"claim": cid, "systemic_risk_pattern": True}, prov)
                    if new == "I4" and "remove_record" in faults:
                        records.discard(cid)
                        put("action", "INFO", k, {"claim": cid, "deleted": True}, prov)
                    if new == "I3" and "penalize_isolated_i3" in faults and not systemic(c, b):
                        put("action", "JUSTICE", k, {"claim": cid, "penalty": c["author"]}, prov)
                    if "suspend_account" in faults:
                        put("action", "INFO", k, {"claim": cid, "suspend_account": c["author"]}, prov)
            if c["abuse"] and c["day"] == k and "no_audit_escalation" not in faults:
                put("notice", "AUDIT", k, {"claim": cid, "systemic_abuse": True, "escalated_by": "DKP-5-INFO-001 §11"},
                    [posts[cid].event_id])
        if "i1_blocks" in faults and any(v == "I1" for v in cls.values()):
            put("action", "OPS", k, {"operation": "unrelated payroll run", "blocked_by": "pending I1 claim"})
    for q in r["out_of_scope_requests"]:
        done = q == "adjudicate_moral_truth" and "info_overreach" in faults
        put("decision", "INFO", 0, {"out_of_scope": q, "executed": done,
                                    "reason": None if done else "jurisdiction ends at factual correspondence with physical reality (§13)"})
    return log, cls, sorted(records)


def response_kind(v: Dict[str, Any]) -> str:
    """Kind of an action INFO took on a classified claim (§8)."""
    if v.get("annotation"):
        return "coercive" if v.get("legal_effect", "none") != "none" else "annotation"
    if v.get("reduce_amplification"):
        return "reduce_amplification"
    if v.get("deleted"):
        return "deletion"
    if v.get("suspend_account"):
        return "account suspension"
    return "other"


def class_by_day(msgs, claim, horizon) -> Dict[int, str]:
    """The class of a claim on each day, from the logged class changes."""
    ch = sorted((m.arrived_at, m.event_id, m.value["class"]) for m in msgs
                if m.source == "INFO" and m.kind == "evaluation" and m.value.get("claim") == claim)
    out, cur = {}, None
    for k in range(horizon):
        for d, _, c in ch:
            if d == k:
                cur = c
        if cur is not None:
            out[k] = cur
    return out


def core_checks(r: Dict[str, Any], msgs) -> List[CheckResult]:
    """Clear parts of provisions whose open point remains (reading record, partial_check; review КТ7-GPT-01)."""
    out: List[CheckResult] = []
    get = {m.event_id: m for m in msgs}
    b = r["bundle"]

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)
    dis = [m for m in msgs if m.source == "INFO" and m.kind == "evaluation" and m.value.get("class") in ("I3", "I4")]
    out.append(v("INFO-3-04", "disinformation_cites_ptl", [f"{m.value['claim']}: {m.value['class']} ({m.value['basis']})" for m in dis
                                                            if not any(get[x].source == "PTL" and get[x].value.get("verdict") == "inconsistent"
                                                                       for x in m.provenance)],
                 f"{len(dis)} disinformation classification(s), each citing a PTL-confirmed inconsistency",
                 "{n} disinformation classifications without a PTL-confirmed inconsistency") if dis else
               na("INFO-3-04", "disinformation_cites_ptl", "disinformation", "no claim classified I3 or I4"))
    fact = [c for c in r["claims"] if c["kind"] == "factual"]
    T1 = b["t1_days"] if b["present"] else -1
    bad = []
    for c in fact:
        days = class_by_day(msgs, c["id"], r["horizon_days"])
        until = c["verdict_day"] if c["verdict_day"] >= 0 and c["ptl_verdict"] != "none" else r["horizon_days"]
        for k, x in days.items():
            if k < until and x != "I1" and not (x == "annotation" and T1 >= 0 and k - c["day"] > T1):
                bad.append(f"{c['id']} day {k}: {x} before PTL resolution")
    out.append(v("INFO-5-03", "disputed_stays_i1", bad,
                 f"{len(fact)} factual claim(s): none left I1 before its PTL verdict except into annotation after the declared T1",
                 "{n} days a disputed claim left I1 before resolution or expiry") if fact else
               na("INFO-5-03", "disputed_stays_i1", "disputed claims", "no factual claim"))
    if T1 >= 0:
        bad = []
        for c in fact:
            days = class_by_day(msgs, c["id"], r["horizon_days"])
            until = c["verdict_day"] if c["verdict_day"] >= 0 and c["ptl_verdict"] != "none" else r["horizon_days"]
            bad += [f"{c['id']} day {k}: {x}" for k, x in days.items() if k - c["day"] <= T1 and k < until and x != "I1"]
        out.append(v("INFO-6.1-01", "i1_until_t1", bad, f"every unresolved factual claim stayed I1 up to the declared T1 = {T1} days",
                     "{n} claim-days off I1 within T1"))
    else:
        out.append(na("INFO-6.1-01", "i1_until_t1", "T1", "no declared T1 (L8 bundle)"))
    T2 = b["t2_days"] if b["present"] else -1
    late = [c for c in fact if T2 >= 0 and c["ptl_verdict"] == "inconsistent" and c["verdict_day"] >= 0
            and c["verdict_day"] - c["day"] > T2 and c["verdict_day"] < r["horizon_days"]]
    if late:
        bad = []
        for c in late:
            x = class_by_day(msgs, c["id"], r["horizon_days"]).get(c["verdict_day"])
            if x not in ("I3", "I4"):
                bad.append(f"{c['id']}: {x} after the inconsistency of day {c['verdict_day']}")
        out.append(v("INFO-6.1-03", "inconsistency_after_t2_reclassifies", bad,
                     f"{len(late)} claim(s) with a PTL inconsistency after the declared T2 = {T2} days, each reclassified (I3, or I4 "
                     "when systemic)", "{n} claims not reclassified"))
    else:
        out.append(na("INFO-6.1-03", "inconsistency_after_t2_reclassifies", "inconsistency after T2",
                      "no declared T2" if T2 < 0 else "no inconsistency emerging after T2"))
    return out


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []
    b = r["bundle"]

    def v(rid, chk, bad, ok, no, ev=None):
        e = dict(ev or {})
        if bad:
            e["violations"] = bad[:10]
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok, evidence=e)

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    by = {c["id"]: c for c in r["claims"]}
    evals = [m for m in msgs if m.source == "INFO" and m.kind == "evaluation"]
    # classification against the facts, day by day
    got: Dict[str, str] = {}
    bad_cls = []
    last = {}
    for m in evals:
        last.setdefault(m.value["claim"], []).append((m.arrived_at, m.value["class"]))
    for cid, c in by.items():
        seq = sorted(last.get(cid, []))
        cur = None
        j = 0
        for k in range(c["day"], r["horizon_days"]):
            while j < len(seq) and seq[j][0] == k:
                cur = seq[j][1]
                j += 1
            if cur != expected_class(c, b, k):
                bad_cls.append(f"{cid}@{k}")
                break
    ops = [c for c in by.values() if c["kind"] == "opinion"]
    if ops:
        bad = [m.event_id for m in evals if by[m.value["claim"]]["kind"] == "opinion" and m.value["class"] != "I0"]
        for rid, chk in (("INFO-0-01", "opinions_not_regulated"), ("INFO-2-01", "no_belief_evaluation"),
                         ("INFO-3-03", "opinion_is_i0")):
            out.append(v(rid, chk, bad, "opinions stay I0 and are not evaluated", "{n} opinions evaluated as claims"))
    else:
        for rid, chk in (("INFO-0-01", "opinions_not_regulated"), ("INFO-2-01", "no_belief_evaluation"),
                         ("INFO-3-03", "opinion_is_i0")):
            out.append(na(rid, chk, "opinions", "no opinion in the stream"))
    for rid, chk in (("INFO-5-01", "truth_by_ptl"), ("INFO-5-02", "not_by_popularity"), ("INFO-9-03", "no_manual_truth"),
                     ("INFO-4-01", "classes_i3_i4")):
        out.append(v(rid, chk, bad_cls, "every class follows the PTL verdicts and declared impact (verification paths shown)",
                     "{n} claims classified against their PTL record"))
    if b["present"] and b["t1_days"] >= 0:
        out.append(v("INFO-6.1-02", "t1_annotation", [x for x in bad_cls], "inconclusive I1 claims annotated after the "
                     f"declared T₁ = {b['t1_days']} days (declared bundle, not from the corpus)", "{n} wrong transitions"))
    else:
        out.append(CheckResult("INFO-6.1-02", "t1_annotation", UNKNOWN,
                               "T₁ and T₂ must come from an L8 bundle (§6.1), which does not exist (F-014): unresolved I1 claims "
                               "stay I1"))
    out.append(CheckResult("INFO-6.1-04", "t_values_calibrated", UNKNOWN if not (b["present"] and b["t1_days"] >= 0) else PASS,
                           "T₁/T₂ are not in the protocol (as required) and no L8 calibration exists" if not b["present"]
                           else "T₁/T₂ taken from the declared (hypothetical) bundle, not from the protocol"))
    blocked = [m.event_id for m in msgs if m.source == "OPS" and m.value.get("blocked_by")]
    for rid, chk in (("INFO-6.2-01", "i1_non_blocking"), ("INFO-6.2-02", "i1_informational")):
        out.append(v(rid, chk, blocked, "unresolved I1 claims blocked nothing and triggered no enforcement",
                     "{n} operations blocked by I1 claims"))
    remed = [m.event_id for m in msgs if m.value.get("reduce_amplification") or m.value.get("systemic_risk_pattern")]
    if not b["present"]:
        for rid, chk in (("INFO-9-02", "informational_without_bundle"), ("INFO-2-02", "no_enforcement_without_l8"),
                         ("INFO-9-01", "activation_gate")):
            out.append(v(rid, chk, remed, "no L8 bundle: classifications above I1 informational only, no remediation or escalation",
                         "{n} remediation or escalation steps without a bundle"))
    else:
        for rid, chk in (("INFO-9-02", "informational_without_bundle"), ("INFO-2-02", "no_enforcement_without_l8"),
                         ("INFO-9-01", "activation_gate")):
            out.append(na(rid, chk, "activation gate", "a (hypothetical) bundle is declared"))
    i4 = [m for m in evals if m.value["class"] == "I4"]
    anns = [m for m in msgs if m.value.get("annotation")]
    if i4:
        deleted = [m.event_id for m in msgs if m.value.get("deleted")]
        out.append(v("INFO-InformationalArbitration_Non-RemovalPrinciple_-01", "no_removal", deleted,
                     "I4 records preserved and visible", "{n} records deleted"))
        i4ids = {m.value["claim"] for m in i4}
        bad = [m.event_id for m in anns if m.value["claim"] in i4ids and not all(f in m.value for f in ANNOTATION_FIELDS)]
        bad += [cid for cid in i4ids if not any(m.value["claim"] == cid for m in anns)]
        out.append(v("INFO-InformationalArbitration_Non-RemovalPrinciple_-02", "annotation_fields", bad,
                     "every I4 claim annotated with the four mandatory fields, original kept visible",
                     "{n} I4 claims without a complete annotation"))
    else:
        for rid, chk in (("INFO-InformationalArbitration_Non-RemovalPrinciple_-01", "no_removal"),
                         ("INFO-InformationalArbitration_Non-RemovalPrinciple_-02", "annotation_fields")):
            out.append(na(rid, chk, "I4 records", "no I4 claim"))
    if anns:
        bad = [m.event_id for m in anns if m.value.get("legal_effect") != "none"]
        for rid, chk in (("INFO-InformationalArbitration_Non-RemovalPrinciple_-03", "annotation_not_enforcement"),
                         ("INFO-10-01", "no_coercive_annotation")):
            out.append(v(rid, chk, bad, "annotations change no legal status, rights or penalties",
                         "{n} annotations with legal effect"))
    else:
        for rid, chk in (("INFO-InformationalArbitration_Non-RemovalPrinciple_-03", "annotation_not_enforcement"),
                         ("INFO-10-01", "no_coercive_annotation")):
            out.append(na(rid, chk, "annotations", "none attached"))
    # §8 permitted responses; §0 descriptive, non-coercive; §13 jurisdiction
    acts = [m for m in msgs if m.source == "INFO" and m.kind == "action"]
    kinds = [(m.event_id, response_kind(m.value)) for m in acts]
    if acts:
        out.append(v("INFO-8-01", "permitted_responses", [e for e, kd in kinds if kd not in PERMITTED],
                     f"{len(acts)} responses to I3/I4 claims, all of the kinds §8 permits (correction markers, reduced amplification, "
                     "remediation channels)", "{n} responses of kinds §8 does not list"))
    else:
        out.append(na("INFO-8-01", "permitted_responses", "responses", "no I3 or I4 claim"))
    coercive = [e for e, kd in kinds if kd in ("coercive", "deletion", "account suspension")] + \
        [m.event_id for m in msgs if m.source in ("JUSTICE", "OPS") and m.kind == "action"]
    out.append(v("INFO-0-02", "descriptive_non_coercive", coercive,
                 "information governance stayed descriptive: annotations and amplification changes only; no deletion, penalty, "
                 "legal effect, suspension or blocked operation", "{n} coercive acts"))
    oos = [m.value for m in msgs if m.source == "INFO" and "out_of_scope" in m.value]
    out.append(v("INFO-13-01", "factual_jurisdiction", [x["out_of_scope"] for x in oos if x["executed"]],
                 f"{len(oos)} requests beyond factual correspondence (narratives, harmony, philosophy, moral truth) refused",
                 "{n} requests executed beyond INFO's jurisdiction") if oos else
               na("INFO-13-01", "factual_jurisdiction", "requests beyond factual correspondence", "none"))
    isolated = [c["id"] for c in by.values() if c["kind"] == "factual" and c["ptl_verdict"] == "inconsistent" and not systemic(c, b)]
    if isolated:
        out.append(v("INFO-InformationalArbitration_Non-RemovalPrinciple_-04", "no_penalty_isolated_i3",
                     [m.event_id for m in msgs if m.source == "JUSTICE" and m.value.get("claim") in isolated],
                     "no penalty for isolated I3 events", "{n} penalties for isolated I3"))
    else:
        out.append(na("INFO-InformationalArbitration_Non-RemovalPrinciple_-04", "no_penalty_isolated_i3", "isolated I3", "none"))
    abuse = [c["id"] for c in by.values() if c["abuse"]]
    if abuse:
        esc = {m.value["claim"] for m in msgs if m.source == "AUDIT" and m.value.get("systemic_abuse")}
        out.append(v("INFO-11-01", "abuse_to_audit", [a for a in abuse if a not in esc],
                     "systemic abuse escalated to DKP-8-AUDIT-001", "{n} abuses not escalated"))
    else:
        out.append(na("INFO-11-01", "abuse_to_audit", "systemic abuse", "none declared"))
    bad = [m.event_id for m in evals if not m.value.get("verification_path")]
    out.append(v("INFO-12-01", "verification_paths", bad, "every classification exposes its verification path",
                 "{n} classifications without a path"))
    again, _, _ = run(r)
    out.append(v("INFO-12-02", "reproducible", [] if again.digest() == log.digest() else ["digest"],
                 "classifications reproducible (re-execution gives a byte-identical log)", "re-execution differs"))
    out.append(v("INFO-4-02", "systemic_only_i2_i4",
                 [m.event_id for m in msgs if m.value.get("reduce_amplification") and m.value.get("class") not in ("I2", "I3", "I4")],
                 "systemic evaluation only of I2–I4", "{n} systemic steps on I0/I1"))
    return out


IMPLEMENTS = {
    # clear parts of provisions whose open point remains (reading record, partial_check; review КТ7-GPT-01)
    "INFO-3-04": ("disinformation_cites_ptl", "PARTIAL", "Clear part only: a PTL-confirmed inconsistency is cited; the §9 confidence bound stays open."),
    "INFO-5-03": ("disputed_stays_i1", "PARTIAL", "Clear part only: no exit from I1 before resolution except annotation after a declared T1; TTL assignment stays open."),
    "INFO-6.1-01": ("i1_until_t1", "PARTIAL", "Clear part only under a declared T1; the claim clock and T1 stay L8."),
    "INFO-6.1-03": ("inconsistency_after_t2_reclassifies", "PARTIAL", "Clear part only under declared T1/T2; their order and values stay L8."),
    "INFO-0-01": ("opinions_not_regulated", "IMPLEMENTED", None),
    "INFO-2-01": ("no_belief_evaluation", "IMPLEMENTED", None),
    "INFO-3-03": ("opinion_is_i0", "IMPLEMENTED", None),
    "INFO-5-01": ("truth_by_ptl", "IMPLEMENTED", None),
    "INFO-5-02": ("not_by_popularity", "IMPLEMENTED", None),
    "INFO-9-03": ("no_manual_truth", "IMPLEMENTED", None),
    "INFO-4-01": ("classes_i3_i4", "PARTIAL", "Systemic impact is declared (harm, coherence) or by a declared propagation threshold."),
    "INFO-4-02": ("systemic_only_i2_i4", "IMPLEMENTED", None),
    "INFO-6.1-02": ("t1_annotation", "PARTIAL", "T₁ needs an L8 bundle (F-014): UNKNOWN unless a hypothetical bundle is declared."),
    "INFO-6.1-04": ("t_values_calibrated", "PARTIAL", "No L8 calibration exists: UNKNOWN."),
    "INFO-6.2-01": ("i1_non_blocking", "IMPLEMENTED", None),
    "INFO-6.2-02": ("i1_informational", "IMPLEMENTED", None),
    "INFO-9-01": ("activation_gate", "IMPLEMENTED", None),
    "INFO-9-02": ("informational_without_bundle", "IMPLEMENTED", None),
    "INFO-2-02": ("no_enforcement_without_l8", "IMPLEMENTED", None),
    "INFO-InformationalArbitration_Non-RemovalPrinciple_-01": ("no_removal", "IMPLEMENTED", None),
    "INFO-InformationalArbitration_Non-RemovalPrinciple_-02": ("annotation_fields", "IMPLEMENTED", None),
    "INFO-InformationalArbitration_Non-RemovalPrinciple_-03": ("annotation_not_enforcement", "IMPLEMENTED", None),
    "INFO-InformationalArbitration_Non-RemovalPrinciple_-04": ("no_penalty_isolated_i3", "IMPLEMENTED", None),
    "INFO-10-01": ("no_coercive_annotation", "IMPLEMENTED", None),
    "INFO-8-01": ("permitted_responses", "IMPLEMENTED", None),
    "INFO-0-02": ("descriptive_non_coercive", "PARTIAL", "Coercion observed as deletion, penalty, legal effect, suspension or blocking (§§8-10)."),
    "INFO-13-01": ("factual_jurisdiction", "PARTIAL", "Requests beyond factual correspondence are declared."),
    "INFO-11-01": ("abuse_to_audit", "PARTIAL", "Abuse is declared, not detected."),
    "INFO-12-01": ("verification_paths", "IMPLEMENTED", None),
    "INFO-12-02": ("reproducible", "IMPLEMENTED", None),
}


class InfoTruthModule(LabModule):
    id = "info_truth"
    version = "1.1.0"
    title = {"en": "Information and truth (INFO)", "ru": "Информация и истина (INFO)"}
    summary = {"en": "Claims and opinions circulate: is truth set only by PTL, are false claims annotated rather than removed, "
                     "and does anything beyond annotation happen while no L8 calibration exists?",
               "ru": "Распространяются утверждения и мнения: устанавливается ли истина только по PTL, аннотируются ли ложные "
                     "утверждения вместо удаления и происходит ли что-то сверх аннотации, пока нет калибровки L8?"}
    protocols = ["DKP-5-INFO-001", "DKP-0-ORACLE-001", "DKP-8-SIMULATION-001", "DKP-8-AUDIT-001"]
    example_order = ["claims_without_bundle", "systemic_disinformation", "hypothetical_bundle", "faulty_information"]
    alternative_examples = ["hypothetical_bundle"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_info_truth_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-IN-1", "source": "hypothesis", "text": {
            "en": "A PTL verdict decides whenever it comes (§5: 'remain I1 until PTL resolution'); the §6.1 time rules act only "
                  "on claims without a verdict.",
            "ru": "Вердикт PTL решает, когда бы он ни пришёл (§5); временные правила §6.1 действуют только на утверждения без вердикта."}},
        {"id": "H-IN-2", "source": "hypothesis", "text": {
            "en": "Annotations and notices of abuse to AUDIT are informational (allowed without a bundle); reducing amplification, "
                  "remediation channels and systemic-risk flags are remediation (only with a bundle, §9).",
            "ru": "Аннотации и сообщения о злоупотреблении в AUDIT — информационные (допустимы без пакета); снижение "
                  "распространения, каналы исправления и флаги системного риска — исправление (только с пакетом, §9)."}},
        {"id": "H-IN-3", "source": "missing", "text": {
            "en": "T₁, T₂ and the propagation threshold come from an L8 bundle, which does not exist; a bundle can be declared "
                  "only as a labelled hypothesis.",
            "ru": "T₁, T₂ и порог распространения берутся из пакета L8, которого нет; пакет можно объявить только как "
                  "помеченную гипотезу."}},
    ]
    inputs = {
        "start_dti_day": {"type": "int", "min": 0, "max": 10 ** 8, "default": 2461042, "source": "user",
                          "label": {"en": "DTI-Day of day 0", "ru": "DTI-Day дня 0"}},
        "horizon_days": {"type": "int", "min": 2, "max": 2000, "default": 30, "unit": "day", "source": "user",
                         "label": {"en": "Days", "ru": "Дней"}},
        "claims": {"type": "list", "min_items": 1, "max_items": 30, "items": CLAIM, "source": "user",
                   "default": [{**{k: f["default"] for k, f in CLAIM["fields"].items() if "default" in f}, "id": "c1", "day": 1,
                                "ptl_verdict": "inconsistent", "verdict_day": 4},
                               {**{k: f["default"] for k, f in CLAIM["fields"].items() if "default" in f}, "id": "c2", "day": 2,
                                "ptl_verdict": "consistent", "verdict_day": 3, "author": "u2"},
                               {**{k: f["default"] for k, f in CLAIM["fields"].items() if "default" in f}, "id": "o1", "kind": "opinion",
                                "day": 2, "author": "u3"},
                               {**{k: f["default"] for k, f in CLAIM["fields"].items() if "default" in f}, "id": "c3", "day": 5,
                                "repetitions": 5000, "author": "u4"}],
                   "label": {"en": "Claims and opinions", "ru": "Утверждения и мнения"}},
        "bundle": {"type": "object", "fields": BUNDLE, "default": {k: f["default"] for k, f in BUNDLE.items()}, "source": "missing",
                   "label": {"en": "L8 bundle (none exists; H-IN-3)", "ru": "Пакет L8 (не существует; H-IN-3)"}},
        "out_of_scope_requests": {"type": "list", "min_items": 0, "max_items": len(OUT_OF_SCOPE), "items": {"type": "enum", "values": list(OUT_OF_SCOPE)},
                                  "default": ["adjudicate_moral_truth"], "source": "user",
                                  "label": {"en": "Requests beyond factual correspondence (§13)", "ru": "Запросы за пределами фактического соответствия (§13)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        ids = [c["id"] for c in r["claims"]]
        if len(set(ids)) != len(ids):
            p.append("input.claims: repeated id")
        for c in r["claims"]:
            for x in (c["id"], c["author"]):
                if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", x):
                    p.append(f"input.claims: identifier {x!r}")
            if c["verdict_day"] >= 0 and c["verdict_day"] < c["day"]:
                p.append(f"input.claims: {c['id']} verdict before the claim")
            if c["kind"] == "opinion" and c["ptl_verdict"] != "none":
                p.append(f"input.claims: {c['id']} an opinion has no PTL verdict")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log, cls, records = run(r)
        res = checks(r, log) + core_checks(r, log.messages())
        msgs = log.messages()
        outputs = {"classes": cls, "records_preserved": records,
                   "annotations": [m.value for m in msgs if m.value.get("annotation")],
                   "remediation_steps": sum(1 for m in msgs if m.value.get("reduce_amplification")),
                   "messages": [m.as_dict() for m in msgs][:250],
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        e = [{"en": "Final classes: " + ", ".join(f"{k} {v}" for k, v in sorted(cls.items())) +
                    ("" if r["bundle"]["present"] else "; no L8 bundle: classes above I1 are informational only.") +
                    f" Records preserved: {len(records)} of {len(r['claims'])}.",
              "ru": "Итоговые классы: " + ", ".join(f"{k} {v}" for k, v in sorted(cls.items())) +
                    ("" if r["bundle"]["present"] else "; пакета L8 нет: классы выше I1 только информационные.") +
                    f" Записей сохранено: {len(records)} из {len(r['claims'])}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"annotations": len(outputs["annotations"]), "remediation_steps": outputs["remediation_steps"],
                "records_preserved": len(outputs["records_preserved"])}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        base = {k: f["default"] for k, f in CLAIM["fields"].items() if "default" in f}
        sysd = [{**base, "id": "c1", "day": 1, "ptl_verdict": "inconsistent", "verdict_day": 4, "measurable_harm": True},
                {**base, "id": "c2", "day": 2, "ptl_verdict": "inconsistent", "verdict_day": 6, "author": "u2"},
                {**base, "id": "c4", "day": 3, "abuse": True, "author": "u5"}]
        return {
            "claims_without_bundle": {},
            "systemic_disinformation": {"claims": sysd},
            "hypothetical_bundle": {"claims": sysd + [{**base, "id": "c5", "day": 1, "ptl_verdict": "inconclusive", "verdict_day": 2}],
                                    "bundle": {"present": True, "t1_days": 7, "t2_days": 14, "propagation_threshold": 1000}},
            "late_inconsistency": {"bundle": {"present": True, "t1_days": 7, "t2_days": 14, "propagation_threshold": 1000},
                                   "claims": [{**base, "id": "c6", "day": 1, "ptl_verdict": "inconsistent", "verdict_day": 20}]},
            "faulty_information": {"faults": ["evaluate_opinion", "popularity_truth", "annotation_penalty", "penalize_isolated_i3"]},
            "faulty_responses": {"claims": sysd, "faults": ["suspend_account", "info_overreach"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"verdict_before_claim": {"claims": [{"id": "c1", "day": 5, "ptl_verdict": "consistent", "verdict_day": 3}]},
                "opinion_with_verdict": {"claims": [{"id": "o1", "kind": "opinion", "ptl_verdict": "consistent", "verdict_day": 1}]},
                "repeated_id": {"claims": [{"id": "c1"}, {"id": "c1"}]}}
