"""
FAILURE CHAIN module — stale and contradictory data (scenario S-LAB-02).

DKP-0-ORACLE-001 (TTL, divergence, halt) → DKP-1-EPISTEMIC-BOUNDARIES-001 (output
metadata, disputes) → DKP-4-EPISTEMIC-TRANSITIONS-001 (downgrade, status quo,
re-entry) → DKP-2-ASSETS-001 / DKP-2-FINANCE-001 (dependent asset control and
state-based transactions).

Three parts are kept apart:
  generator  readings of three independent oracle classes (ORACLE §6) from the
             declared scenario: true value, a biased or silent class, exclusion,
             systemic halt, dispute;
  adapter    a reference implementation of the rules, step by step; at step k it
             sees only readings with time <= k.  Declared ``faults`` switch single
             rules off so that the checks can be seen to detect the violation;
  checker    recomputes TTL weights, S(t), divergence and the epistemic state from
             the generator's readings and judges the adapter's log against the
             provisions.  It does not trust the adapter's own flags.

The mapping of PTL conditions to EPISTEMIC-BOUNDARIES §5 states (H-FC-1) and the
divergence metric (H-FC-3) are declared hypotheses shared by adapter and checker:
they define the experiment, they are not results.  Penalty units and asset
restriction levels are model units (H-FC-6), not money or legal measures.
"""

from __future__ import annotations

import bisect
import copy
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.run import canonical_json, sha256_text
from lab.core.schema import LabInputError

LAB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORACLE_TEXT = os.path.join(LAB_ROOT, "corpus", "world-aad3e86", "Dikenocracy", "Protocols",
                           "L0_Physical_Truth", "DKP-0-ORACLE-001.md")

CLASSES = ("ground", "orbital", "autonomous")       # ORACLE §6
THRESHOLD = 0.07                                     # ORACLE §11, §16: divergence threshold 7 %
ARBITRATION_MINUTES = 14 * 1440                      # ORACLE §11, §16: arbitration window 14 days
MAX_READINGS = 300_000

VALID, CONDITIONAL, INVALID = "VALID", "CONDITIONAL", "INVALID"
SUFFICIENT, INSUFFICIENT, DEGRADED = "SUFFICIENT_DATA", "INSUFFICIENT_DATA", "DEGRADED_SIGNAL"
CONSISTENT, CONFLICT, UNRESOLVED = "CONSISTENT", "ORACLE_CONFLICT", "UNRESOLVED"
METADATA_FIELDS = ("validity_state", "confidence_state", "consistency_state",
                   "scope_ref", "revalidation_required", "dispute_allowed")      # EB §5

# data type (input value) -> row label of the ORACLE §17 table
DATA_TYPES = {
    "co2": "Atmospheric CO₂ concentration",
    "surface_temperature": "Surface temperature (land/sea)",
    "active_fire": "Active fire detection",
    "biodiversity": "Biodiversity indices",
    "land_use": "Land-use change",
}
TTL_REQUIREMENT = {"co2": "ORACLE-17-01", "surface_temperature": "ORACLE-17-01", "active_fire": "ORACLE-17-01",
                   "biodiversity": "ORACLE-17-02", "land_use": "ORACLE-17-02"}
UNIT_MINUTES = {"minute": 1, "minutes": 1, "hour": 60, "hours": 60, "day": 1440, "days": 1440}

FAULTS = {
    "stale_weight_kept": "data older than its TTL keeps its weight",
    "divergence_ignored": "no divergence flag is raised",
    "no_propagation": "upstream downgrades do not reach dependent outputs",
    "accrue_during_suspension": "penalties keep accruing while suspended",
    "escalate_during_suspension": "asset restriction keeps escalating while suspended",
    "auto_reactivate": "after recovery the old evaluation is reactivated without recomputation",
    "mutate_on_dispute": "a dispute overwrites the original evaluation in place",
    "execute_incomplete": "outputs with incomplete metadata are executed",
    "repair_metadata": "the consumer fills in missing metadata and executes",
    "arbitration_overrun": "the arbitration stays open after its 14-day maximum",
    "deadline_rounded_up": "the 14-day deadline is rounded up to the next grid step (the lab's error before review КТ4-GPT-01)",
}


def ttl_registry() -> Dict[str, int]:
    """Maximum TTL per data type in minutes, read from the §17 table of the pinned text."""
    with open(ORACLE_TEXT, encoding="utf-8") as f:
        text = f.read()
    section = text.split("### 17. TTL Registry (Normative)", 1)[1].split("### 18.", 1)[0]
    rows = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        m = re.fullmatch(r"(\d+) (minutes?|hours?|days?)", cells[-1]) if len(cells) == 2 else None
        if m:
            rows[cells[0]] = int(m.group(1)) * UNIT_MINUTES[m.group(2)]
    missing = [label for label in DATA_TYPES.values() if label not in rows]
    if missing:
        raise RuntimeError(f"ORACLE §17 table: rows not found: {missing}")
    return {key: rows[label] for key, label in DATA_TYPES.items()}


TTL_TEXT = ttl_registry()


# declared hypotheses shared by adapter and checker ---------------------------------
def spread(values: List[float]) -> float:
    """H-FC-3: largest pairwise |a-b| / max(|a|,|b|) between admissible class values."""
    worst = 0.0
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            m = max(abs(values[i]), abs(values[j]))
            if m > 0:
                worst = max(worst, abs(values[i] - values[j]) / m)
    return worst


def classify(admissible: int, non_excluded: int, divergence: bool, halt: bool) -> Dict[str, str]:
    """H-FC-1: PTL conditions -> EPISTEMIC-BOUNDARIES §5 states."""
    if admissible == 0:
        confidence = INSUFFICIENT
    elif admissible < non_excluded:
        confidence = DEGRADED
    else:
        confidence = SUFFICIENT
    if divergence:
        consistency = CONFLICT
    elif admissible >= 2:
        consistency = CONSISTENT
    else:
        consistency = UNRESOLVED
    if halt or confidence == INSUFFICIENT or consistency == CONFLICT:
        validity = INVALID
    elif confidence == DEGRADED or consistency == UNRESOLVED:
        validity = CONDITIONAL
    else:
        validity = VALID
    return {"validity_state": validity, "confidence_state": confidence, "consistency_state": consistency}


def listed_downgrades(prev: Dict[str, str], cur: Dict[str, str]) -> List[str]:
    """The upstream transitions listed in EPISTEMIC-TRANSITIONS §4.1."""
    out = []
    if prev["validity_state"] == VALID and cur["validity_state"] in (CONDITIONAL, INVALID):
        out.append("validity_state")
    if prev["consistency_state"] == CONSISTENT and cur["consistency_state"] == CONFLICT:
        out.append("consistency_state")
    if prev["confidence_state"] == SUFFICIENT and cur["confidence_state"] == DEGRADED:
        out.append("confidence_state")
    return out


def in_window(window: List[float], k: int) -> bool:
    return int(window[0]) <= k < int(window[1])


def complete(md: Optional[Dict[str, Any]]) -> bool:
    return bool(md) and all(f in md and md[f] is not None for f in METADATA_FIELDS)


# generator --------------------------------------------------------------------------
def generate(r: Dict[str, Any]) -> Dict[str, List[Tuple[int, float]]]:
    """Readings (minute, value) of each oracle class over the horizon."""
    step = r["step_minutes"]
    out = {}
    for c in CLASSES:
        rows = []
        for t in range(0, r["horizon_steps"] * step, r[f"{c}_interval_minutes"]):
            k = t // step
            if c == r["silent_class"] and in_window(r["silent_window"], k):
                continue
            changed = 0 <= r["value_change_at_step"] <= k
            v = r["changed_value"] if changed else r["true_value"]
            if c == r["faulty_class"] and in_window(r["bias_window"], k):
                v = v * (1 + r["bias_percent"] / 100)
            rows.append((t, round(v, 9)))
        out[c] = rows
    return out


def observation_log(readings: Dict[str, List[Tuple[int, float]]]) -> EventLog:
    """Generator readings as §6.3 messages: measured and available at the same minute."""
    log = EventLog("minute", tie_rule="arrival minute; one reading per class and minute")
    log.extend(Message(event_id=f"obs-{c}-{t}", kind="observation", source=c, arrived_at=t, measured_at=t,
                       value=v, unit="model unit")
               for c in CLASSES for t, v in readings[c])
    return log


# adapter ----------------------------------------------------------------------------
def run_adapter(r: Dict[str, Any], readings: Dict[str, List[Tuple[int, float]]],
                ttl: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Reference implementation of the rules (minus declared faults). Returns rows, events, evaluations."""
    faults = set(r["faults"])
    step, limit, esc = r["step_minutes"], r["limit"], r["escalation_every_steps"]
    scope = f"scenario/{r['data_type']}"
    log = observation_log(readings)                    # the adapter reads only through log.view(now)
    rows: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    store: Dict[str, Dict[str, Any]] = {}
    prev = None
    div_open = False
    arb_open = None
    mode, current, reval, pending = "NO_EVALUATION", None, False, None
    level = penalty = active_steps = 0

    def new_evaluation(k, S, meta, cls, supersedes):
        rec = {"id": f"EV-{len(store) + 1:03d}", "step": k, "value": S,
               "inputs": {"S": S, "last_reading_age": {c: cls[c]["age"] for c in CLASSES},
                          "ptl": dict(meta)},
               "provenance": sorted(cls[c]["event_id"] for c in CLASSES if cls[c]["weight"]),
               "metadata": {**meta, "scope_ref": scope, "revalidation_required": False, "dispute_allowed": True},
               "supersedes": supersedes}
        store[rec["id"]] = rec
        events.append({"step": k, "type": "evaluation_created", "evaluation": rec["id"], "value": S,
                       "digest": sha256_text(canonical_json(rec))})
        return rec["id"]

    def emit(kind, k, new_level=None, drop_scope=False):
        md = dict(store[current]["metadata"])
        if kind == "asset_order":
            md["revalidation_required"] = True                     # ASSETS §8.3(e)
        if drop_scope:
            md.pop("scope_ref")
        if complete(md):
            classified, executed, out = md["validity_state"], True, md
        elif "repair_metadata" in faults:
            out = {**md, "scope_ref": scope}
            classified, executed = out["validity_state"], True
        elif "execute_incomplete" in faults:
            classified, executed, out = md.get("validity_state"), True, md
        else:
            classified, executed, out = INVALID, False, None      # EB §5.x: refused, not repaired
        ev = {"step": k, "type": kind, "evaluation": current, "emitted": md, "classified": classified,
              "executed": executed, "executed_output": out}
        if kind == "asset_order":
            ev["level"] = new_level
        events.append(ev)
        return executed

    for k in range(r["horizon_steps"]):
        t = k * step
        halt = in_window(r["halt_window"], k)
        cls = {}
        view = log.view(t)
        for c in CLASSES:
            m = view.latest("observation", c)
            excluded = c == r["faulty_class"] and 0 <= r["exclude_faulty_at_step"] <= k
            if m is None:
                cls[c] = {"age": None, "value": None, "weight": 0, "excluded": excluded, "event_id": None}
                continue
            fresh = t - m.measured_at <= ttl or "stale_weight_kept" in faults
            cls[c] = {"age": t - m.measured_at, "value": m.value, "weight": 1 if fresh and not excluded else 0,
                      "excluded": excluded, "event_id": m.event_id}
        adm = [c for c in CLASSES if cls[c]["weight"]]
        vals = [cls[c]["value"] for c in adm]
        S = round(sum(vals) / len(vals), 9) if vals else None
        sp = spread(vals)
        if "divergence_ignored" not in faults:
            if not div_open and sp > THRESHOLD:
                div_open = True
                events.append({"step": k, "type": "divergence_open", "spread": round(sp, 6)})
                arb_open = k
                events.append({"step": k, "type": "arbitration_open"})
            elif div_open and len(adm) >= 2 and sp <= THRESHOLD:
                div_open = False
                by = "exclusion" if any(cls[c]["excluded"] for c in CLASSES) else "convergence"
                events.append({"step": k, "type": "divergence_resolved", "by": by, "spread": round(sp, 6)})
                if arb_open is not None:
                    events.append({"step": k, "type": "arbitration_closed", "outcome": f"resolved by {by}"})
                    arb_open = None
            # ORACLE §11: the arbitration window is a maximum; it ends even when the data still disagree.
            # What follows an unresolved window is not defined (F-018); the freeze stays (H-FC-7).
            # On a step grid the window closes at the last step that does not pass the 14-day deadline: the next
            # step would (review КТ4-GPT-01; a step longer than 14 days closes the window where it opens).
            last = ARBITRATION_MINUTES // r["step_minutes"]
            if "deadline_rounded_up" in faults:
                last = -(-ARBITRATION_MINUTES // r["step_minutes"])
            if arb_open is not None and (k - arb_open) >= last and \
                    "arbitration_overrun" not in faults:
                events.append({"step": k, "type": "arbitration_closed", "outcome": "window expired unresolved",
                               "elapsed_minutes": (k - arb_open) * r["step_minutes"], "deadline_minutes": ARBITRATION_MINUTES})
                arb_open = None
        meta = classify(len(adm), sum(1 for c in CLASSES if not cls[c]["excluded"]), div_open, halt)

        downs = listed_downgrades(prev, meta) if prev else []
        if downs and mode == "ACTIVE" and "no_propagation" not in faults:
            mode, reval = "SUSPENDED", True
            pending = {"reason": "downgrade", "since": k, "ready_at": None}
            events.append({"step": k, "type": "suspend", "reason": "downgrade", "fields": downs, "evaluation": current})
        if k == r["dispute_at_step"] and current is not None:
            events.append({"step": k, "type": "dispute", "evaluation": current})
            if mode == "ACTIVE":
                mode, reval = "SUSPENDED", True
                events.append({"step": k, "type": "suspend", "reason": "dispute", "evaluation": current})
            pending = {"reason": "dispute", "since": k, "ready_at": None}

        valid = meta["validity_state"] == VALID
        if pending and not valid:
            pending["ready_at"] = None                             # awaiting an admissible state
        if current is None and valid:
            current = new_evaluation(k, S, meta, cls, None)
            mode = "ACTIVE" if S > limit else "INACTIVE"
            events.append({"step": k, "type": "activate" if mode == "ACTIVE" else "no_enforcement",
                           "evaluation": current})
        elif pending and valid:
            if "auto_reactivate" in faults and pending["reason"] == "downgrade":
                mode, reval, pending = "ACTIVE", False, None
                events.append({"step": k, "type": "resume", "evaluation": current})
            else:
                if pending["ready_at"] is None:
                    pending["ready_at"] = k + r["recompute_delay_steps"]
                if k >= pending["ready_at"]:
                    old = current
                    if "mutate_on_dispute" in faults and pending["reason"] == "dispute":
                        store[old].update(step=k, value=S, inputs={"S": S, "ptl": dict(meta), "last_reading_age":
                                                                    {c: cls[c]["age"] for c in CLASSES}})
                        events.append({"step": k, "type": "recomputed", "evaluation": old, "reason": "dispute"})
                    else:
                        current = new_evaluation(k, S, meta, cls, old)
                        events.append({"step": k, "type": "recomputed", "evaluation": current,
                                       "reason": pending["reason"]})
                        if pending["reason"] == "dispute":
                            events.append({"step": k, "type": "delta", "old": old, "new": current,
                                           "old_value": store[old]["value"], "new_value": S,
                                           "delta": round(S - store[old]["value"], 9)})
                    reval, pending = False, None
                    if store[current]["value"] > limit:
                        mode = "ACTIVE"
                        events.append({"step": k, "type": "resume", "evaluation": current})
                    else:
                        if level:
                            events.append({"step": k, "type": "lift", "evaluation": current, "level": 0})
                            level = 0
                        mode = "INACTIVE"
                        events.append({"step": k, "type": "end", "evaluation": current})
        elif (current is not None and valid and mode in ("ACTIVE", "INACTIVE")
              and r["reevaluation_policy"] != "declared_events"):
            old_value = store[current]["value"]
            new_data = any(cls[c]["weight"] and cls[c]["age"] == 0 for c in CLASSES)    # a reading arrived now
            if r["reevaluation_policy"] == "new_admissible_data" and new_data and S != old_value:
                old = current
                current = new_evaluation(k, S, meta, cls, old)
                events.append({"step": k, "type": "recomputed", "evaluation": current, "reason": "new_admissible_data"})
                if S > limit:
                    if mode != "ACTIVE":
                        events.append({"step": k, "type": "resume", "evaluation": current})
                    mode = "ACTIVE"
                else:
                    if level:
                        events.append({"step": k, "type": "lift", "evaluation": current, "level": 0})
                        level = 0
                    if mode != "INACTIVE":
                        events.append({"step": k, "type": "end", "evaluation": current})
                    mode = "INACTIVE"
            elif (r["reevaluation_policy"] == "material_change"
                  and abs(S - old_value) > abs(old_value) * r["material_change_percent"] / 100):
                events.append({"step": k, "type": "material_change", "evaluation": current,
                               "old_value": old_value, "S": S})
                if mode == "ACTIVE":
                    mode, reval = "SUSPENDED", True
                    events.append({"step": k, "type": "suspend", "reason": "material_change", "evaluation": current})
                pending = {"reason": "material_change", "since": k, "ready_at": None}

        acting = mode == "ACTIVE"
        if acting or (mode == "SUSPENDED" and "accrue_during_suspension" in faults):
            if emit("transaction", k):
                penalty += 1
        if acting or (mode == "SUSPENDED" and "escalate_during_suspension" in faults):
            active_steps += 1
            if level == 0 and acting:
                if emit("asset_order", k, 1):
                    level = 1
            elif level and active_steps % esc == 0:
                if emit("asset_order", k, level + 1):
                    level += 1
        if acting and k == r["incomplete_order_at_step"]:
            if emit("asset_order", k, level + 1, drop_scope=True):
                level += 1

        rows.append({"step": k, "t_min": t, "classes": copy.deepcopy(cls), "admissible": adm, "S": S,
                     "spread": round(sp, 9), "divergence_open": div_open, "halt": halt, "ptl": meta,
                     "mode": mode, "revalidation_required": reval, "evaluation": current,
                     "asset_level": level, "penalty_units": penalty})
        prev = meta
    return rows, events, store


def contradicted_steps(r: Dict[str, Any], rows: List[Dict[str, Any]], store: Dict[str, Dict[str, Any]]) -> int:
    """Steps of enforcement while S(t) and the relied-on evaluation lie on different sides of the limit."""
    return sum(1 for row in rows if row["mode"] == "ACTIVE" and row["S"] is not None
               and (row["S"] > r["limit"]) != (store[row["evaluation"]]["value"] > r["limit"]))


# checker ----------------------------------------------------------------------------
def expected_states(r: Dict[str, Any], readings: Dict[str, List[Tuple[int, float]]], ttl: int) -> List[Dict[str, Any]]:
    """Independent recomputation of what the PTL output must be at every step."""
    step = r["step_minutes"]
    times = {c: [t for t, _ in readings[c]] for c in CLASSES}
    out = []
    div = False
    for k in range(r["horizon_steps"]):
        t = k * step
        adm: Dict[str, float] = {}
        zero, non_excluded = [], 0
        for c in CLASSES:
            if c == r["faulty_class"] and 0 <= r["exclude_faulty_at_step"] <= k:
                continue
            non_excluded += 1
            i = bisect.bisect_right(times[c], t) - 1
            if i < 0 or t - times[c][i] > ttl:
                zero.append(c)
            else:
                adm[c] = readings[c][i][1]
        vals = [adm[c] for c in CLASSES if c in adm]
        sp = spread(vals)
        opened = closed = False
        if not div and sp > THRESHOLD:
            div = opened = True
        elif div and len(vals) >= 2 and sp <= THRESHOLD:
            div, closed = False, True
        halt = in_window(r["halt_window"], k)
        out.append({"step": k, "admissible": sorted(adm), "zero_weight": zero,
                    "S": round(sum(vals) / len(vals), 9) if vals else None, "spread": sp,
                    "divergence": div, "opened": opened, "closed": closed, "halt": halt,
                    "meta": classify(len(vals), non_excluded, div, halt)})
    return out


def exp_runs_longer_than(steps: List[int], n: int) -> List[Tuple[int, int]]:
    """Runs of divergence longer than n steps (arbitration windows that must expire unresolved)."""
    return [(a, b) for a, b in runs(steps) if b - a + 1 > n]


def runs(steps: List[int]) -> List[Tuple[int, int]]:
    """Maximal runs [a, b] of consecutive step numbers."""
    out: List[Tuple[int, int]] = []
    for s in steps:
        if out and s == out[-1][1] + 1:
            out[-1] = (out[-1][0], s)
        else:
            out.append((s, s))
    return out


def verdict(rid: str, check: str, bad: List[Any], ok_text: str, bad_text: str, evidence: Optional[Dict] = None):
    ev = dict(evidence or {})
    if bad:
        ev["violations"] = bad[:10]
        ev["violation_count"] = len(bad)
    return CheckResult(rid, check, FAIL if bad else PASS, bad_text.format(n=len(bad)) if bad else ok_text, evidence=ev)


def na(rid: str, check: str, what: str, why: str) -> CheckResult:
    return CheckResult(rid, check, NOT_APPLICABLE, what, applicability=why)


def run_checks(r: Dict[str, Any], ttl: int, readings, rows, events, store) -> List[CheckResult]:
    exp = expected_states(r, readings, ttl)
    N = r["horizon_steps"]
    out: List[CheckResult] = []

    # ORACLE: TTL, stale data, silence ------------------------------------------------
    times = {c: [t for t, _ in readings[c]] for c in CLASSES}
    bad = []
    for row in rows:
        for c in CLASSES:
            i = bisect.bisect_right(times[c], row["t_min"]) - 1
            if i >= 0 and row["t_min"] - times[c][i] > ttl and row["classes"][c]["weight"] != 0:
                bad.append({"step": row["step"], "class": c, "age_min": row["t_min"] - times[c][i]})
    for rid in ("ORACLE-4.6-01", "ORACLE-9-01"):
        out.append(verdict(rid, "ttl_zero_weight", bad, f"every datum older than its TTL ({ttl} min) had weight 0",
                           "{n} class-steps kept a weight after the TTL expired", {"ttl_minutes": ttl}))
    bad = [{"step": row["step"], "used": row["admissible"], "admissible": e["admissible"], "S": row["S"], "expected_S": e["S"]}
           for row, e in zip(rows, exp)
           if not set(row["admissible"]) <= set(e["admissible"])
           or (row["S"] is None) != (e["S"] is None)
           or (row["S"] is not None and abs(row["S"] - e["S"]) > 1e-9)]
    out.append(verdict("ORACLE-9-02", "no_stale_in_state", bad,
                       "S(t) used only admissible data and had no value when no datum was admissible",
                       "{n} steps used stale data or substituted a value"))
    zero_steps = [e["step"] for e in exp if e["zero_weight"]]
    if zero_steps:
        bad = [s for s in zero_steps if rows[s]["ptl"]["confidence_state"] == SUFFICIENT]
        out.append(verdict("ORACLE-9-03", "silence_propagates", bad,
                           f"in all {len(zero_steps)} steps with a silent or stale class the output declared "
                           "DEGRADED_SIGNAL or INSUFFICIENT_DATA (H-FC-1)",
                           "{n} steps with a silent or stale class were reported as SUFFICIENT_DATA"))
    else:
        out.append(na("ORACLE-9-03", "silence_propagates", "propagation of silence or zero weight",
                      "no class was silent or stale in this experiment"))

    # ORACLE: divergence ---------------------------------------------------------------
    exp_open = [e["step"] for e in exp if e["opened"]]
    exp_close = [e["step"] for e in exp if e["closed"]]
    got_open = [e["step"] for e in events if e["type"] == "divergence_open"]
    got_close = [e["step"] for e in events if e["type"] == "divergence_resolved"]
    max_spread = max(e["spread"] for e in exp)
    out.append(CheckResult("ORACLE-11-01", "divergence_threshold", PASS if got_open == exp_open else FAIL,
                           (f"divergence flags raised exactly where the cross-class difference exceeded 7 % "
                            f"(steps {exp_open[:5]}; largest difference {max_spread:.1%})" if exp_open else
                            f"no difference above 7 % and no flag (largest difference {max_spread:.1%})")
                           if got_open == exp_open else
                           f"flags at steps {got_open[:5]}, expected at {exp_open[:5]}",
                           evidence={"expected_open": exp_open, "raised": got_open}))
    div_steps = [e["step"] for e in exp if e["divergence"]]
    actions = [e for e in events if e["type"] in ("transaction", "asset_order") and e["executed"]]
    asset_decisions = [e for e in events if (e["type"] == "asset_order" and e["executed"]) or e["type"] == "lift"]
    if div_steps:
        ds = set(div_steps)
        bad = [{"step": a["step"], "type": a["type"]} for a in actions if a["step"] in ds]
        out.append(verdict("ORACLE-11-02", "divergence_freeze", bad,
                           f"no state-based transaction during {len(div_steps)} steps of unresolved divergence",
                           "{n} state-based transactions executed during divergence"))
        # the arbitration window (ORACLE §11): opened by the divergence flag, closed by resolution or at the
        # 14-day maximum; its length is measured, not the length of the disagreement
        step = r["step_minutes"]
        limit = ARBITRATION_MINUTES          # compared in minutes, never rounded to the step grid (КТ4-GPT-01)
        opens = [e["step"] for e in events if e["type"] == "arbitration_open"]
        closes = [(e["step"], e["outcome"]) for e in events if e["type"] == "arbitration_closed"]
        spans, j = [], 0
        for a in opens:
            c = next((x for x in closes if x[0] >= a), None)
            spans.append((a, c[0] if c else r["horizon_steps"], c[1] if c else "open at the end of the horizon"))
        too_long = [{"opened": a, "minutes": (b - a) * step} for a, b, _ in spans if (b - a) * step > limit]
        out.append(verdict("ORACLE-11-03", "arbitration_window", too_long,
                           f"{len(spans)} arbitration windows, each closed within the 14-day maximum "
                           f"({', '.join(o for _, _, o in spans) or 'none'})",
                           "{n} arbitration windows longer than 14 days"))
        expired = [x for x in exp_runs_longer_than(div_steps, ARBITRATION_MINUTES // step)]
        if got_close != exp_close:
            out.append(CheckResult("ORACLE-11-04", "divergence_resolution", FAIL,
                                   f"divergence ended at steps {got_close[:5]}; admissible ends at {exp_close[:5]}",
                                   evidence={"expected": exp_close, "adapter": got_close}))
        elif expired:
            out.append(CheckResult("ORACLE-11-04", "divergence_resolution", UNKNOWN,
                                   f"{len(expired)} arbitration windows ended after 14 days without convergence or exclusion; "
                                   "ORACLE §11 defines no state after an unresolved window (F-018). Dependent "
                                   "transactions stay frozen while the data disagree (H-FC-7)"))
        elif exp_close:
            out.append(CheckResult("ORACLE-11-04", "divergence_resolution", PASS,
                                   "divergence ended only on convergence within 7 % or exclusion of the faulty class",
                                   evidence={"expected": exp_close, "adapter": got_close}))
        else:
            out.append(na("ORACLE-11-04", "divergence_resolution", "resolution of a divergence",
                          "the divergence was not resolved within the horizon"))
    else:
        out.append(na("ORACLE-11-02", "divergence_freeze", "freeze of state-based transactions",
                      "no divergence occurred in this experiment"))
        out.append(na("ORACLE-11-03", "arbitration_window", "arbitration window", "no divergence occurred"))
        out.append(na("ORACLE-11-04", "divergence_resolution", "resolution of a divergence", "no divergence occurred"))

    halt_steps = [e["step"] for e in exp if e["halt"]]
    if halt_steps:
        hs = set(halt_steps)
        created = [e["evaluation"] for e in events if e["type"] == "evaluation_created"]
        bad = [{"step": a["step"], "type": a["type"]} for a in actions if a["step"] in hs]
        bad += [{"erased": i} for i in created if i not in store]
        out.append(verdict("ORACLE-13-02", "halt_blocks_l2", bad,
                           f"no L2 execution during {len(halt_steps)} halt steps; all {len(created)} evaluation "
                           "records kept", "{n} L2 executions during the halt or erased records"))
    else:
        out.append(na("ORACLE-13-02", "halt_blocks_l2", "behaviour during a systemic halt",
                      "no systemic halt in this experiment"))

    text_ttl = TTL_TEXT[r["data_type"]]
    for rid in ("ORACLE-17-01", "ORACLE-17-02"):
        if TTL_REQUIREMENT[r["data_type"]] == rid:
            out.append(CheckResult(rid, "ttl_registry", PASS if ttl <= text_ttl else FAIL,
                                   f"TTL for {DATA_TYPES[r['data_type']]}: {ttl} min (§17 maximum {text_ttl} min)",
                                   evidence={"ttl_minutes": ttl, "text_maximum_minutes": text_ttl}))
        else:
            out.append(na(rid, "ttl_registry", "TTL maximum of other data types",
                          f"this experiment uses {DATA_TYPES[r['data_type']]}"))

    # EPISTEMIC-BOUNDARIES §5.x, §8 / ASSETS §8.3: metadata ---------------------------
    emissions = [e for e in events if e["type"] in ("transaction", "asset_order")]
    incomplete = [e for e in emissions if not complete(e["emitted"])]
    if incomplete:
        bad = [{"step": e["step"], "classified": e["classified"]} for e in incomplete if e["classified"] != INVALID]
        out.append(verdict("EB-5.x-02", "incomplete_is_invalid", bad,
                           f"all {len(incomplete)} outputs with incomplete metadata were classified INVALID",
                           "{n} outputs with incomplete metadata were not classified INVALID"))
        bad = [{"step": e["step"], "type": e["type"]} for e in incomplete if e["executed"]]
        out.append(verdict("EB-5.x-03", "incomplete_not_executed", bad,
                           f"none of {len(incomplete)} outputs with incomplete metadata was executed",
                           "{n} outputs with incomplete metadata were executed"))
        bad = [{"step": e["step"]} for e in incomplete if e["executed"] and complete(e["executed_output"])]
        out.append(verdict("EB-5.x-06", "no_downstream_repair", bad,
                           "missing metadata was not filled in downstream",
                           "{n} outputs had missing metadata filled in by the consumer and were executed"))
        no_scope = [e for e in incomplete if "scope_ref" not in e["emitted"]]
        bad = [{"step": e["step"]} for e in no_scope if e["executed"]]
        out.append(verdict("EB-8-02", "no_scope_no_enforcement", bad,
                           f"none of {len(no_scope)} outputs without scope_ref was enforced",
                           "{n} outputs without scope_ref were enforced"))
        bad = [{"step": e["step"]} for e in incomplete if e["type"] == "asset_order" and e["executed"]]
        out.append(verdict("ASSETS-8.3-07", "asset_order_requires_metadata", bad,
                           "asset control outputs without the full metadata set were not enforced",
                           "{n} asset control outputs without the full metadata set were enforced"))
    else:
        why = "every emitted output carried the full metadata set; the refusal path was not exercised"
        out.append(na("EB-5.x-02", "incomplete_is_invalid", "classification of incomplete outputs", why))
        out.append(na("EB-5.x-03", "incomplete_not_executed", "execution of incomplete outputs", why))
        out.append(na("EB-5.x-06", "no_downstream_repair", "downstream repair of metadata", why))
        out.append(na("EB-8-02", "no_scope_no_enforcement", "enforcement without scope_ref", why))
        out.append(na("ASSETS-8.3-07", "asset_order_requires_metadata", "asset outputs without metadata", why))
    orders = [e for e in emissions if e["type"] == "asset_order" and e["executed"]]
    if orders:
        bad = [{"step": e["step"]} for e in orders
               if not complete(e["executed_output"]) or e["executed_output"].get("revalidation_required") is not True
               or e["executed_output"].get("dispute_allowed") is not True]
        out.append(verdict("ASSETS-8.3-06", "asset_order_metadata", bad,
                           f"all {len(orders)} executed asset orders carried the six fields with "
                           "revalidation_required and dispute_allowed TRUE",
                           "{n} executed asset orders lacked fields or the TRUE flags"))
    else:
        out.append(na("ASSETS-8.3-06", "asset_order_metadata", "metadata of asset orders",
                      "no asset order was executed in this experiment"))

    # EPISTEMIC-TRANSITIONS ---------------------------------------------------------
    bad = [{"step": a["step"], "type": a["type"], "ptl": exp[a["step"]]["meta"]["validity_state"]}
           for a in actions if exp[a["step"]]["meta"]["validity_state"] != VALID]
    if actions:
        out.append(verdict("ETRANS-3-01", "operational_within_validity", bad,
                           f"all {len(actions)} executed actions happened while the upstream output was VALID",
                           "{n} actions executed while the upstream output was not VALID"))
    else:
        out.append(na("ETRANS-3-01", "operational_within_validity", "operation within validity",
                      "no action was executed in this experiment"))

    downgrade_steps = [k for k in range(1, N) if listed_downgrades(exp[k - 1]["meta"], exp[k]["meta"])]
    affected = [k for k in downgrade_steps if rows[k - 1]["mode"] == "ACTIVE"]
    if affected:
        bad1 = [k for k in affected if not rows[k]["revalidation_required"]]
        bad2 = [k for k in affected if rows[k]["mode"] not in ("SUSPENDED", "INACTIVE")]
        out.append(verdict("ETRANS-4.1-01", "revalidation_flag", bad1,
                           f"revalidation_required set at all {len(affected)} listed downgrades of an active chain",
                           "{n} listed downgrades left revalidation_required FALSE"))
        out.append(verdict("ETRANS-4.1-02", "suspension_on_downgrade", bad2,
                           f"dependent outputs suspended at all {len(affected)} listed downgrades",
                           "{n} listed downgrades did not suspend the dependent outputs"))
        out.append(verdict("ETRANS-3-02", "downgrade_propagates", sorted(set(bad1) | set(bad2)),
                           "every listed downgrade reached the asset control and the transactions",
                           "{n} downgrades did not propagate downstream"))
        resumes = sorted(e["step"] for e in events if e["type"] in ("resume", "end"))
        bad = []
        for k in affected:
            until = next((s for s in resumes if s >= k), N)
            bad += [{"downgrade": k, "order_step": a["step"]} for a in asset_decisions
                    if a["type"] == "asset_order" and k <= a["step"] < until]
        out.append(verdict("ETRANS-4.1-03", "no_escalation_after_downgrade", bad,
                           "no asset escalation between a downgrade and the recomputed re-entry",
                           "{n} escalations after a downgrade before re-entry"))
    else:
        why = "no listed downgrade happened while an enforcement output depended on the upstream output"
        for rid, chk in (("ETRANS-4.1-01", "revalidation_flag"), ("ETRANS-4.1-02", "suspension_on_downgrade"),
                         ("ETRANS-3-02", "downgrade_propagates"), ("ETRANS-4.1-03", "no_escalation_after_downgrade")):
            out.append(na(rid, chk, "reaction to an upstream downgrade", why))

    # uncertainty or dispute: from an upstream state other than VALID, or from a dispute,
    # until the next deterministic recomputation (or the end of the horizon)
    disputes = [e["step"] for e in events if e["type"] == "dispute"]
    recomputes = sorted(e["step"] for e in events if e["type"] == "recomputed")
    uncertain_set = set()
    for a, b in runs([e["step"] for e in exp if e["meta"]["validity_state"] != VALID]):
        uncertain_set |= set(range(a, next((s for s in recomputes if s > b), N)))
    for d in disputes:
        uncertain_set |= set(range(d, next((s for s in recomputes if s >= d), N)))
    engaged = [k for k in sorted(uncertain_set) if rows[k]["evaluation"] is not None]
    if engaged:
        us = set(engaged)
        bad = [{"step": a["step"]} for a in actions if a["type"] == "asset_order" and a["step"] in us]
        out.append(verdict("ETRANS-4.3-02", "no_escalation_in_uncertainty", bad,
                           f"no escalation during {len(engaged)} steps of uncertainty or dispute",
                           "{n} escalations during uncertainty or dispute"))
        bad = [{"step": a["step"]} for a in actions if a["type"] == "transaction" and a["step"] in us]
        for rid, chk in (("ETRANS-4.3-03", "no_penalty_accumulation"), ("FINANCE-11.2-03", "no_accumulation_in_status_quo")):
            out.append(verdict(rid, chk, bad, f"no penalty accrued during {len(engaged)} steps of uncertainty or dispute",
                               "{n} penalty units accrued during uncertainty or dispute"))
        bad = []
        for a, b in runs(engaged):
            before = rows[a - 1]["asset_level"] if a > 0 else 0
            bad += [{"step": k, "level": rows[k]["asset_level"], "before": before}
                    for k in range(a, b + 1) if rows[k]["asset_level"] != before]
        out.append(verdict("ETRANS-4.3-01", "status_quo_preserved", bad,
                           "the asset restriction stayed as it was throughout uncertainty or dispute",
                           "{n} steps changed the asset restriction during uncertainty or dispute"))
        bad = []
        for a, b in runs(engaged):
            inside = [x["step"] for x in actions if a <= x["step"] <= b]
            if inside:
                bad.append({"period": [a, b], "first_action": inside[0], "actions": len(inside)})
        out.append(verdict("ETRANS-4.3-04", "awaits_recomputation", bad,
                           "enforcement waited for a deterministic recomputation after every period of "
                           "uncertainty or dispute",
                           "{n} periods had enforcement before any recomputation"))
    else:
        why = "no uncertainty or dispute while an evaluation was in force"
        for rid, chk in (("ETRANS-4.3-01", "status_quo_preserved"), ("ETRANS-4.3-02", "no_escalation_in_uncertainty"),
                         ("ETRANS-4.3-03", "no_penalty_accumulation"), ("FINANCE-11.2-03", "no_accumulation_in_status_quo"),
                         ("ETRANS-4.3-04", "awaits_recomputation")):
            out.append(na(rid, chk, "behaviour during uncertainty or dispute", why))

    created_at = {e["evaluation"]: e["step"] for e in events if e["type"] == "evaluation_created"}
    resumes = [e for e in events if e["type"] == "resume"]
    suspends = [e["step"] for e in events if e["type"] == "suspend"]
    if resumes:
        bad1, bad2 = [], []
        for e in resumes:
            last_suspend = max((s for s in suspends if s <= e["step"]), default=-1)
            rec = store.get(e["evaluation"], {})
            c = created_at.get(e["evaluation"], -1)
            fresh = c >= last_suspend and c == e["step"]
            recomputed = rec.get("value") is not None and exp[c]["S"] is not None and abs(rec["value"] - exp[c]["S"]) < 1e-9 \
                if c >= 0 else False
            if not (fresh and complete(rec.get("metadata")) and rec["metadata"]["validity_state"] == VALID and recomputed):
                bad1.append({"resume": e["step"], "evaluation": e["evaluation"], "created": c})
            if c < last_suspend:
                bad2.append({"resume": e["step"], "evaluation": e["evaluation"], "created": c, "suspended": last_suspend})
        out.append(verdict("ETRANS-4.4-01", "reentry_new_output", bad1,
                           f"each of {len(resumes)} re-entries used a new VALID evaluation with full metadata, "
                           "recomputed from the inputs at that step",
                           "{n} re-entries without a new recomputed evaluation"))
        out.append(verdict("ETRANS-4.4-02", "no_auto_reactivation", bad2,
                           "no earlier evaluation was reactivated", "{n} re-entries reactivated an earlier evaluation"))
    else:
        why = "enforcement was never resumed in this experiment"
        out.append(na("ETRANS-4.4-01", "reentry_new_output", "re-entry of enforcement", why))
        out.append(na("ETRANS-4.4-02", "no_auto_reactivation", "reactivation of earlier outputs", why))

    # ETRANS §4.2 conditions: degradation, new admissible data (EB §7.1: a reading that arrives and changes S(t)),
    # loss of consistency; declared disputes are new admissible data too
    arrivals = {k for k in range(1, N) if exp[k]["S"] is not None and exp[k - 1]["S"] is not None
                and abs(exp[k]["S"] - exp[k - 1]["S"]) > 1e-9
                and any(bisect.bisect_right(times[c], k * r["step_minutes"]) - 1 >= 0
                        and times[c][bisect.bisect_right(times[c], k * r["step_minutes"]) - 1] == k * r["step_minutes"]
                        for c in exp[k]["admissible"])}
    triggers = sorted(set(downgrade_steps) | set(disputes) | arrivals |
                      {k for k in range(1, N) if exp[k - 1]["meta"]["consistency_state"] == CONSISTENT
                       and exp[k]["meta"]["consistency_state"] != CONSISTENT})
    if triggers:
        bad = []
        for a in actions:
            c = created_at.get(a["evaluation"], -1)
            hit = [t for t in triggers if c < t <= a["step"]]
            if hit:
                bad.append({"step": a["step"], "evaluation": a["evaluation"], "created": c, "trigger": hit[-1]})
        out.append(verdict("ETRANS-4.2-01", "no_persistence_on_past_valid", bad,
                           "no action relied on an evaluation older than the latest degradation, dispute or "
                           "loss of consistency", "{n} actions relied on an evaluation made before a later trigger"))
    else:
        out.append(na("ETRANS-4.2-01", "no_persistence_on_past_valid", "persistence on past VALID state",
                      "no degradation, dispute or loss of consistency occurred"))

    # EPISTEMIC-BOUNDARIES §7.2: disputes -----------------------------------------------
    if disputes:
        digests = {e["evaluation"]: e["digest"] for e in events if e["type"] == "evaluation_created"}
        disputed = [e["evaluation"] for e in events if e["type"] == "dispute"]
        bad = [i for i in disputed if sha256_text(canonical_json(store[i])) != digests[i]]
        out.append(verdict("EB-7.2-01", "dispute_preserves_original", bad,
                           "disputed evaluations are byte-identical to their records at creation",
                           "{n} disputed evaluations were changed in place"))
        done, new_ok, delta_ok, waiting = [], [], [], []
        for d, old in zip(disputes, disputed):
            rec_ev = next((e for e in events if e["type"] == "recomputed" and e["step"] >= d), None)
            if rec_ev is None:
                waiting.append(d)
                continue
            done.append(d)
            nid = rec_ev["evaluation"]
            if nid != old and nid in created_at and created_at[nid] > d:
                new_ok.append(d)
            if any(e["type"] == "delta" and e["old"] == old and e["new"] == nid for e in events):
                delta_ok.append(d)
        if not done:
            for rid, chk in (("EB-7.2-02", "dispute_new_evaluation"), ("EB-7.2-03", "dispute_recomputes"),
                             ("EB-7.2-04", "dispute_delta")):
                out.append(CheckResult(rid, chk, UNKNOWN, "recomputation still awaited at the end of the horizon",
                                       evidence={"disputes": waiting}))
        else:
            missing_new = [d for d in done if d not in new_ok]
            out.append(verdict("EB-7.2-02", "dispute_new_evaluation", missing_new,
                               f"each of {len(done)} disputes created a new evaluation event",
                               "{n} disputes produced no new evaluation event"))
            bad = []
            for d in new_ok:
                nid = next(e["evaluation"] for e in events if e["type"] == "recomputed" and e["step"] >= d)
                c = created_at[nid]
                if exp[c]["S"] is None or abs(store[nid]["value"] - exp[c]["S"]) > 1e-9:
                    bad.append({"dispute": d, "evaluation": nid})
            out.append(verdict("EB-7.2-03", "dispute_recomputes", bad + [{"dispute": d} for d in missing_new],
                               "recomputation used the admissible inputs at the time of recomputation",
                               "{n} disputes were not recomputed from updated inputs"))
            out.append(verdict("EB-7.2-04", "dispute_delta", [d for d in done if d not in delta_ok],
                               "a comparative delta was produced for every dispute",
                               "{n} disputes produced no comparative delta"))
    else:
        for rid, chk in (("EB-7.2-01", "dispute_preserves_original"), ("EB-7.2-02", "dispute_new_evaluation"),
                         ("EB-7.2-03", "dispute_recomputes"), ("EB-7.2-04", "dispute_delta")):
            out.append(na(rid, chk, "dispute processing", "no dispute in this experiment"))

    # ASSETS §2 ------------------------------------------------------------------------
    blocked = set(halt_steps) | set(div_steps)
    if blocked:
        bad = [{"step": a["step"], "type": a["type"]} for a in asset_decisions if a["step"] in blocked]
        out.append(verdict("ASSETS-2-02", "assets_invalid_in_halt_or_divergence", bad,
                           f"no asset decision during {len(blocked)} steps of halt or unresolved divergence",
                           "{n} asset decisions during halt or unresolved divergence"))
    else:
        out.append(na("ASSETS-2-02", "assets_invalid_in_halt_or_divergence", "asset decisions under halt or divergence",
                      "no systemic halt and no divergence in this experiment"))
    return out


IMPLEMENTS = {
    "ORACLE-4.6-01": ("ttl_zero_weight", "IMPLEMENTED", None),
    "ORACLE-9-01": ("ttl_zero_weight", "IMPLEMENTED", None),
    "ORACLE-9-02": ("no_stale_in_state", "PARTIAL", "S(t) is an equal-weight mean of admissible values (H-FC-2)."),
    "ORACLE-9-03": ("silence_propagates", "PARTIAL", "Uses the declared mapping H-FC-1 of zero-weight conditions to EB states."),
    "ORACLE-11-01": ("divergence_threshold", "PARTIAL", "The text does not define the difference of posteriors; point values are compared (H-FC-3)."),
    "ORACLE-11-02": ("divergence_freeze", "IMPLEMENTED", None),
    "ORACLE-11-03": ("arbitration_window", "IMPLEMENTED", None),
    "ORACLE-11-04": ("divergence_resolution", "PARTIAL", "Ends by convergence within 7 % or exclusion; staleness does not end it (H-FC-4); after an unresolved window the next state is undefined (F-018): UNKNOWN."),
    "ORACLE-13-02": ("halt_blocks_l2", "PARTIAL", "The halt is a scenario input; its triggers (confidence, coverage) are not computed."),
    "ORACLE-17-01": ("ttl_registry", "IMPLEMENTED", None),
    "ORACLE-17-02": ("ttl_registry", "IMPLEMENTED", None),
    "EB-5.x-02": ("incomplete_is_invalid", "IMPLEMENTED", None),
    "EB-5.x-03": ("incomplete_not_executed", "IMPLEMENTED", None),
    "EB-5.x-06": ("no_downstream_repair", "PARTIAL", "Checks that the consumer does not fill in missing fields; other repairs are not modelled."),
    "EB-8-02": ("no_scope_no_enforcement", "IMPLEMENTED", None),
    "EB-7.2-01": ("dispute_preserves_original", "IMPLEMENTED", None),
    "EB-7.2-02": ("dispute_new_evaluation", "IMPLEMENTED", None),
    "EB-7.2-03": ("dispute_recomputes", "PARTIAL", "Admissibility of the new inputs is the TTL rule only."),
    "EB-7.2-04": ("dispute_delta", "IMPLEMENTED", None),
    "ETRANS-3-01": ("operational_within_validity", "PARTIAL", "Validity of the upstream output under H-FC-1."),
    "ETRANS-3-02": ("downgrade_propagates", "PARTIAL", "One chain: PTL output → evaluation → asset control and transactions."),
    "ETRANS-4.1-01": ("revalidation_flag", "IMPLEMENTED", None),
    "ETRANS-4.1-02": ("suspension_on_downgrade", "IMPLEMENTED", None),
    "ETRANS-4.1-03": ("no_escalation_after_downgrade", "IMPLEMENTED", None),
    "ETRANS-4.2-01": ("no_persistence_on_past_valid", "PARTIAL", "New admissible data = a reading that arrives and changes S(t), or a declared dispute (H-FC-5)."),
    "ETRANS-4.3-01": ("status_quo_preserved", "IMPLEMENTED", None),
    "ETRANS-4.3-02": ("no_escalation_in_uncertainty", "IMPLEMENTED", None),
    "ETRANS-4.3-03": ("no_penalty_accumulation", "IMPLEMENTED", None),
    "ETRANS-4.3-04": ("awaits_recomputation", "IMPLEMENTED", None),
    "ETRANS-4.4-01": ("reentry_new_output", "IMPLEMENTED", None),
    "ETRANS-4.4-02": ("no_auto_reactivation", "IMPLEMENTED", None),
    "ASSETS-2-02": ("assets_invalid_in_halt_or_divergence", "IMPLEMENTED", None),
    "ASSETS-8.3-06": ("asset_order_metadata", "PARTIAL", "Inheritance from a Justice output is replaced by the evaluation of this chain."),
    "ASSETS-8.3-07": ("asset_order_requires_metadata", "IMPLEMENTED", None),
    "FINANCE-11.2-03": ("no_accumulation_in_status_quo", "PARTIAL", "Status quo of an epistemic dispute; Justice-domain disputes are not modelled."),
}

STEP_LABEL = {"en": "step", "ru": "шаг"}


def _window(default=None):
    return {"type": "pair", "min": 0, "max": 10 ** 6, "default": default or [0, 0], "unit": "step", "source": "user"}


class FailureChainModule(LabModule):
    id = "failure_chain"
    version = "1.2.0"
    title = {"en": "Stale and contradictory data (failure chain)",
             "ru": "Устаревшие и противоречивые данные (цепочка отказа)"}
    summary = {"en": "Sensors go silent or disagree: do dependent asset restrictions and penalties stop, wait "
                     "for a new evaluation and keep the old records?",
               "ru": "Датчики замолкают или расходятся: останавливаются ли зависимые ограничения имущества и "
                     "штрафы, ждут ли новой оценки и сохраняют ли старые записи?"}
    protocols = ["DKP-0-ORACLE-001", "DKP-1-EPISTEMIC-BOUNDARIES-001", "DKP-4-EPISTEMIC-TRANSITIONS-001",
                 "DKP-2-ASSETS-001", "DKP-2-FINANCE-001"]
    example_order = ["divergence_resolved", "divergence_faulty_adapter", "stale_ground", "dispute_recompute",
                     "incomplete_order", "systemic_halt", "value_drop", "value_drop_in_sync", "long_divergence", "fire_ttl",
                     "all_faults"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_failure_chain_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-FC-1", "source": "hypothesis", "text": {
            "en": "PTL conditions → EB states: no admissible class = INSUFFICIENT_DATA; some class stale = DEGRADED_SIGNAL; "
                  "open divergence = ORACLE_CONFLICT; fewer than 2 admissible classes = UNRESOLVED; halt, conflict or "
                  "insufficient data = INVALID; degraded or unresolved = CONDITIONAL.",
            "ru": "Состояния PTL → состояния EB: нет допустимых классов = INSUFFICIENT_DATA; часть классов устарела = "
                  "DEGRADED_SIGNAL; открытое расхождение = ORACLE_CONFLICT; меньше двух классов = UNRESOLVED; остановка, "
                  "конфликт или нехватка данных = INVALID; деградация или неразрешённость = CONDITIONAL."}},
        {"id": "H-FC-2", "source": "hypothesis", "text": {
            "en": "S(t) is the equal-weight mean of admissible class values (stand-in for the Bayesian ensemble of ORACLE §10).",
            "ru": "S(t) — среднее допустимых значений классов с равными весами (замена байесовского ансамбля ORACLE §10)."}},
        {"id": "H-FC-3", "source": "hypothesis", "text": {
            "en": "Divergence metric: the largest pairwise |a−b|/max(|a|,|b|) between the latest admissible values of "
                  "different classes; values taken at different times are not aligned.",
            "ru": "Мера расхождения: наибольшее попарное |a−b|/max(|a|,|b|) между последними допустимыми значениями разных "
                  "классов; значения разного времени не выравниваются."}},
        {"id": "H-FC-4", "source": "hypothesis", "text": {
            "en": "A divergence ends only by convergence within 7 % or by exclusion of the faulty class; one side "
                  "going stale does not end it.",
            "ru": "Расхождение заканчивается только сближением в пределах 7 % или исключением неисправного класса; "
                  "устаревание одной стороны его не заканчивает."}},
        {"id": "H-FC-5", "source": "text", "text": {
            "en": "New admissible data trigger re-evaluation (EB §7.1, ETRANS §4.2, JUSTICE §11): when a reading arrives "
                  "and changes S(t), the dependent evaluation is recomputed at once (a recomputation that changes nothing "
                  "confirms the current evaluation). Declared disputes, the first VALID state and re-entry after a "
                  "downgrade also recompute. The immediacy of system-triggered recomputation is the lab's choice.",
            "ru": "Новые допустимые данные запускают переоценку (EB §7.1, ETRANS §4.2, JUSTICE §11): когда приходит "
                  "показание и меняет S(t), зависимая оценка сразу пересчитывается (пересчёт без изменения подтверждает "
                  "текущую оценку). Объявленный спор, первое состояние VALID и возврат после понижения тоже пересчитывают. "
                  "Немедленность системного пересчёта — выбор лаборатории."}},
        {"id": "H-FC-5-ALT", "source": "alternative", "text": {
            "en": "Readings for comparison: 'material_change' recomputes only when S(t) moves beyond a declared tolerance, "
                  "after the status quo delay; 'declared_events' is the lab's former reading (routine readings are not new "
                  "admissible data). It contradicts EB §7.1 and ETRANS §4.2 and is kept only to reproduce F-001, which was "
                  "an implementation error of the lab.",
            "ru": "Прочтения для сравнения: 'material_change' — пересчёт только при изменении S(t) сверх допуска, после "
                  "задержки статус-кво; 'declared_events' — прежнее прочтение лаборатории (обычные показания — не новые "
                  "допустимые данные). Оно противоречит EB §7.1 и ETRANS §4.2 и сохранено только для воспроизведения F-001 — "
                  "ошибки реализации лаборатории."}},
        {"id": "H-FC-6", "source": "hypothesis", "text": {
            "en": "Enforcement stand-in: while the evaluated value exceeds the limit, an asset restriction applies "
                  "(level +1 every N active steps) and a penalty accrues 1 model unit per active step. Not money.",
            "ru": "Модель принуждения: пока оценка выше предела, действует ограничение имущества (уровень +1 каждые "
                  "N активных шагов) и начисляется 1 модельная единица штрафа за шаг. Это не деньги."}},
        {"id": "H-FC-7", "source": "hypothesis", "text": {
            "en": "Arbitration window (ORACLE §11): opened by the divergence flag, closed by convergence or exclusion, and at the "
                  "latest when 14 days have passed, even if the data still disagree. After an unresolved window the next state "
                  "is undefined (F-018); dependent transactions stay frozen while the data disagree (status quo, ETRANS §4.3).",
            "ru": "Окно арбитража (ORACLE §11): открывается флагом расхождения, закрывается сходимостью или исключением, и не "
                  "позже чем через 14 дней, даже если данные ещё расходятся. Состояние после неразрешённого окна не определено "
                  "(F-018); зависимые транзакции остаются замороженными, пока данные расходятся (status quo, ETRANS §4.3)."}},
    ]
    inputs = {
        "data_type": {"type": "enum", "values": list(DATA_TYPES), "default": "surface_temperature", "source": "text",
                      "label": {"en": "Data type (TTL from ORACLE §17)", "ru": "Тип данных (TTL из ORACLE §17)"}},
        "ttl_minutes": {"type": "int", "min": -1, "max": 10 ** 6, "default": -1, "unit": "min", "source": "text",
                        "label": {"en": "TTL (-1: the §17 maximum)", "ru": "TTL (-1: максимум §17)"}},
        "step_minutes": {"type": "int", "min": 1, "max": 1440, "default": 60, "unit": "min", "source": "user",
                         "label": {"en": "Step length", "ru": "Длина шага"}},
        "horizon_steps": {"type": "int", "min": 2, "max": 5000, "default": 240, "unit": "step", "source": "user",
                          "label": {"en": "Number of steps", "ru": "Число шагов"}},
        "ground_interval_minutes": {"type": "int", "min": 1, "max": 10 ** 6, "default": 60, "unit": "min", "source": "user",
                                    "label": {"en": "Ground sensors: reading every", "ru": "Наземные датчики: показание каждые"}},
        "orbital_interval_minutes": {"type": "int", "min": 1, "max": 10 ** 6, "default": 360, "unit": "min", "source": "user",
                                     "label": {"en": "Orbital sensing: reading every", "ru": "Спутники: показание каждые"}},
        "autonomous_interval_minutes": {"type": "int", "min": 1, "max": 10 ** 6, "default": 120, "unit": "min",
                                        "source": "user", "label": {"en": "Autonomous platforms: reading every",
                                                                    "ru": "Автономные платформы: показание каждые"}},
        "true_value": {"type": "number", "min": -10 ** 9, "max": 10 ** 9, "default": 100, "source": "user",
                       "label": {"en": "True value (model unit)", "ru": "Истинное значение (модельная единица)"}},
        "value_change_at_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": -1, "unit": "step", "source": "user",
                                 "label": {"en": "Value changes at step (-1: never)", "ru": "Значение меняется на шаге (-1: никогда)"}},
        "changed_value": {"type": "number", "min": -10 ** 9, "max": 10 ** 9, "default": 80, "source": "user",
                          "label": {"en": "New true value", "ru": "Новое истинное значение"}},
        "faulty_class": {"type": "enum", "values": list(CLASSES), "default": "orbital", "source": "user",
                         "label": {"en": "Faulty class", "ru": "Неисправный класс"}},
        "bias_percent": {"type": "number", "min": -100, "max": 1000, "default": 0, "unit": "%", "source": "user",
                         "label": {"en": "Bias of the faulty class", "ru": "Смещение неисправного класса"}},
        "bias_window": {**_window(), "label": {"en": "Bias from/to step", "ru": "Смещение с/до шага"}},
        "exclude_faulty_at_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": -1, "unit": "step", "source": "user",
                                   "label": {"en": "Faulty class excluded at step (-1: never)",
                                             "ru": "Неисправный класс исключён на шаге (-1: никогда)"}},
        "silent_class": {"type": "enum", "values": ["none"] + list(CLASSES), "default": "none", "source": "user",
                         "label": {"en": "Silent class", "ru": "Молчащий класс"}},
        "silent_window": {**_window(), "label": {"en": "Silent from/to step", "ru": "Молчит с/до шага"}},
        "halt_window": {**_window(), "label": {"en": "Systemic halt from/to step (ORACLE §13)",
                                               "ru": "Системная остановка с/до шага (ORACLE §13)"}},
        "dispute_at_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": -1, "unit": "step", "source": "user",
                            "label": {"en": "Dispute filed at step (-1: none)", "ru": "Спор подан на шаге (-1: нет)"}},
        "incomplete_order_at_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": -1, "unit": "step",
                                     "source": "user",
                                     "label": {"en": "Asset order without scope_ref emitted at step (-1: none)",
                                               "ru": "Приказ без scope_ref выпущен на шаге (-1: нет)"}},
        "recompute_delay_steps": {"type": "int", "min": 0, "max": 1000, "default": 2, "unit": "step",
                                  "source": "hypothesis",
                                  "label": {"en": "Recomputation takes", "ru": "Пересчёт занимает"}},
        "reevaluation_policy": {"type": "enum", "values": ["new_admissible_data", "material_change", "declared_events"],
                                "default": "new_admissible_data", "source": "text",
                                "label": {"en": "When the evaluation is recomputed (H-FC-5; alternatives H-FC-5-ALT)",
                                          "ru": "Когда пересчитывается оценка (H-FC-5; альтернативы H-FC-5-ALT)"}},
        "material_change_percent": {"type": "number", "min": 0, "max": 1000, "default": 5, "unit": "%",
                                    "source": "alternative",
                                    "label": {"en": "Material change of S(t) (for 'material_change')",
                                              "ru": "Существенное изменение S(t) (для 'material_change')"}},
        "limit": {"type": "number", "min": -10 ** 9, "max": 10 ** 9, "default": 90, "source": "hypothesis",
                  "label": {"en": "Enforcement above (H-FC-6)", "ru": "Принуждение выше (H-FC-6)"}},
        "escalation_every_steps": {"type": "int", "min": 1, "max": 10 ** 6, "default": 24, "unit": "step",
                                   "source": "hypothesis",
                                   "label": {"en": "Restriction level +1 every (H-FC-6)", "ru": "Уровень ограничения +1 каждые (H-FC-6)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS),
                   "items": {"type": "enum", "values": list(FAULTS)}, "default": [], "source": "user",
                   "label": {"en": "Deliberate adapter faults (counterexamples)",
                             "ru": "Намеренные ошибки адаптера (контрпримеры)"},
                   "help": {"en": "Each fault switches one rule off: " + "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        for key in ("bias_window", "silent_window", "halt_window"):
            if not all(float(x).is_integer() for x in r[key]):
                p.append(f"input.{key}: steps must be whole numbers")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        for key in ("dispute_at_step", "value_change_at_step", "exclude_faulty_at_step", "incomplete_order_at_step"):
            if r[key] >= r["horizon_steps"]:
                p.append(f"input.{key}: beyond the horizon ({r['horizon_steps']} steps)")
        total = r["horizon_steps"] * r["step_minutes"]
        n = sum(-(-total // r[f"{c}_interval_minutes"]) for c in CLASSES)
        if n > MAX_READINGS:
            p.append(f"input: {n} readings exceed {MAX_READINGS}; use longer intervals or fewer steps")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        ttl = TTL_TEXT[r["data_type"]] if r["ttl_minutes"] < 0 else r["ttl_minutes"]
        readings = generate(r)
        self.report_progress(0.2, "adapter")
        rows, events, store = run_adapter(r, readings, ttl)
        self.report_progress(0.6, "checks")
        checks = run_checks(r, ttl, readings, rows, events, store)
        modes = [row["mode"] for row in rows]
        last = rows[-1]
        # diagnostic, not a check: enforcement while the current S(t) is on the other side of the
        # limit than the evaluation it relies on (MODEL_GAPS §11, finding F-001)
        contradicted = contradicted_steps(r, rows, store)
        outputs = {
            "ttl_minutes": ttl,
            "ttl_text_maximum_minutes": TTL_TEXT[r["data_type"]],
            "readings": {c: len(readings[c]) for c in CLASSES},
            "observation_log": {"time_unit": "minute", "messages": sum(len(v) for v in readings.values()),
                                "digest": observation_log(readings).digest()},
            "events": [e for e in events if e["type"] != "transaction"],
            "evaluations": [store[i] for i in sorted(store)],
            "totals": {
                "penalty_units": last["penalty_units"],
                "max_asset_level": max(row["asset_level"] for row in rows),
                "steps_active": modes.count("ACTIVE"),
                "steps_suspended": modes.count("SUSPENDED"),
                "steps_divergence": sum(1 for row in rows if row["divergence_open"]),
                "evaluations": len(store),
                "final_mode": last["mode"],
                "steps_enforced_against_current_state": contradicted,
            },
        }
        records = [{k: v for k, v in row.items()} for row in rows]
        return ModuleResult(outputs=outputs, checks=checks, explain=self.explain(r, ttl, events, rows, store),
                            records=records)

    def explain(self, r, ttl, events, rows, store) -> List[Dict[str, str]]:
        dt = DATA_TYPES[r["data_type"]]
        out = [{"en": f"{dt}: TTL {ttl} min (ORACLE §17 maximum {TTL_TEXT[r['data_type']]} min); "
                      f"{r['horizon_steps']} steps of {r['step_minutes']} min.",
                "ru": f"{dt}: TTL {ttl} мин (максимум ORACLE §17 — {TTL_TEXT[r['data_type']]} мин); "
                      f"{r['horizon_steps']} шагов по {r['step_minutes']} мин."}]
        text = {
            "divergence_open": ("classes disagree by {spread:.1%} (> 7 %): divergence flag",
                                "классы расходятся на {spread:.1%} (> 7 %): флаг расхождения"),
            "divergence_resolved": ("divergence resolved by {by}", "расхождение снято ({by})"),
            "suspend": ("dependent outputs suspended ({reason}); revalidation required",
                        "зависимые решения приостановлены ({reason}); нужна перепроверка"),
            "dispute": ("dispute filed against {evaluation}", "подан спор по {evaluation}"),
            "evaluation_created": ("new evaluation {evaluation}: value {value}", "новая оценка {evaluation}: значение {value}"),
            "delta": ("comparative delta {old} → {new}: {delta:+g}", "сравнение {old} → {new}: {delta:+g}"),
            "activate": ("enforcement starts on {evaluation}", "принуждение начинается по {evaluation}"),
            "resume": ("enforcement resumes on {evaluation}", "принуждение возобновлено по {evaluation}"),
            "end": ("evaluation {evaluation} is below the limit: restriction lifted",
                    "оценка {evaluation} ниже предела: ограничение снято"),
        }
        shown = 0
        for e in events:
            if e["type"] in text and shown < 12:
                en, ru = text[e["type"]]
                out.append({"en": f"Step {e['step']}: " + en.format(**e), "ru": f"Шаг {e['step']}: " + ru.format(**e)})
                shown += 1
        last = rows[-1]
        out.append({"en": f"End: mode {last['mode']}; {last['penalty_units']} penalty units (model); asset restriction "
                          f"level {last['asset_level']}; evaluation records: {len(store)}.",
                    "ru": f"Итог: режим {last['mode']}; {last['penalty_units']} единиц штрафа (модель); уровень "
                          f"ограничения {last['asset_level']}; записей оценок: {len(store)}."})
        if contradicted_steps(r, rows, store):
            n = contradicted_steps(r, rows, store)
            out.append({"en": f"Enforcement acted in {n} steps while the current S(t) was on the other side of the "
                              "limit than the evaluation it relies on. No provision is reported as violated: see "
                              "MODEL_GAPS §11, finding F-001.",
                        "ru": f"Принуждение действовало {n} шагов, когда текущее S(t) было по другую сторону предела, "
                              "чем оценка, на которой оно основано. Нарушение положений не фиксируется: см. "
                              "MODEL_GAPS §11, находка F-001."})
        if r["faults"]:
            out.append({"en": "Deliberate adapter faults: " + ", ".join(r["faults"]) + ". FAIL marks what the checks caught.",
                        "ru": "Намеренные ошибки адаптера: " + ", ".join(r["faults"]) + ". FAIL — то, что поймали проверки."})
        return out

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        t = outputs["totals"]
        return {"penalty_units": t["penalty_units"], "max_asset_level": t["max_asset_level"],
                "steps_suspended": t["steps_suspended"], "steps_divergence": t["steps_divergence"],
                "evaluations": t["evaluations"], "final_mode": t["final_mode"],
                "steps_enforced_against_current_state": t["steps_enforced_against_current_state"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        div = {"bias_percent": -12, "bias_window": [24, 240], "exclude_faulty_at_step": 72}
        return {
            "divergence_resolved": dict(div),
            "divergence_faulty_adapter": {**div, "faults": ["auto_reactivate", "accrue_during_suspension",
                                                             "escalate_during_suspension"]},
            "stale_ground": {"silent_class": "ground", "silent_window": [48, 144]},
            "dispute_recompute": {"dispute_at_step": 60},
            "incomplete_order": {"incomplete_order_at_step": 30},
            "systemic_halt": {"halt_window": [40, 60]},
            "value_drop": {"value_change_at_step": 50},
            "value_drop_in_sync": {"value_change_at_step": 48},
            "long_divergence": {"bias_percent": -12, "bias_window": [24, 600], "horizon_steps": 600},
            # review КТ4-GPT-01: 14 days = 20160 min falls between two 1000-minute steps
            "coarse_grid_divergence": {"step_minutes": 1000, "horizon_steps": 30, "ground_interval_minutes": 1000,
                                       "orbital_interval_minutes": 1000, "autonomous_interval_minutes": 1000,
                                       "bias_percent": -12, "bias_window": [1, 30]},
            "fire_ttl": {"data_type": "active_fire", "step_minutes": 5, "horizon_steps": 288,
                         "ground_interval_minutes": 5, "orbital_interval_minutes": 90, "autonomous_interval_minutes": 10},
            "all_faults": {**div, "dispute_at_step": 120, "incomplete_order_at_step": 100, "silent_class": "ground",
                           "silent_window": [150, 200], "faults": list(FAULTS)},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "fractional_window": {"bias_window": [1.5, 3]},
            "unknown_fault": {"faults": ["skip_everything"]},
            "dispute_beyond_horizon": {"dispute_at_step": 240},
            "too_many_readings": {"horizon_steps": 5000, "step_minutes": 1440, "ground_interval_minutes": 1},
        }
