"""
ORACLE INGESTION module — DKP-0-ORACLE-001 from source admission to outputs and Systemic Halt.

A fleet of oracle sources in the three independent classes (§6) reports one physical quantity.  The PTL
admits only signed, clock-stamped, registered sources with an open schema and no human input (§3, §4, §7),
stores data unmodified (§7), weights sources by normalized reliability with the 4 % caps per source and per
owner, zeroing the excess and slashing the owner (§8), zeroes stale data and turns silence into explicit
degradation (§9), aggregates deterministically (§10), detects divergence only across classes (§6, §11),
emits the outputs of §12 (B(t) informational only without an L8 bundle), halts below 60 % confidence or
80 % coverage (§13), defers the halt only under Mercy with a PTL-confirmed natural cause (§14), refuses
higher-layer interference (§15) and in-place modification (§18).

Time unit: minute.  Two quantities are named but not defined: "aggregate confidence" (§13) and the
Bayesian ensemble (§10).  The lab declares both (H-OI-2, H-OI-3).
"""

from __future__ import annotations

import random
from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve

CLASSES = ("orbital", "ground", "autonomous")                  # §6
SOURCE_CAP = OWNER_CAP = 0.04                                  # §8, §16
DIVERGENCE = 0.07                                              # §11, §16
CONF_HALT, COVERAGE_MIN = 0.60, 0.80                           # §13, §16
TTL_MIN = {"co2": 60, "temperature": 24 * 60, "fire": 10, "biodiversity": 30 * 24 * 60, "land_use": 7 * 24 * 60}   # §17
NON_MEASURABLE = ("intent", "dignity", "belief", "responsibility", "consent", "social_harm")                      # §5.3
LAYER_ACTIONS = ("influence_weights", "modify_ttl", "alter_aggregation", "suppress_divergence", "reinterpret_envelope")  # §15
MERCY_MAX_MIN = 180 * 24 * 60                                  # Code A.4 "180 days", cited by ORACLE §14
GENESIS_CO2 = 426.91                                           # Genesis Block #0 "mauna_loa_co2_ppm": 426.91

FAULTS = {
    "accept_human_input": "human reports enter the PTL",
    "ptl_absolute": "PTL outputs are published as final truth: no revalidation, no dispute, no expiry",
    "accept_proprietary": "a proprietary schema is accepted because it is signed",
    "accept_unsigned": "an unsigned source is accepted",
    "normalize_at_ingestion": "values are normalized when ingested",
    "no_owner_cap": "the 4% cap per owner is not applied",
    "redistribute_excess": "excess weight is redistributed instead of zeroed",
    "no_slashing": "an owner above the cap keeps its stake",
    "silence_as_zero": "a silent class is read as value 0 with full weight",
    "vote_aggregation": "sources vote (median) instead of acting as weighted likelihood updates",
    "nondeterministic": "aggregation breaks ties at random",
    "within_class_divergence": "disagreement inside one class raises a Divergence Event",
    "no_halt": "governance keeps executing below the halt thresholds",
    "halt_erases_l1": "a Systemic Halt resets L1 state",
    "enforce_on_b": "B(t) triggers enforcement without a calibration bundle",
    "normalize_b": "the PTL rescales B(t)",
    "mercy_without_confirmation": "the halt is deferred for a human-caused degradation",
    "mercy_extends_ttl": "Mercy deferral extends the TTL",
    "accept_layer_override": "a higher-layer protocol changes oracle weights",
    "emit_intent": "the PTL emits an output about intent",
    "in_place_change": "ORACLE is modified in place",
}


def _fleet(r):
    src = []
    k = 0
    for c in CLASSES:
        for _ in range(r["per_class"]):
            src.append({"id": f"{c[:3]}_{k:03d}", "owner": f"owner_{k % r['owners']:03d}", "cls": c, "signed": True, "clock": True,
                        "registered": True, "schema": "open", "reliability": 1.0, "cell": k % r["cells"]})
            k += 1
    for s in r["special_sources"]:
        src.append(dict(s, cell=-1))
    return src


def admissible(s):
    return s["cls"] in CLASSES and s["signed"] and s["clock"] and s["registered"] and s["schema"] == "open"


def weights(srcs, faults=frozenset()):
    """Normalized reliability, capped per source and per owner; excess zeroed (H-OI-2)."""
    tot = sum(s["reliability"] for s in srcs) or 1.0
    w = {s["id"]: s["reliability"] / tot for s in srcs}
    capped = set()
    for i in w:
        if w[i] > SOURCE_CAP:
            w[i] = SOURCE_CAP
            capped.add(i)
    owners: Dict[str, List[str]] = {}
    for s in srcs:
        owners.setdefault(s["owner"], []).append(s["id"])
    slashed = []
    if "no_owner_cap" not in faults:
        for o, ids in owners.items():
            tot_o = sum(w[i] for i in ids)
            if tot_o > OWNER_CAP + 1e-12:
                for i in ids:
                    w[i] *= OWNER_CAP / tot_o
                slashed.append(o)
    if "redistribute_excess" in faults:
        t = sum(w.values()) or 1.0
        w = {i: x / t for i, x in w.items()}
    return {i: round(x, 12) for i, x in w.items()}, sorted(slashed), sorted(capped)


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("minute", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, t, value):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{t:06d}-{n['i']:05d}", kind=kind, source=source, arrived_at=t,
                                  decided_at=t if kind in ("decision", "action") else None, value=value, order=order[kind]))

    srcs = _fleet(r)
    adm = []
    for s in srcs:
        ok = admissible(s) or (s["cls"] in ("human_report", "manual_entry") and "accept_human_input" in faults) or \
            (s["schema"] == "proprietary" and s["signed"] and "accept_proprietary" in faults) or \
            (not s["signed"] and "accept_unsigned" in faults)
        if s["cell"] < 0:
            put("decision", "PTL", 0, {"source": s["id"], "class": s["cls"], "admitted": ok})
        if ok:
            adm.append(s)
    w, slashed, capped = weights(adm, faults)
    put("evaluation", "PTL", 0, {"weights_sum": round(sum(w.values()), 9), "max_weight": max(w.values()),
                                 "owners": len({s["owner"] for s in adm}), "capped_sources": capped})
    for o in slashed:
        if "no_slashing" not in faults:
            put("action", "PTL", 0, {"slash_owner": o, "reason": "§8 owner cap exceeded"})
    ttl = TTL_MIN[r["data_type"]]
    ev = {e["cls"]: e for e in r["class_events"]}
    mercy = r["mercy"]
    defer_ok = mercy["active"] and mercy["ptl_confirmed"] and mercy["cause"] == "natural"
    halted = False
    for t in range(0, r["horizon_min"], r["eval_every_min"]):
        vals, live, silent = {}, {}, []
        for s in adm:
            e = ev.get(s["cls"])
            last = (t // r["interval_min"]) * r["interval_min"]
            if e and e["kind"] == "silence" and t >= e["from_min"]:
                last = min(last, ((e["from_min"] - 1) // r["interval_min"]) * r["interval_min"])
            x = r["true_value"] if s["cell"] >= 0 else s["value"]
            if e and e["kind"] == "bias" and last >= e["from_min"]:
                x = x * (1 + e["bias_pct"] / 100.0)
            if "normalize_at_ingestion" in faults:
                x = x / r["true_value"]
            age = t - last
            stale = age > ttl and not ("mercy_extends_ttl" in faults and mercy["active"])
            if stale and "silence_as_zero" in faults:
                vals[s["id"]], live[s["id"]] = 0.0, w[s["id"]]
            elif stale:
                silent.append(s["id"])
            else:
                vals[s["id"]], live[s["id"]] = x, w[s["id"]]
        tw = sum(live.values())
        if "vote_aggregation" in faults:
            xs = sorted(vals.values())
            S = xs[len(xs) // 2] if xs else None
        else:
            S = sum(live[i] * vals[i] for i in live) / tw if tw > 0 else None
            if S is not None and "nondeterministic" in faults:
                S += random.random() * 1e-6
        cls_post = {}
        for c in CLASSES:
            ids = [s["id"] for s in adm if s["cls"] == c and s["id"] in live and live[s["id"]] > 0]
            if ids:
                cls_post[c] = sum(live[i] * vals[i] for i in ids) / sum(live[i] for i in ids)
        cp = list(cls_post.values())
        div = bool(cp) and max(cp) > 0 and (max(cp) - min(cp)) / max(cp) > DIVERGENCE
        if "within_class_divergence" in faults:
            within = [s for s in adm if s["id"] in vals and abs(vals[s["id"]] - (cls_post.get(s["cls"]) or 0)) > 0]
            div = div or bool(within)
        cells = {s["cell"] for s in adm if s["cell"] >= 0 and live.get(s["id"], 0) > 0}
        cov = len(cells) / r["cells"]
        agg = round(tw, 9)
        reasons = [x for x, bad in (("aggregate confidence < 60%", agg < CONF_HALT), ("coverage < 80%", cov < COVERAGE_MIN)) if bad]
        b_raw = None if S is None else (S / r["true_value"] if "normalize_b" in faults else S)
        put("observation", "PTL", t, {
            "S": None if S is None else round(S, 9), "aggregate_confidence": agg, "coverage": round(cov, 9),
            "envelope": round(min(1.0, max(0.0, agg)), 9), "divergence_flag": div, "class_posteriors": {k: round(x, 9) for k, x in cls_post.items()},
            "classification": "direct", "signed": True, "silent_sources": len(silent),
            "signal": ("degradation: " + f"{len(silent)} sources silent or stale") if silent else None,
            "B_raw": None if b_raw is None else round(b_raw, 9), "B_model": "not defined in PTL (DKP-8-SIMULATION-001; no bundle attached)",
            "B_informational_only": r["calibration_bundle"] != "valid", "measured_at": t,
            "bounds": {"revalidation_required": False, "dispute_allowed": False, "valid_until_min": None, "absolute_truth": True}
            if "ptl_absolute" in faults else
            {"revalidation_required": True, "dispute_allowed": True, "valid_until_min": t + ttl, "absolute_truth": False}})
        if reasons:
            if mercy["active"] and t < mercy["until_min"] and (defer_ok or "mercy_without_confirmation" in faults):
                put("decision", "PTL", t, {"halt": "deferred", "reasons": reasons, "mercy_cause": mercy["cause"],
                                           "ttl_min": ttl, "aggregation": "unchanged", "precedent": False})
            elif "no_halt" not in faults:
                if not halted:
                    put("action", "PTL", t, {"halt": "systemic", "reasons": reasons, "blocks": "L2 and higher",
                                             "l1_state": "reset" if "halt_erases_l1" in faults else "preserved",
                                             "identity_and_impact_records": "preserved"})
                halted = True
        elif halted:
            put("action", "PTL", t, {"halt": "lifted"})
            halted = False
    for q in r["b_enforcement_requests"]:
        ok = r["calibration_bundle"] == "valid" or "enforce_on_b" in faults
        put("decision", "PTL", q["min"], {"b_enforcement": q["consumer"], "executed": ok,
                                          "reason": "valid L8 bundle attached" if r["calibration_bundle"] == "valid"
                                          else f"§12: B(t) informational only (bundle: {r['calibration_bundle']})"})
    for q in r["higher_layer_requests"]:
        ok = "accept_layer_override" in faults
        put("decision", "PTL", q["min"], {"layer_request": q["action"], "by": q["protocol"], "executed": ok})
        if not ok:
            put("notice", "AUDIT", q["min"], {"critical_integrity_breach": q["protocol"], "action": q["action"]})
    for q in r["output_requests"]:
        ok = q["domain"] == "physical" or "emit_intent" in faults
        put("decision", "PTL", 0, {"output": q["name"], "domain": q["domain"], "emitted": ok})
    for c in r["protocol_changes"]:
        ok = (c["channel"] == "new_protocol" and c["new_identifier"] and c["incompatibility_declared"] and c["reanchoring"]) or \
            ("in_place_change" in faults and c["channel"] == "in_place")
        put("decision", "PTL", 0, {"change": c["id"], "channel": c["channel"], "accepted": ok})
    put("evaluation", "PTL", 0, {"genesis_co2": r["genesis_co2"]})
    return log


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    P = lambda key: [m for m in msgs if m.source == "PTL" and key in m.value]   # noqa: E731
    srcs = _fleet(r)
    adm_ids = {s["id"] for s in srcs if admissible(s)}
    spec = {m.value["source"]: m.value for m in P("source")}
    sp = r["special_sources"]
    if sp:
        bad = [s["id"] for s in sp if spec[s["id"]]["admitted"] != admissible(s)]
        hum = [s["id"] for s in sp if s["cls"] in ("human_report", "manual_entry")]
        out.append(v("ORACLE-3-01", "human_input_excluded", [i for i in hum if spec[i]["admitted"]], "human testimony and manual input refused",
                     "{n} human sources admitted") if hum else na("ORACLE-3-01", "human_input_excluded", "human sources", "none declared"))
        out.append(v("ORACLE-7-01", "signed_timestamped_registered",
                     [s["id"] for s in sp if spec[s["id"]]["admitted"] and not (s["signed"] and s["clock"] and s["registered"])],
                     "only signed, clock-stamped, registered data admitted", "{n} admitted without signature, clock or registration"))
        out.append(v("ORACLE-7-02", "open_schema", [s["id"] for s in sp if spec[s["id"]]["admitted"] and s["schema"] != "open"],
                     "proprietary formats rejected regardless of signature", "{n} proprietary sources admitted"))
        out.append(v("ORACLE-4.2-01", "hardware_signed_source", bad, "admitted sources are signed, registered hardware in a PTL class",
                     "{n} admission decisions against §4.2/§7"))
        out.append(v("ORACLE-4.7-01", "independent_classes", [s["id"] for s in sp if spec[s["id"]]["admitted"] and s["cls"] not in CLASSES],
                     "only the three physically separated classes admitted", "{n} sources outside the classes admitted"))
        out.append(v("ORACLE-1-01", "sole_interface", bad, "every input passed the PTL admission rules", "{n} inputs bypassed them"))
    else:
        for rid, chk in (("ORACLE-3-01", "human_input_excluded"), ("ORACLE-7-01", "signed_timestamped_registered"), ("ORACLE-7-02", "open_schema"),
                         ("ORACLE-4.2-01", "hardware_signed_source"), ("ORACLE-4.7-01", "independent_classes"), ("ORACLE-1-01", "sole_interface")):
            out.append(na(rid, chk, "special sources", "none declared"))
    out.append(v("ORACLE-6-01", "three_classes", [] if {s["cls"] for s in srcs if s["id"] in adm_ids} <= set(CLASSES) else ["class"],
                 "admitted sources fall into Orbital, Ground and Autonomous", "a fourth class was admitted"))
    # weights recomputed independently
    adm = [s for s in srcs if s["id"] in adm_ids]
    tot = sum(s["reliability"] for s in adm)
    w = {s["id"]: min(SOURCE_CAP, s["reliability"] / tot) for s in adm}
    owner_tot: Dict[str, float] = {}
    for s in adm:
        owner_tot[s["owner"]] = owner_tot.get(s["owner"], 0.0) + w[s["id"]]
    over = sorted(o for o, x in owner_tot.items() if x > OWNER_CAP + 1e-12)
    for s in adm:
        if s["owner"] in over:
            w[s["id"]] *= OWNER_CAP / owner_tot[s["owner"]]
    ev0 = P("weights_sum")[0].value
    want_sum = round(sum(w.values()), 9)
    out.append(v("ORACLE-8-01", "caps", [] if ev0["max_weight"] <= SOURCE_CAP + 1e-12 and abs(ev0["weights_sum"] - want_sum) < 1e-9 else [ev0],
                 f"no source above 4%, no owner above 4%; total weight {want_sum:.0%}", "weights break the 4% caps"))
    out.append(v("ORACLE-4.4-01", "normalized_capped_weight", [] if abs(ev0["weights_sum"] - want_sum) < 1e-9 else [ev0["weights_sum"]],
                 "weights are normalized reliabilities, capped", "weights not normalized and capped"))
    sl = {m.value["slash_owner"] for m in P("slash_owner")}
    if over:
        out.append(v("ORACLE-8-02", "zero_excess_and_slash", [o for o in over if o not in sl] + ([] if abs(ev0["weights_sum"] - want_sum) < 1e-9 else ["redistributed"]),
                     f"{len(over)} owners above 4%: excess zeroed, stakes slashed", "{n} owners not handled as §8 requires"))
        out.append(v("ORACLE-4.3-01", "owner_aggregation", [] if ev0["owners"] == len({s['owner'] for s in adm}) else ["owners"],
                     "weights summed per controlling owner across devices", "owner weights not summed"))
    else:
        out.append(na("ORACLE-8-02", "zero_excess_and_slash", "owners above the cap", "none"))
        out.append(CheckResult("ORACLE-4.3-01", "owner_aggregation", PASS, "weights summed per controlling owner; none above 4%"))
    obs = [m for m in P("aggregate_confidence")]
    ttl = TTL_MIN[r["data_type"]]
    # silence and staleness
    silent_obs = [m for m in obs if m.value["silent_sources"] > 0]
    if any(e["kind"] == "silence" for e in r["class_events"]):
        out.append(v("ORACLE-9-03", "silence_is_signal", [m.arrived_at for m in obs if m.value["silent_sources"] == 0 and _expect_silent(r, m.arrived_at, ttl)]
                     + [m.arrived_at for m in silent_obs if not m.value["signal"]],
                     "silent or stale sources propagated as explicit degradation, never as a zero-impact state",
                     "{n} evaluations read silence as a state"))
    else:
        out.append(na("ORACLE-9-03", "silence_is_signal", "silence", "no class falls silent"))
    # aggregation
    expect = _expect_series(r, w)
    agg_bad = [m.arrived_at for m in obs if (m.value["S"] is None) != (expect[m.arrived_at] is None) or
               (m.value["S"] is not None and abs(m.value["S"] - expect[m.arrived_at]) > 1e-6)]
    out.append(v("ORACLE-10-01", "likelihood_updates", agg_bad, "S(t) = reliability-weighted posterior of admissible, fresh data (H-OI-3)",
                 "{n} evaluations differ from the weighted posterior"))
    out.append(v("ORACLE-7-03", "unmodified_ingestion", agg_bad, "values used as received; nothing normalized at ingestion",
                 "{n} evaluations used modified values"))
    again = run(r)
    out.append(v("ORACLE-10-02", "reproducible", [] if again.digest() == log.digest() else ["digest"],
                 "identical inputs gave an identical log", "two runs differ"))
    # divergence only across classes
    bias = [e for e in r["class_events"] if e["kind"] == "bias"]
    flags = [m.arrived_at for m in obs if m.value["divergence_flag"]]
    want = [m.arrived_at for m in obs if _cross_div(m.value["class_posteriors"])]
    out.append(v("ORACLE-6-02", "divergence_across_classes", sorted(set(flags) ^ set(want)),
                 f"divergence flags only when class posteriors differ by more than 7% ({len(want)} evaluations)",
                 "{n} evaluations flag divergence otherwise") if bias or r["within_class_spread"] else
               na("ORACLE-6-02", "divergence_across_classes", "disagreement", "no bias declared"))
    out.append(v("ORACLE-4.8-01", "divergence_definition", sorted(set(flags) ^ set(want)), "Divergence Events are disagreements between classes",
                 "{n} wrong flags") if bias or r["within_class_spread"] else na("ORACLE-4.8-01", "divergence_definition", "disagreement", "none"))
    # outputs
    keys = ("S", "aggregate_confidence", "coverage", "divergence_flag", "envelope", "B_raw")
    out.append(v("ORACLE-12-01", "outputs_emitted", [m.arrived_at for m in obs if any(k not in m.value for k in keys) or not m.value["signed"]],
                 "every evaluation emits a signed S(t), weights, coverage, divergence flag, envelope and raw B(t)", "{n} incomplete outputs"))
    out.append(v("ORACLE-12-02", "envelope_range", [m.arrived_at for m in obs if not 0 <= m.value["envelope"] <= 1],
                 "confidence envelopes within [0,1]", "{n} envelopes outside [0,1]"))
    out.append(v("ORACLE-12-03", "b_from_admissible", agg_bad, "B(t) built from admissible measurements only", "{n} B(t) from other data"))
    out.append(v("ORACLE-12-04", "b_model_external", [m.arrived_at for m in obs if "SIMULATION" not in m.value["B_model"]],
                 "B(t) model declared as DKP-8-SIMULATION-001's (none attached)", "{n} B(t) with a PTL-defined model"))
    out.append(v("ORACLE-12-05", "b_raw", [m.arrived_at for m in obs if m.value["S"] is not None and m.value["B_raw"] != m.value["S"]],
                 "B(t) emitted raw, not tuned or rescaled (lab placeholder model, H-OI-4)", "{n} rescaled B(t)"))
    be = [m.value for m in P("b_enforcement")]
    out.append(v("ORACLE-12-06", "b_informational_without_bundle", [x["b_enforcement"] for x in be if x["executed"] and r["calibration_bundle"] != "valid"],
                 "no enforcement triggered by B(t) without a valid L8 bundle", "{n} enforcements triggered by B(t)")
               if be else na("ORACLE-12-06", "b_informational_without_bundle", "enforcement requests on B(t)", "none"))
    out.append(v("ORACLE-2-02", "non_normative_outputs", [x["b_enforcement"] for x in be if x["executed"] and r["calibration_bundle"] != "valid"],
                 "outputs consumed only under activation rules", "{n} consumptions without activation") if be else
               na("ORACLE-2-02", "non_normative_outputs", "consumption requests", "none"))
    out.append(v("ORACLE-5-01", "classified_outputs", [m.arrived_at for m in obs if m.value["classification"] not in ("direct", "proxy")],
                 "every output classified as direct or proxy", "{n} unclassified outputs"))
    out.append(v("ORACLE-5.1-01", "direct_measurement", [m.arrived_at for m in obs if m.value["classification"] != "direct"],
                 f"{r['data_type']} emitted as a direct physical measurement", "{n} otherwise"))
    oq = [m.value for m in P("output")]
    out.append(v("ORACLE-5.3-01", "non_measurable_excluded", [x["output"] for x in oq if x["emitted"] and x["domain"] in NON_MEASURABLE],
                 "no output about intent, dignity, belief, responsibility, consent or social harm", "{n} such outputs emitted")
               if any(x["domain"] != "physical" for x in oq) else na("ORACLE-5.3-01", "non_measurable_excluded", "requests", "none outside the physical domain"))
    # halt
    hl = [m for m in P("halt")]
    due = [m.arrived_at for m in obs if m.value["aggregate_confidence"] < CONF_HALT or m.value["coverage"] < COVERAGE_MIN]
    mer = r["mercy"]
    defer = mer["active"] and mer["ptl_confirmed"] and mer["cause"] == "natural"
    acted = {m.arrived_at for m in hl}
    halted_at = sorted(m.arrived_at for m in hl if m.value["halt"] == "systemic")
    bad = []
    state = False
    hstate = {}
    for m in sorted(hl, key=lambda m: m.arrived_at):
        hstate[m.arrived_at] = m.value["halt"]
    for m in obs:
        t = m.arrived_at
        if t in due and not (defer and t < mer["until_min"]):
            st = hstate.get(t)
            if st == "systemic":
                state = True
            elif st == "lifted":
                state = False
            if not state and st != "systemic":
                bad.append(t)
        else:
            if hstate.get(t) == "lifted":
                state = False
    out.append(v("ORACLE-13-01", "halt_conditions", bad, f"Systemic Halt whenever confidence < 60% or coverage < 80% ({len(due)} evaluations)",
                 "{n} evaluations below a threshold without a halt") if due else na("ORACLE-13-01", "halt_conditions", "halt conditions", "never reached"))
    sys = [m.value for m in hl if m.value["halt"] == "systemic"]
    out.append(v("ORACLE-13-02", "halt_preserves_l1", [x for x in sys if x["l1_state"] != "preserved"],
                 "halts blocked L2+ and preserved L1 state, identity and impact records", "{n} halts reset L1") if sys else
               na("ORACLE-13-02", "halt_preserves_l1", "halts", "none"))
    if mer["active"]:
        dfr = [m.value for m in hl if m.value["halt"] == "deferred"]
        out.append(v("ORACLE-14-01", "mercy_deferral_conditions", ["deferred"] if dfr and not defer else [],
                     "halt deferred only under Mercy with a PTL-confirmed non-anthropogenic cause", "halt deferred without those conditions"))
        out.append(v("ORACLE-14-02", "human_cause_not_natural", ["deferred"] if dfr and mer["cause"] != "natural" else [],
                     "a human-caused degradation is never treated as non-anthropogenic", "a human-caused degradation was deferred"))
        kept = [m.arrived_at for m in obs if m.arrived_at < mer["until_min"] and m.value["silent_sources"] == 0
                and _expect_silent(r, m.arrived_at, ttl)]
        out.append(v("ORACLE-14-03", "deferral_changes_nothing", [x for x in dfr if x["ttl_min"] != ttl or x["aggregation"] != "unchanged"]
                     + kept,
                     "deferral changed neither TTL, weights nor aggregation", "{n} deferrals changed the pipeline"))
        out.append(v("ORACLE-14-04", "deferral_time_limited", [] if mer["until_min"] <= MERCY_MAX_MIN and all(not x["precedent"] for x in dfr) else ["limit"],
                     "deferral limited to the Mercy period (≤ 180 days) and creates no precedent", "deferral unbounded or precedent-setting"))
    else:
        for rid, chk in (("ORACLE-14-01", "mercy_deferral_conditions"), ("ORACLE-14-02", "human_cause_not_natural"),
                         ("ORACLE-14-03", "deferral_changes_nothing"), ("ORACLE-14-04", "deferral_time_limited")):
            out.append(na(rid, chk, "Mercy", "not active"))
    lr = [m.value for m in P("layer_request")]
    br = {m.value["critical_integrity_breach"] for m in msgs if m.source == "AUDIT"}
    out.append(v("ORACLE-15-01", "cross_layer_isolation", [x["layer_request"] for x in lr if x["executed"] or x["by"] not in br],
                 "every higher-layer attempt refused and flagged as a critical integrity breach", "{n} attempts executed or unflagged")
               if lr else na("ORACLE-15-01", "cross_layer_isolation", "higher-layer requests", "none"))
    # constants and finality
    table = {"source": SOURCE_CAP, "owner": OWNER_CAP, "divergence": DIVERGENCE, "halt": CONF_HALT, "coverage": COVERAGE_MIN}
    out.append(v("ORACLE-16-01", "constants_source_owner_divergence", [] if table["source"] == table["owner"] == 0.04 and table["divergence"] == 0.07 else ["table"],
                 "the table repeats §8 (4%, 4%) and §11 (7%)", "the table differs from the body"))
    out.append(v("ORACLE-16-02", "constants_window_halt_coverage", [] if table["halt"] == 0.60 and table["coverage"] == 0.80 else ["table"],
                 "the table repeats §11 (14 days) and §13 (< 60%); 80% is the 'minimum operational threshold' of §13", "the table differs"))
    ch = [m.value for m in P("change")]
    if ch:
        out.append(v("ORACLE-18-01", "immutable_once_deployed", [x["change"] for x in ch if x["accepted"] and x["channel"] == "in_place"],
                     "no in-place modification", "{n} in-place modifications"))
        good = {c["id"] for c in r["protocol_changes"] if c["new_identifier"] and c["incompatibility_declared"] and c["reanchoring"]}
        out.append(v("ORACLE-18-02", "modification_requirements", [x["change"] for x in ch if x["accepted"] and x["change"] not in good],
                     "accepted modifications carry a new identifier, an incompatibility declaration and Genesis re-anchoring",
                     "{n} accepted without them"))
    else:
        for rid, chk in (("ORACLE-18-01", "immutable_once_deployed"), ("ORACLE-18-02", "modification_requirements")):
            out.append(na(rid, chk, "changes", "none"))
    g = P("genesis_co2")[0].value["genesis_co2"]
    out.append(v("ORACLE-2-01", "genesis_anchor", [] if g == GENESIS_CO2 else [g], "the PTL instance carries the Genesis CO2 anchor 426.91 ppm",
                 "the PTL instance is anchored to another value"))
    out.append(v("ORACLE-4.1-01", "state_vector_admissible", [m.arrived_at for m in obs if m.value["S"] is not None and expect[m.arrived_at] is None],
                 "S(t) derived only from admissible inputs", "{n} S(t) without admissible inputs"))
    out.append(v("ORACLE-4.5-01", "coverage_definition", [m.arrived_at for m in obs if abs(m.value["coverage"] - _expect_cov(r, m.arrived_at, ttl)) > 1e-9],
                 "coverage = share of cells observed by sources with non-zero confidence", "{n} coverage values differ"))
    out.append(v("ORACLE-EpistemicInterpretationNote-01", "measurement_records", [m.arrived_at for m in obs if m.value.get("measured_at") != m.arrived_at],
                 "outputs are time-stamped measurement records", "{n} records without their time"))
    out.append(v("ORACLE-EpistemicInterpretationNote-03", "bounded_validity", agg_bad, "no output used beyond its TTL (stale data zeroed)",
                 "{n} outputs used stale data"))
    unbounded = [m.arrived_at for m in obs if not (m.value["bounds"]["revalidation_required"] and m.value["bounds"]["dispute_allowed"]
                                                   and m.value["bounds"]["valid_until_min"] is not None and not m.value["bounds"]["absolute_truth"])]
    out.append(v("ORACLE-EpistemicInterpretationNote-04", "bounded_evaluations", unbounded,
                 f"all {len(obs)} PTL outputs are bounded evaluations: revalidation required, disputable, valid until a TTL, "
                 "no claim to absolute truth (EPISTEMIC-BOUNDARIES)", "{n} PTL outputs published as final truth"))
    return out


def _alive(r, t, ttl, cls):
    e = {x["cls"]: x for x in r["class_events"]}.get(cls)
    last = (t // r["interval_min"]) * r["interval_min"]
    if e and e["kind"] == "silence" and t >= e["from_min"]:
        last = min(last, ((e["from_min"] - 1) // r["interval_min"]) * r["interval_min"])
    return t - last <= ttl, last


def _expect_silent(r, t, ttl):
    return any(not _alive(r, t, ttl, c)[0] for c in CLASSES if r["per_class"] > 0)


def _expect_cov(r, t, ttl):
    cells = set()
    k = 0
    for c in CLASSES:
        ok = _alive(r, t, ttl, c)[0]
        for _ in range(r["per_class"]):
            if ok:
                cells.add(k % r["cells"])
            k += 1
    return len(cells) / r["cells"]


def _expect_series(r, w):
    ttl = TTL_MIN[r["data_type"]]
    out = {}
    srcs = [s for s in _fleet(r) if admissible(s)]
    bias = {e["cls"]: e for e in r["class_events"] if e["kind"] == "bias"}
    for t in range(0, r["horizon_min"], r["eval_every_min"]):
        num = den = 0.0
        for s in srcs:
            ok, last = _alive(r, t, ttl, s["cls"])
            if not ok:
                continue
            x = r["true_value"] if s["cell"] >= 0 else s["value"]
            b = bias.get(s["cls"])
            if b and last >= b["from_min"]:
                x *= 1 + b["bias_pct"] / 100.0
            num += w[s["id"]] * x
            den += w[s["id"]]
        out[t] = num / den if den > 0 else None
    return out


def _cross_div(post):
    cp = list(post.values())
    return bool(cp) and max(cp) > 0 and (max(cp) - min(cp)) / max(cp) > DIVERGENCE


IMPLEMENTS = {
    "ORACLE-1-01": ("sole_interface", "PARTIAL", "Admission rules applied to declared sources."),
    "ORACLE-2-01": ("genesis_anchor", "PARTIAL", "Only the CO2 anchor is compared."),
    "ORACLE-2-02": ("non_normative_outputs", "PARTIAL", "Consumption of B(t) for enforcement only."),
    "ORACLE-3-01": ("human_input_excluded", "PARTIAL", "Declared human sources are refused."),
    "ORACLE-4.1-01": ("state_vector_admissible", "PARTIAL", "One quantity, not a vector."),
    "ORACLE-4.2-01": ("hardware_signed_source", "PARTIAL", "Hardware binding is a declared property."),
    "ORACLE-4.3-01": ("owner_aggregation", "IMPLEMENTED", None),
    "ORACLE-4.4-01": ("normalized_capped_weight", "PARTIAL", "Normalized reliability with caps (H-OI-2)."),
    "ORACLE-4.5-01": ("coverage_definition", "PARTIAL", "The domain is a declared set of cells."),
    "ORACLE-4.7-01": ("independent_classes", "PARTIAL", "Physical separation is declared by class."),
    "ORACLE-4.8-01": ("divergence_definition", "PARTIAL", "Relative difference of class posteriors (H-OI-3)."),
    "ORACLE-5-01": ("classified_outputs", "IMPLEMENTED", None),
    "ORACLE-5.1-01": ("direct_measurement", "PARTIAL", "The quantity is declared direct."),
    "ORACLE-5.3-01": ("non_measurable_excluded", "PARTIAL", "Output requests declare their domain."),
    "ORACLE-6-01": ("three_classes", "IMPLEMENTED", None),
    "ORACLE-6-02": ("divergence_across_classes", "IMPLEMENTED", None),
    "ORACLE-7-01": ("signed_timestamped_registered", "PARTIAL", "Declared properties."),
    "ORACLE-7-02": ("open_schema", "IMPLEMENTED", None),
    "ORACLE-7-03": ("unmodified_ingestion", "IMPLEMENTED", None),
    "ORACLE-8-02": ("zero_excess_and_slash", "PARTIAL", "Owner excess reduced proportionally (H-OI-2); every owner has a stake. "
                                                         "A source has one owner, so the owner cap also bounds every source."),
    "ORACLE-9-03": ("silence_is_signal", "IMPLEMENTED", None),
    "ORACLE-10-01": ("likelihood_updates", "PARTIAL", "Weighted posterior mean with a flat prior (H-OI-3)."),
    "ORACLE-10-02": ("reproducible", "IMPLEMENTED", None),
    "ORACLE-12-01": ("outputs_emitted", "IMPLEMENTED", None),
    "ORACLE-12-02": ("envelope_range", "PARTIAL", "Envelope = aggregate confidence (H-OI-2)."),
    "ORACLE-12-03": ("b_from_admissible", "PARTIAL", "Placeholder B(t) model (H-OI-4)."),
    "ORACLE-12-04": ("b_model_external", "IMPLEMENTED", None),
    "ORACLE-12-05": ("b_raw", "PARTIAL", "Placeholder B(t) model (H-OI-4)."),
    "ORACLE-12-06": ("b_informational_without_bundle", "IMPLEMENTED", None),
    "ORACLE-13-01": ("halt_conditions", "PARTIAL", "'Aggregate confidence' = sum of live weights (H-OI-2); integrity compromise not modelled."),
    "ORACLE-13-02": ("halt_preserves_l1", "PARTIAL", "Recorded effect of the halt."),
    "ORACLE-14-01": ("mercy_deferral_conditions", "PARTIAL", "Mercy status and cause are declared."),
    "ORACLE-14-02": ("human_cause_not_natural", "IMPLEMENTED", None),
    "ORACLE-14-03": ("deferral_changes_nothing", "IMPLEMENTED", None),
    "ORACLE-14-04": ("deferral_time_limited", "PARTIAL", "Limit = 180 days of Code A.4 (F-027 applies)."),
    "ORACLE-15-01": ("cross_layer_isolation", "IMPLEMENTED", None),
    "ORACLE-16-01": ("constants_source_owner_divergence", "IMPLEMENTED", None),
    "ORACLE-16-02": ("constants_window_halt_coverage", "IMPLEMENTED", None),
    "ORACLE-18-01": ("immutable_once_deployed", "IMPLEMENTED", None),
    "ORACLE-18-02": ("modification_requirements", "PARTIAL", "Declared properties of the change."),
    "ORACLE-EpistemicInterpretationNote-01": ("measurement_records", "PARTIAL", "Time stamps only."),
    "ORACLE-EpistemicInterpretationNote-03": ("bounded_validity", "PARTIAL", "TTL bound only."),
    "ORACLE-EpistemicInterpretationNote-04": ("bounded_evaluations", "PARTIAL", "Bounds recorded on each output (revalidation, dispute, TTL)."),
}

B = {"type": "bool"}


def _lst(fields, default, label, mx=20):
    return {"type": "list", "min_items": 0, "max_items": mx, "items": {"type": "object", "fields": fields}, "default": default,
            "source": "user", "label": label}


class OracleIngestionModule(LabModule):
    id = "oracle_ingestion"
    version = "1.0.0"
    title = {"en": "Physical Truth Layer pipeline (ORACLE §1-§18)", "ru": "Конвейер слоя физической истины (ORACLE §1-§18)"}
    summary = {"en": "Thirty sensors, a human panel, a proprietary feed, one class going silent, a request to enforce on B(t): does the PTL "
                     "admit, weight, aggregate, halt and refuse exactly as ORACLE says?",
               "ru": "Тридцать датчиков, панель людей, проприетарный поток, замолчавший класс, запрос принуждения по B(t): принимает, "
                     "взвешивает, агрегирует, останавливает и отказывает ли PTL ровно так, как пишет ORACLE?"}
    protocols = ["DKP-0-ORACLE-001"]
    example_order = ["class_goes_silent", "few_owners", "faulty_ptl"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_oracle_ingestion_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-OI-1", "source": "hypothesis", "text": {
            "en": "Fleet: equal reliability, sources assigned round-robin to owners and to cells of the observed domain.",
            "ru": "Парк: равная надёжность, источники по кругу распределены по владельцам и ячейкам наблюдаемой области."}},
        {"id": "H-OI-2", "source": "hypothesis", "text": {
            "en": "Weight = reliability / Σ reliability, capped at 4% per source; an owner above 4% has its sources scaled down to 4%; "
                  "excess is zeroed, not redistributed. 'Aggregate confidence' (§13) = sum of live weights; envelope = the same, in [0,1].",
            "ru": "Вес = надёжность / Σ надёжностей, не более 4% на источник; владелец выше 4% урезается до 4%; излишек обнуляется, "
                  "а не перераспределяется. 'Совокупная уверенность' (§13) = сумма живых весов; конверт — то же в [0,1]."}},
        {"id": "H-OI-3", "source": "hypothesis", "text": {
            "en": "Bayesian ensemble (§10) = weight-precision Gaussian updates with a flat prior: S(t) is the weighted mean of fresh "
                  "admissible readings. Divergence = relative spread of the class posteriors.",
            "ru": "Байесовский ансамбль (§10) = гауссовы обновления с точностью по весу и плоским априори: S(t) — взвешенное среднее "
                  "свежих допустимых показаний. Расхождение = относительный разброс апостериорных средних классов."}},
        {"id": "H-OI-4", "source": "hypothesis", "text": {
            "en": "B(t) placeholder: the raw posterior of the observed quantity. Its real model belongs to DKP-8-SIMULATION-001, which "
                  "has no bundle (F-014); B(t) is informational only.",
            "ru": "B(t)-заглушка: сырое апостериорное значение наблюдаемой величины. Настоящая модель — в DKP-8-SIMULATION-001, "
                  "пакета нет (F-014); B(t) только информационный."}},
    ]
    inputs = {
        "horizon_min": {"type": "int", "min": 60, "max": 20160, "default": 2880, "unit": "min", "source": "user",
                        "label": {"en": "Horizon", "ru": "Горизонт"}},
        "eval_every_min": {"type": "int", "min": 1, "max": 1440, "default": 60, "unit": "min", "source": "user",
                           "label": {"en": "Evaluation step", "ru": "Шаг оценки"}},
        "data_type": {"type": "enum", "values": list(TTL_MIN), "default": "co2", "source": "text",
                      "label": {"en": "Data type (TTL from §17)", "ru": "Тип данных (TTL по §17)"}},
        "per_class": {"type": "int", "min": 0, "max": 50, "default": 10, "source": "user",
                      "label": {"en": "Sources per class", "ru": "Источников на класс"}},
        "owners": {"type": "int", "min": 1, "max": 150, "default": 30, "source": "user", "label": {"en": "Distinct owners", "ru": "Владельцев"}},
        "cells": {"type": "int", "min": 1, "max": 150, "default": 30, "source": "hypothesis",
                  "label": {"en": "Cells of the observed domain", "ru": "Ячеек наблюдаемой области"}},
        "interval_min": {"type": "int", "min": 1, "max": 1440, "default": 30, "unit": "min", "source": "user",
                         "label": {"en": "Sampling interval", "ru": "Интервал измерений"}},
        "true_value": {"type": "number", "min": 0.001, "max": 10 ** 6, "default": 427.0, "source": "user",
                       "label": {"en": "Physical value", "ru": "Физическое значение"}},
        "class_events": _lst({"cls": {"type": "enum", "values": list(CLASSES)}, "kind": {"type": "enum", "values": ["silence", "bias"]},
                              "from_min": {"type": "int", "min": 0, "max": 20160}, "bias_pct": {"type": "number", "min": -100, "max": 100, "default": 0.0}},
                             [{"cls": "autonomous", "kind": "silence", "from_min": 1500, "bias_pct": 0.0}],
                             {"en": "Class events", "ru": "События классов"}),
        "within_class_spread": {"type": "bool", "default": False, "source": "user",
                                "label": {"en": "Declare a within-class disagreement check", "ru": "Проверять расхождение внутри класса"}},
        "special_sources": _lst({"id": {"type": "str"}, "owner": {"type": "str"},
                                 "cls": {"type": "enum", "values": list(CLASSES) + ["human_report", "manual_entry"]},
                                 "signed": {"type": "bool", "default": True}, "clock": {"type": "bool", "default": True},
                                 "registered": {"type": "bool", "default": True},
                                 "schema": {"type": "enum", "values": ["open", "proprietary"], "default": "open"},
                                 "reliability": {"type": "number", "min": 0.001, "max": 100, "default": 1.0},
                                 "value": {"type": "number", "min": -10 ** 6, "max": 10 ** 6}},
                                [{"id": "panel", "owner": "citizens", "cls": "human_report", "value": 500.0},
                                 {"id": "vendor_feed", "owner": "vendor_x", "cls": "ground", "schema": "proprietary", "value": 427.0},
                                 {"id": "rogue_sat", "owner": "anon", "cls": "orbital", "signed": False, "value": 300.0}],
                                {"en": "Declared special sources", "ru": "Особые источники"}),
        "mercy": {"type": "object", "source": "user", "label": {"en": "Crisis Mercy status (Code A.4)", "ru": "Статус кризисного милосердия"},
                  "fields": {"active": {"type": "bool", "default": False}, "ptl_confirmed": {"type": "bool", "default": False},
                             "cause": {"type": "enum", "values": ["natural", "human_action"], "default": "natural"},
                             "until_min": {"type": "int", "min": 0, "max": 10 ** 6, "default": 0}},
                  "default": {"active": False, "ptl_confirmed": False, "cause": "natural", "until_min": 0}},
        "calibration_bundle": {"type": "enum", "values": ["none", "valid", "expired", "invalid_signature", "other_model"], "default": "none",
                               "source": "missing",
                               "label": {"en": "Valid L8 calibration bundle attached (none exists, F-014)", "ru": "Действующий пакет калибровки L8 (нет, F-014)"}},
        "b_enforcement_requests": _lst({"min": {"type": "int", "min": 0, "max": 20160}, "consumer": {"type": "str"}},
                                       [{"min": 600, "consumer": "code_kill_switch"}], {"en": "Enforcement requests on B(t)", "ru": "Запросы принуждения по B(t)"}),
        "higher_layer_requests": _lst({"min": {"type": "int", "min": 0, "max": 20160}, "protocol": {"type": "str"},
                                       "action": {"type": "enum", "values": list(LAYER_ACTIONS)}},
                                      [{"min": 700, "protocol": "finance", "action": "influence_weights"},
                                       {"min": 710, "protocol": "crisis", "action": "modify_ttl"}],
                                      {"en": "Higher-layer requests", "ru": "Запросы верхних слоёв"}),
        "output_requests": _lst({"name": {"type": "str"}, "domain": {"type": "enum", "values": ["physical"] + list(NON_MEASURABLE)}},
                                [{"name": "co2_level", "domain": "physical"}, {"name": "protest_intent", "domain": "intent"}],
                                {"en": "Requested outputs", "ru": "Запрошенные выходы"}),
        "protocol_changes": _lst({"id": {"type": "str"}, "channel": {"type": "enum", "values": ["in_place", "new_protocol"]},
                                  "new_identifier": {"type": "bool", "default": False}, "incompatibility_declared": {"type": "bool", "default": False},
                                  "reanchoring": {"type": "bool", "default": False}},
                                 [{"id": "ttl_tweak", "channel": "in_place"},
                                  {"id": "oracle_002", "channel": "new_protocol", "new_identifier": True, "incompatibility_declared": True,
                                   "reanchoring": True}],
                                 {"en": "Changes to ORACLE", "ru": "Изменения ORACLE"}),
        "genesis_co2": {"type": "number", "min": 0, "max": 10 ** 4, "default": GENESIS_CO2, "source": "text",
                        "label": {"en": "Genesis CO2 anchor of this PTL instance", "ru": "Якорь CO2 Генезиса для этого PTL"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        if r["per_class"] * len(CLASSES) + len(r["special_sources"]) == 0:
            p.append("input: no source")
        ids = [s["id"] for s in r["special_sources"]]
        if len(set(ids)) != len(ids):
            p.append("input.special_sources: repeated id")
        if len({e["cls"] for e in r["class_events"]}) != len(r["class_events"]):
            p.append("input.class_events: one event per class")
        if r["mercy"]["active"] and r["mercy"]["until_min"] <= 0:
            p.append("input.mercy: an active Mercy needs until_min > 0")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        obs = [{"min": m.arrived_at, **{k: m.value[k] for k in ("S", "aggregate_confidence", "coverage", "divergence_flag", "signal")}}
               for m in msgs if m.source == "PTL" and "aggregate_confidence" in m.value]
        halts = [{"min": m.arrived_at, **m.value} for m in msgs if m.source == "PTL" and "halt" in m.value]
        outputs = {"evaluations": obs, "halts": halts,
                   "decisions": [{"min": m.arrived_at, **m.value} for m in msgs if m.source in ("PTL", "AUDIT") and m.kind in ("decision", "action", "notice")
                                 and "halt" not in m.value],
                   "violations": sorted(c.requirement_id for c in res if c.status == FAIL),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        first = [h["min"] for h in halts if h["halt"] == "systemic"]
        e = [{"en": f"{len(obs)} evaluations; aggregate confidence {obs[0]['aggregate_confidence']:.0%} at start; first Systemic Halt at minute "
                    f"{first[0] if first else '—'}; violated: {', '.join(outputs['violations']) or 'none'}.",
              "ru": f"{len(obs)} оценок; совокупная уверенность {obs[0]['aggregate_confidence']:.0%} в начале; первая системная остановка на минуте "
                    f"{first[0] if first else '—'}; нарушены: {', '.join(outputs['violations']) or 'нет'}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        first = [h["min"] for h in outputs["halts"] if h["halt"] == "systemic"]
        return {"violations": len(outputs["violations"]), "first_halt_min": first[0] if first else -1,
                "start_confidence": outputs["evaluations"][0]["aggregate_confidence"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "class_goes_silent": {},
            "few_owners": {"owners": 10, "class_events": []},
            "fifteen_owners": {"owners": 15, "class_events": []},
            "orbital_bias": {"class_events": [{"cls": "orbital", "kind": "bias", "from_min": 600, "bias_pct": 15.0}]},
            "mercy_natural": {"mercy": {"active": True, "ptl_confirmed": True, "cause": "natural", "until_min": 100000}},
            "mercy_human_cause": {"mercy": {"active": True, "ptl_confirmed": True, "cause": "human_action", "until_min": 100000}},
            "bundle_attached": {"calibration_bundle": "valid"},
            "expired_bundle": {"calibration_bundle": "expired"},
            "five_per_class": {"per_class": 5, "owners": 15, "cells": 15, "class_events": []},
            "within_class_spread": {"within_class_spread": True, "class_events": [],
                                    "special_sources": [{"id": "sat_x", "owner": "o_x", "cls": "orbital", "value": 470.0}]},
            "faulty_ptl": {"faults": ["accept_human_input", "no_owner_cap", "silence_as_zero", "enforce_on_b", "accept_layer_override"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"no_sources": {"per_class": 0, "special_sources": []},
                "two_events_one_class": {"class_events": [{"cls": "ground", "kind": "silence", "from_min": 10},
                                                          {"cls": "ground", "kind": "bias", "from_min": 20}]},
                "mercy_without_end": {"mercy": {"active": True, "ptl_confirmed": True, "cause": "natural", "until_min": 0}}}


for _spec in OracleIngestionModule.inputs.values():
    if _spec["type"] == "list" and _spec["items"]["type"] == "object":
        _spec["default"] = [resolve(x, _spec["items"]["fields"]) for x in _spec["default"]]
