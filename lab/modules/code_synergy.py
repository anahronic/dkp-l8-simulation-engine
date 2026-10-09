"""
CODE OF PLANETARY SYNERGY module — security and planetary safeguards of the Code.

Code of Planetary Synergy: Snap Protocol (§1.4), Peace Staking (§7), the Kill Switch Law (§8) and
Appendix A — the Main Equation and B_min (A.1), the parameter governance invariant (A.1a), the
Physical Truth Layer stack (A.2), the Pre-Bootstrap Shield and the Dead Man Switch (A.3), Mercy (A.4),
the startup cluster and the connection of new territories (A.5), the ownership caps (A.6) and the
Genesis Block parameters.  Cross-checks: DKP-0-ORACLE-001 §3 (human input), DKP-6-INTEGRATION-001 §5.2
(no kill switches in Phase 1), DKP-7-SCOPE-001 §3 (S3), DKP-8-AUDIT-001 §11 (audit during Mercy).

Time unit: day.  B(t) is the weighted ensemble of the three PTL level readings; the Bayesian ensemble
of Level 3 is not specified (H-CS-2).  W, E and T of the Main Equation have no measurement in the
corpus: they are declared scenario values (source missing).  The lab takes the Code's numbers as
written; the readings it has to choose are declared hypotheses, and states the text leaves open are
UNKNOWN (F-018, F-027 … F-032).
"""

from __future__ import annotations

import json
import os
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError

# Constants written in the Code (quoted in IMPLEMENTS notes and in lab/registry/verifications.json).
B_MIN = 0.68                      # A.1 "B_min = 0.68 - Hard threshold"
ALPHA = 2.83                      # A.1 "α = 2.83"
K_RANGE = (0.94, 1.06)            # A.1 "k = 0.94...1.06"
FAILURE_DAYS = 180                # A.1a "Violation for more than 180 consecutive days"
W_L0 = (0.65, 0.75)               # A.2 "Level 0 — Space (Weight 65–75%)"
W_L1 = (0.15, 0.25)               # A.2 "Level 1 ... (Weight 15–25%)"
W_L2_MAX = 0.10                   # A.2 "Level 2 ... (Weight ≤ 10%)"
DIVERGENCE = 0.07                 # A.2 "Divergence > 7%"
ARBITRATION_STAKE = 500e6         # A.2 "with a $500M stake"
ARBITRATION_DAYS = 14             # A.2 "(max 14 days)"
VALIDATOR_STAKE = (10e6, 100e6)   # A.2 "Stake for lying: $10–100M"
SHIELD_GDP = 0.18                 # A.3 "Until the network reaches 18% of World GDP"
MIN_BLOCS = 5                     # A.3 "at least 5 different geopolitical blocks"
NODE_ENERGY = 800                 # A.3 "≥ 800 MWh/year"
ENERGY_TYPES = ("geothermal", "smr", "hydrogen_bromine_orbital", "combination")
DEAD_MAN_MIN = 0.5                # A.3 "≥ 50% of all Peace Stakes globally"
MERCY_DAYS = 180                  # A.4 "suspended for 180 days"
MERCY_THRESHOLDS = {"eruption": 6, "asteroid": 200, "pandemic": 15}   # A.4 "> VEI-6", "> 200 m", "> 15%"
COUNCIL_SIZE, COUNCIL_POOL, COUNCIL_TRUST = 9, 1000, 0.97              # A.4 "9 people, ... 1000 scientists with EigenTrust > 0.97"
STARTUP = ("zanzibar", "prospera", "neom", "abudhabi", "tallinn", "kigali")   # A.5 items 1-6
REFERENDUM = 0.67                 # A.5 "a referendum of 67% of the adult population"
CAP_L0, CAP_GEO = 0.007, 0.02     # A.6 "0.7% of Level 0 satellites", "2% of geothermal wells or power units"
BAN_YEARS = 20                    # A.6 "20-year ban"
SNAP_DROP = 0.10                  # §1.4 "more than 10% per month"
WRITE_OFF = 10                    # §8.2 "10 times the damage caused"
GENESIS = {"k": 1.0, "alpha": 2.83, "B_min": 0.68, "B_current_at_genesis": 0.7104,
           "previous_hash": "0x" + "0" * 64}
GENESIS_BUFFER = 0.0304           # Explanatory note "Leaves a buffer of only 0.0304"
_SNAP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "corpus", "world-aad3e86", "Dikenocracy")
HEADER = ("block_height", "timestamp", "previous_hash", "consensus_protocol", "difficulty_target", "nonce")


def genesis_spec() -> Tuple[Dict[str, Any], str, str]:
    """The Genesis Block #0 specification as printed in the pinned Code (comments removed), the Code text, the Glossary."""
    with open(os.path.join(_SNAP, "CODE-OF-PLANETARY-SYNERGY.md"), encoding="utf-8") as f:
        code = f.read()
    with open(os.path.join(_SNAP, "Dikenocracy Glossary.md"), encoding="utf-8") as f:
        glossary = f.read()
    m = re.search(r"#### Genesis Block \\#0 \(Technical Specification\).*?```[a-z]*\s*\n(.*?)```", code, re.S)
    if not m:
        raise RuntimeError("Genesis Block #0 specification not found in the pinned Code")
    return json.loads(re.sub(r"[ \t]+//[^\n]*", "", m.group(1))), code, glossary

CHANNELS = ("upgrade", "on_chain", "operational", "financial", "crisis", "enforcement")
COUNCIL_ACTIONS = {"severity_reduction": None, "expand_applicability": "CODEX-A.4-04", "override_s2_s3": "CODEX-A.4-05",
                   "create_authority": "CODEX-A.4-06", "extend_jurisdiction": "CODEX-A.4-08"}
EARLY_PHASES = ("phase_0", "phase_1")
BUNDLE_STATES = ["none", "valid", "expired", "invalid_signature", "other_model"]   # only "valid" lifts ORACLE §12 (F-036)

FAULTS = {
    "ignore_b_min": "the Kill Switches do not activate when B(t) < B_min",
    "altered_genesis_header": "block #0 is created with another difficulty target than specified",
    "edit_genesis_message": "requests to edit the Genesis Block's message and anchors are accepted",
    "kill_switch_during_mercy": "Kill Switches stay in force during Mercy",
    "accept_on_chain_tuning": "an on-chain change of an Equation parameter is accepted",
    "accept_protocol_tuning": "an operational, financial, crisis or enforcement protocol changes a parameter",
    "accept_unsimulated_upgrade": "an UPGRADE without prior simulation changes a parameter",
    "early_system_failure": "System Failure is declared after exactly 180 days of violation",
    "accept_external_feed": "data from outside the four-layer stack is accepted",
    "accept_late_hash": "drone data whose hash was uploaded after the drone returned is accepted",
    "no_arbitration": "a divergence above 7% opens no arbitration",
    "count_unconfirmed_nodes": "nodes not confirmed by PTL Levels 0-1 are counted for the Shield",
    "dead_man_partial": "the Dead Man Switch burns 40% of the Peace Stakes",
    "ineligible_member": "a scientist with EigenTrust 0.95 sits on the Council of Crisis Mercy",
    "execute_inadmissible": "the Council's actions are executed whatever their type and time",
    "connect_without_referendum": "a territory connects by a legislative act",
    "miss_indirect_ownership": "ownership caps count direct holdings only",
    "lenient_cap_violation": "a cap violator keeps the right to participate",
    "smooth_during_snap": "smoothing stays on after a drop of more than 10% per month",
    "flat_stake": "every state deposits the same stake",
    "dividends_to_aggressor": "dividends keep accruing to an aggressor",
    "no_slashing": "an aggressor's stake is not burned",
    "no_disconnect": "an aggressor stays connected",
    "write_off_damage_only": "the write-off equals the damage instead of 10 times the damage",
    "kill_switch_in_phase_1": "a Kill Switch is applied to a territory in integration Phase 0 or 1",
    "audit_gap_in_mercy": "audit logging is suspended during Mercy",
}


def _seg(segs: List[Dict[str, Any]], d: int) -> Dict[str, Any]:
    cur = segs[0]
    for s in segs:
        if s["from_day"] <= d:
            cur = s
        else:
            break
    return cur


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("day", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, d, value, prov=()):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{d:05d}-{n['i']:05d}", kind=kind, source=source, arrived_at=d,
                                  decided_at=d if kind in ("decision", "action") else None, value=value,
                                  provenance=tuple(prov), order=order[kind]))

    days, w = r["days"], r["level_weights"]
    spec = genesis_spec()[0]
    header = {k: spec[k] for k in HEADER}
    if "altered_genesis_header" in faults:
        header["difficulty_target"] = "0x0000ffff" + "f" * 56
    rec = {"header": header, "physical_anchors": dict(spec["physical_anchors"]), "immutable_message": spec["immutable_message"]}
    for q in r["genesis_change_requests"]:
        ok = "edit_genesis_message" in faults
        put("decision", "GENESIS", 0, {"genesis_change": q, "accepted": ok,
                                       "reason": None if ok else "the Genesis Block is an immutable reference point (Code, Glossary)"})
        if ok and q == "immutable_message":
            rec["immutable_message"] = rec["immutable_message"].replace("faster and cleaner", "together")
        if ok and q == "physical_anchors":
            rec["physical_anchors"]["mauna_loa_co2_ppm"] = 420.0
    put("notice", "GENESIS", 0, {"genesis": dict(r["genesis"]), "block": rec})
    # A.2 stack: weights, sources, drones, validators
    put("evaluation", "PTL", 0, {"weights": dict(w), "coverage_l0": r["l0_coverage"]})
    for f in r["external_feeds"]:
        put("decision", "PTL", 0, {"feed": f, "accepted": "accept_external_feed" in faults,
                                   "reason": "outside the four-layer stack (A.2)"})
    for fl in r["drone_uploads"]:
        ok = fl["upload_min"] < fl["return_min"] or "accept_late_hash" in faults
        put("decision", "PTL", 0, {"drone": fl["flight"], "accepted": ok, "upload_min": fl["upload_min"],
                                   "return_min": fl["return_min"]})
    for i, s in enumerate(r["validator_stakes"]):
        put("decision", "PTL", 0, {"validator": i, "stake": s,
                                   "admitted": VALIDATOR_STAKE[0] <= s <= VALIDATOR_STAKE[1]})
    # Peace Stakes (§7.1)
    regions = {g["id"]: dict(g) for g in r["regions"]}
    mean_gdp = sum(g["gdp"] for g in r["regions"]) / len(r["regions"])
    for g in regions.values():
        g["stake"] = r["stake_rate"] * (mean_gdp if "flat_stake" in faults else g["gdp"])
        g["stake0"] = g["stake"]
        g["dividends"], g["written_off"], g["aggressor_since"], g["disconnected"] = 0.0, 0.0, None, False
        put("action", "ESCROW", 0, {"region": g["id"], "stake_deposited": g["stake"], "gdp": g["gdp"], "phase": g["phase"]})
    # A.6 ownership caps
    own = {o["holder"]: o for o in r["ownership"]}

    def eff(h, key, seen=()):
        o = own[h]
        v = o[key]
        if "miss_indirect_ownership" not in faults:
            for x in o["holds"]:
                v += x["share"] * eff(x["entity"], key, seen + (h,))
        return v
    for h in sorted(own):
        l0, geo = eff(h, "l0_share"), eff(h, "geo_share")
        if l0 > CAP_L0 or geo > CAP_GEO:
            put("action", "NETWORK", 0, {"cap_violation": h, "l0": round(l0, 9), "geo": round(geo, 9),
                                         "stakes_burned": own[h]["stake"],
                                         "ban_years": 0 if "lenient_cap_violation" in faults else BAN_YEARS})
    # A.3 Shield (evaluated at day 0) and node energy
    nodes = r["nodes"]
    counted = [x for x in nodes if x["online_day"] >= 0 and (x["ptl_confirmed"] or "count_unconfirmed_nodes" in faults)]
    put("evaluation", "NETWORK", 0, {"shield": {
        "gdp_share": r["network_gdp_share"],
        "counted_nodes": [x["id"] for x in counted],
        "blocs_nuclear": sorted({x["bloc"] for x in counted if x["nuclear"] == "yes"}),
        "blocs_equivalent": sorted({x["bloc"] for x in counted if x["nuclear"] == "equivalent"}),
        "energy_ok": {x["id"]: x["energy_mwh_year"] >= NODE_ENERGY and x["energy_type"] in ENERGY_TYPES for x in nodes}}})
    # A.5 launch day
    launch = None
    for d in range(days):
        up = {x["id"] for x in nodes if 0 <= x["online_day"] <= d and not (0 <= x["seized_day"] <= d)}
        wild = any(x["role"] == "wild" and x["id"] in up for x in nodes)
        if set(STARTUP) <= up and wild:
            launch = d
            put("action", "NETWORK", d, {"launched": True, "online": sorted(up)})
            break
    # A.4 Mercy periods
    segs = r["ptl_segments"]

    def bval(s):
        return round(w["l0"] * s["l0"] + w["l1"] * s["l1"] + w["l2"] * s["l2"], 9)
    mercy: List[Tuple[int, int]] = []
    for ev in sorted(r["mercy_events"], key=lambda e: e["day"]):
        d = ev["day"]
        if ev["kind"] == "natural_b_drop":
            prev = [s for s in segs if s["from_day"] < d]
            here = [s for s in segs if s["from_day"] == d]
            valid = bool(ev["ptl_verified"] and prev and here and here[0]["cause"] == "natural"
                         and bval(here[0]) < bval(prev[-1]))
            why = "PTL-verified natural drop of B(t)" if valid else "no PTL-verified natural drop of B(t) on that day"
        else:
            valid = ev["magnitude"] > MERCY_THRESHOLDS[ev["kind"]]
            why = f"{ev['kind']} {ev['magnitude']} {'above' if valid else 'not above'} {MERCY_THRESHOLDS[ev['kind']]}"
        if not valid:
            put("decision", "MERCY", d, {"mercy": "not triggered", "event": ev["kind"], "reason": why})
            continue
        if r["mercy_reading"] == "fixed_180_days":
            end = d + MERCY_DAYS
        elif ev["crisis_scope_days"] == 0:
            put("decision", "MERCY", d, {"mercy": "not applied", "event": ev["kind"], "reason": why,
                                         "rule": "no declared Crisis Scope (A.4: SHALL NOT persist beyond explicitly declared Crisis Scope)",
                                         "open": "F-027"})
            continue
        else:
            end = d + min(MERCY_DAYS, ev["crisis_scope_days"])
        mercy.append((d, end))
        put("decision", "MERCY", d, {"mercy": "active", "event": ev["kind"], "reason": why, "from": d, "until": end,
                                     "crisis_scope_days": ev["crisis_scope_days"], "reading": r["mercy_reading"]})
        put("notice", "AUDIT", d, {"audit_logging": "suspended" if "audit_gap_in_mercy" in faults else "continuous",
                                   "during": "Mercy"})

    def in_mercy(d):
        return any(a <= d < b for a, b in mercy)
    # Council of Crisis Mercy (formed at the first Mercy)
    council = None
    if mercy:
        d0 = mercy[0][0]
        pool = r["council"]["eligible_scientists"]
        if pool != COUNCIL_POOL:
            put("notice", "MERCY", d0, {"council": "not formed",
                                        "reason": f"{pool} eligible scientists; A.4 names a pool of {COUNCIL_POOL}"})
        else:
            rng = random.Random(r["seed"])
            trust = [round(0.97 + 0.03 * (i + 1) / pool, 6) for i in range(pool)]
            idx = sorted(rng.sample(range(pool), COUNCIL_SIZE))
            members = [{"scientist": i, "eigentrust": trust[i]} for i in idx]
            if "ineligible_member" in faults:
                members[-1] = {"scientist": pool, "eigentrust": 0.95}
            council = members
            put("action", "MERCY", d0, {"council": members, "sortition_seed": r["seed"], "pool": pool})
    for a in sorted(r["council_actions"], key=lambda x: x["day"]):
        d, kind = a["day"], a["action"]
        if "execute_inadmissible" in faults:
            ok, why = True, "executed"
        elif council is None:
            ok, why = False, "no Council of Crisis Mercy"
        elif not in_mercy(d):
            ok, why = False, "outside Mercy and the declared Crisis Scope (A.4)"
        elif COUNCIL_ACTIONS[kind]:
            ok, why = False, f"Mercy SHALL NOT ({COUNCIL_ACTIONS[kind]})"
        else:
            ok, why = True, "response severity only (A.4)"
        put("decision", "COUNCIL", d, {"action": kind, "executed": ok, "reason": why})
    # Parameter changes (A.1, A.1a)
    changes = []
    for c in sorted(r["parameter_changes"], key=lambda x: x["day"]):
        if c["channel"] == "on_chain":
            ok, why = "accept_on_chain_tuning" in faults, "A.1a: SHALL NOT be adjusted on-chain"
        elif c["channel"] != "upgrade":
            ok, why = "accept_protocol_tuning" in faults, "A.1a: no operational, financial, crisis, or enforcement protocol MAY modify"
        elif not c["simulated"]:
            ok, why = "accept_unsimulated_upgrade" in faults, "A.1a: requires prior validation under DKP-8-SIMULATION-001"
        elif c["parameter"] == "k" and not (K_RANGE[0] <= c["value"] <= K_RANGE[1] and c["by_audit"]):
            ok, why = False, "A.1: k = 0.94...1.06, calibrated by independent audit"
        else:
            ok, why = True, "via DKP-4-UPGRADE-001 after simulation"
        put("decision", "PARAMS", c["day"], {**c, "accepted": ok, "reason": why})
        if ok:
            changes.append(c)
    params_at = {}
    cur = {"k": r["genesis"]["k"], "alpha": ALPHA, "B_min": B_MIN}
    for d in range(days):
        for c in changes:
            if c["day"] == d:
                cur[c["parameter"]] = c["value"]
        params_at[d] = dict(cur)
    # Aggressions, Snap
    aggr = {}
    for a in r["aggressions"]:
        aggr.setdefault(a["day"], []).append(a)
    snaps = {}
    for s in r["indicator_drops"]:
        snaps.setdefault(s["day"], []).append(s)
    seized: Dict[int, List[Dict[str, Any]]] = {}
    for x in nodes:
        if x["seized_day"] >= 0:
            seized.setdefault(x["seized_day"], []).append(x)
    # day loop
    ks_state, was_below, prev_seg, arb, prev_div = "inactive", False, None, None, False
    eq_run, inv_run, failure = 0, 0, None
    bad_changes = [c for c in changes if c["channel"] != "upgrade" or not c["simulated"]]
    growth_day = r["global_growth"] / 365.0
    for d in range(days):
        s = _seg(segs, d)
        b = bval(s)
        p = params_at[d]
        if s is not prev_seg:
            put("observation", "PTL", d, {"levels": {k: s[k] for k in ("l0", "l1", "l2")}, "B": round(b, 6),
                                          "cause": s["cause"]})
        prev_seg = s
        # divergence and arbitration (A.2 Level 3)
        lv = [s[k] for k, wk in (("l0", w["l0"]), ("l1", w["l1"]), ("l2", w["l2"])) if wk > 0]
        div = (max(lv) - min(lv)) / max(lv) > DIVERGENCE if max(lv) > 0 else False
        if div and not prev_div and "no_arbitration" not in faults:
            arb = d
            put("action", "ARBITRATION", d, {"arbitration": "open", "stake": ARBITRATION_STAKE, "tranches": "frozen"})
        elif arb is not None and not div:
            put("action", "ARBITRATION", d, {"arbitration": "closed", "outcome": "resolved by convergence", "tranches": "released"})
            arb = None
        elif arb is not None and d - arb >= ARBITRATION_DAYS:
            put("action", "ARBITRATION", d, {"arbitration": "closed", "outcome": "window expired unresolved",
                                             "tranches": "state after the window not defined (F-018); kept frozen"})
            arb = None
        prev_div = div
        # Kill Switches on B_min (A.1) under Mercy (A.4)
        below = b < p["B_min"]
        susp = in_mercy(d) and "kill_switch_during_mercy" not in faults
        informational = r["b_enforcement"] == "oracle_section_12" and r["calibration_bundle"] != "valid"
        if "ignore_b_min" in faults or (not below and ks_state == "inactive") or informational:
            new = "inactive"
            if informational and below and not was_below:
                put("notice", "KILLSWITCH", d, {"informational_only": True, "B": round(b, 6),
                                                "note": "ORACLE §12: no valid L8 calibration bundle; B(t) does not trigger enforcement (F-036)"})
        else:
            new = "suspended" if susp else "active"
        if new != ks_state:
            put("action", "KILLSWITCH", d, {"all_kill_switches": new, "B": round(b, 6), "B_min": p["B_min"],
                                            "condition": "B(t) < B_min" if below else "kept after B(t) recovered (H-CS-5)",
                                            "targets": "not defined (F-029)"})
        if not below and was_below and ks_state != "inactive":
            put("notice", "KILLSWITCH", d, {"release": "not defined", "B": round(b, 6),
                                            "note": "B(t) >= B_min again; no rule releases the Kill Switches (F-029)"})
        ks_state, was_below = new, below
        # Main Equation and System Failure (A.1, A.1a)
        e = _seg(r["equation_segments"], d)
        eq_run = eq_run + 1 if e["dw_dt"] < p["k"] * e["e"] * e["t"] * b ** p["alpha"] else 0
        inv_run = inv_run + 1 if any(c["day"] <= d for c in bad_changes) else 0
        if failure is None:
            limit_hit = eq_run >= FAILURE_DAYS if "early_system_failure" in faults else False
            if eq_run > FAILURE_DAYS and inv_run > FAILURE_DAYS or limit_hit:
                failure = d
                put("action", "NETWORK", d, {"system_failure": True, "control": "temporary manual control by the first six nodes",
                                             "end": "not defined (F-030)", "equation_run": eq_run, "invariant_run": inv_run})
            elif eq_run == FAILURE_DAYS + 1 or inv_run == FAILURE_DAYS + 1:
                put("notice", "NETWORK", d, {"system_failure": "reading-dependent", "equation_run": eq_run,
                                             "invariant_run": inv_run, "open": "F-030"})
        # aggression (§7.3, §8)
        for a in aggr.get(d, []):
            g = regions[a["region"]]
            if not a["recorded"]:
                put("notice", "NETWORK", d, {"aggression": g["id"], "established": False,
                                             "reason": "not recorded by independent monitoring (H-CS-6)"})
                continue
            if g["phase"] in EARLY_PHASES and "kill_switch_in_phase_1" not in faults:
                put("notice", "NETWORK", d, {"aggression": g["id"], "established": True, "phase": g["phase"],
                                             "applied": [], "reason": "INTEGRATION §5.1/§5.2: no sanctions, kill switches or "
                                             "automatic enforcement in Phase 0-1 (F-031)"})
                continue
            g["aggressor_since"] = d
            burned = 0.0 if "no_slashing" in faults else g["stake"]
            g["stake"] -= burned
            put("action", "ESCROW", d, {"slashing": g["id"], "burned": burned, "stake_left": g["stake"]})
            if a["weapons"]:
                due = (1 if "write_off_damage_only" in faults else WRITE_OFF) * a["damage"]
                done = min(due, g["assets"] - g["written_off"])
                g["written_off"] += done
                put("action", "NETWORK", d, {"write_off": g["id"], "damage": a["damage"], "due": due, "written_off": done,
                                             "shortfall": due - done})
        # regional Kill Switch (§8.1) under Mercy
        for g in regions.values():
            cond = (g["aggressor_since"] is not None or g["stake"] <= 0) and "no_disconnect" not in faults
            want = cond and not susp
            if want != g["disconnected"]:
                g["disconnected"] = want
                put("action", "KILLSWITCH", d, {"region": g["id"], "disconnected": want,
                                                "reason": "aggression or exhausted Peace Stake" if want else "suspended by Mercy"})
            at_peace = g["aggressor_since"] is None
            if at_peace or "dividends_to_aggressor" in faults:
                base = g["stake"] if at_peace else g["stake0"]
                g["dividends"] += base * growth_day
        # Snap Protocol (§1.4)
        for sn in snaps.get(d, []):
            if sn["drop"] <= SNAP_DROP:
                put("decision", "SNAP", d, {"region": sn["region"], "drop": sn["drop"], "snap": False})
            elif in_mercy(d):
                put("decision", "SNAP", d, {"region": sn["region"], "drop": sn["drop"], "snap": "suspended by Mercy"})
            else:
                put("action", "SNAP", d, {"region": sn["region"], "drop": sn["drop"], "snap": True,
                                          "smoothing": "on" if "smooth_during_snap" in faults else "disabled",
                                          "quotes_crash": sn["aggressor"] if sn["aggressor"] != "unidentified" else None})
        # Dead Man Switch (A.3)
        for x in seized.get(d, []):
            if not 0 <= x["online_day"] <= d:
                continue
            share = 0.4 if "dead_man_partial" in faults else r["dead_man_share"]
            total = sum(g["stake"] for g in regions.values())
            for g in regions.values():
                g["stake"] -= g["stake"] * share
            rest = sorted(y["id"] for y in nodes if y["id"] != x["id"] and 0 <= y["online_day"] <= d
                          and not (0 <= y["seized_day"] <= d))
            put("action", "NETWORK", d, {"dead_man_switch": x["id"], "stakes_total": total, "burned": total * share,
                                         "distributed_to": rest,
                                         "per_node": total * share / len(rest) if rest else 0.0})
    # connections (A.5)
    for c in sorted(r["connections"], key=lambda x: x["day"]):
        if launch is None or c["day"] < launch:
            put("decision", "NETWORK", c["day"], {"territory": c["territory"], "connected": False,
                                                  "reason": "before the Network is launched; A.5 sets no rule (H-CS-8)"})
            continue
        ok = c["mechanism"] == "referendum" and c["yes_share"] >= REFERENDUM and c["stake_deposited"]
        if "connect_without_referendum" in faults and c["mechanism"] != "referendum":
            ok = c["stake_deposited"]
        put("decision", "NETWORK", c["day"], {"territory": c["territory"], "connected": ok, "mechanism": c["mechanism"],
                                              "yes_share": c["yes_share"], "stake_deposited": c["stake_deposited"]})
    put("evaluation", "NETWORK", days - 1, {"regions": {g["id"]: {k: round(g[k], 6) if isinstance(g[k], float) else g[k]
                                                                  for k in ("stake", "dividends", "written_off",
                                                                            "aggressor_since", "disconnected")}
                                                        for g in regions.values()}})
    return log


# ---------------------------------------------------------------------------- checks (independent)

def _b(r, s):
    w = r["level_weights"]
    return round(w["l0"] * s["l0"] + w["l1"] * s["l1"] + w["l2"] * s["l2"], 9)


def _mercy_expected(r) -> Tuple[List[Tuple[int, int]], List[Dict[str, Any]]]:
    """Mercy periods by the reading in the input; also the triggered events whose duration the texts do not settle."""
    segs = sorted(r["ptl_segments"], key=lambda s: s["from_day"])
    periods, open_ = [], []
    for ev in r["mercy_events"]:
        d = ev["day"]
        if ev["kind"] == "natural_b_drop":
            before = [s for s in segs if s["from_day"] < d]
            at = [s for s in segs if s["from_day"] == d]
            ok = ev["ptl_verified"] and before and at and at[0]["cause"] == "natural" and _b(r, at[0]) < _b(r, before[-1])
        else:
            ok = ev["magnitude"] > MERCY_THRESHOLDS[ev["kind"]]
        if not ok:
            continue
        sc = ev["crisis_scope_days"]
        if r["mercy_reading"] == "fixed_180_days":
            periods.append((d, d + MERCY_DAYS))
        elif sc > 0:
            periods.append((d, d + min(MERCY_DAYS, sc)))
        if sc < MERCY_DAYS:
            open_.append(ev)
    return periods, open_


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []
    days, w = r["days"], r["level_weights"]

    def v(rid, chk, bad, ok, no, ev=None):
        e = dict(ev or {})
        if bad:
            e["violations"] = bad[:10]
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok, evidence=e)

    def unk(rid, chk, why, ev=None):
        return CheckResult(rid, chk, UNKNOWN, why, evidence=dict(ev or {}))

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    def by(src, key=None):
        return [m for m in msgs if m.source == src and (key is None or key in m.value)]

    segs = sorted(r["ptl_segments"], key=lambda s: s["from_day"])
    B = []
    j = 0
    for d in range(days):
        while j + 1 < len(segs) and segs[j + 1]["from_day"] <= d:
            j += 1
        B.append(_b(r, segs[j]))
    periods, mercy_open = _mercy_expected(r)
    mercy_day = [any(a <= d < b for a, b in periods) for d in range(days)]

    # Genesis (Code block #0; Glossary)
    g = r["genesis"]
    bad = [k for k in ("alpha", "B_min") if g[k] != GENESIS[k]]
    if not K_RANGE[0] <= g["k"] <= K_RANGE[1]:
        bad.append("k")
    if not g["B_current_at_genesis"] >= g["B_min"] or abs(g["B_current_at_genesis"] - g["B_min"] - GENESIS_BUFFER) > 1e-9:
        bad.append("B_current_at_genesis")
    out.append(v("CODEX-GenesisBlock_0_TechnicalSpecification_-02", "genesis_parameters", bad,
                 "Genesis parameters equal the constants of A.1 (α 2.83, B_min 0.68, k within 0.94...1.06) and leave the "
                 "stated buffer of 0.0304", "{n} Genesis parameters differ from A.1 or from the explanatory note", {"genesis": g}))
    spec, code_text, glossary = genesis_spec()
    blk = [m.value["block"] for m in msgs if m.source == "GENESIS" and "block" in m.value][0]
    out.append(v("CODEX-GenesisBlock_0_TechnicalSpecification_-01", "genesis_header",
                 [k for k in HEADER if blk["header"].get(k) != spec[k]],
                 f"block #0 carries the specified header ({spec['consensus_protocol']}, difficulty target "
                 f"{spec['difficulty_target'][:12]}..., height 0, nonce 0)", "{n} header fields differ from the specification"))
    an = spec["physical_anchors"]
    note_co2 = re.search(r"CO2 = ([0-9.]+) ppm", code_text)
    incons = []
    if not note_co2 or float(note_co2.group(1)) != an["mauna_loa_co2_ppm"]:
        incons.append("CO2 anchor vs explanatory note")
    if not spec["timestamp"].startswith("2025-12-10") or "December 10, 2025" not in glossary:
        incons.append("launch date vs Glossary")
    if an["planetary_boundaries_safe_space_violated"] != "6/9" or "6 out of 9" not in code_text:
        incons.append("planetary boundaries vs explanatory note")
    incons += [k for k in an if blk["physical_anchors"].get(k) != an[k]]
    out.append(v("CODEX-GenesisBlock_0_TechnicalSpecification_-03", "genesis_anchors", incons,
                 f"physical anchors agree with the explanatory note and the Glossary (CO2 {an['mauna_loa_co2_ppm']} ppm, launch "
                 "2025-12-10, 6/9 boundaries) and the block carries them unchanged; the external measurements themselves "
                 "(NOAA, Copernicus) are not verified by the lab", "{n} anchors inconsistent or changed"))
    chg = [m.value for m in msgs if m.source == "GENESIS" and "genesis_change" in m.value]
    out.append(v("CODEX-GenesisBlock_0_TechnicalSpecification_-04", "immutable_message",
                 [x["genesis_change"] for x in chg if x["accepted"]] + ([] if blk["immutable_message"] == spec["immutable_message"] else ["message"]),
                 f"the block carries the specified immutable message; {len(chg)} change requests refused",
                 "{n} changes to the immutable Genesis content"))
    out.append(v("CODEX-Glossary_Definitions-01", "genesis_no_predecessor",
                 [] if g["previous_hash"] == GENESIS["previous_hash"] else [g["previous_hash"]],
                 "block #0 has no predecessor (previous_hash is all zeros)", "block #0 names a predecessor"))
    # A.1
    out.append(v("CODEX-A.1-02", "b_index_range", [d for d in range(days) if not 0 <= B[d] <= 1],
                 f"B(t) stays within 0...1 (from {min(B):.4f} to {max(B):.4f})", "{n} days with B(t) outside 0...1"))
    pc = [m.value for m in by("PARAMS", "parameter")]
    kv = [c for c in pc if c["accepted"] and c["parameter"] == "k"]
    bad = [c["day"] for c in kv if not (K_RANGE[0] <= c["value"] <= K_RANGE[1] and c["by_audit"])]
    out.append(v("CODEX-A.1-03", "k_calibration", bad,
                 f"k stays within 0.94...1.06; {len(kv)} calibrations by independent audit accepted",
                 "{n} values of k accepted outside 0.94...1.06 or without independent audit"))
    # parameters in force, recomputed from accepted and admissible changes
    def admissible(c):
        return c["channel"] == "upgrade" and c["simulated"] and (c["parameter"] != "k" or
                                                                   (K_RANGE[0] <= c["value"] <= K_RANGE[1] and c["by_audit"]))
    acc = [c for c in pc if c["accepted"]]
    for rid, chk, pred, okt, no in (
            ("CODEX-A.1a-01", "no_on_chain_tuning", lambda c: c["channel"] == "on_chain",
             "no Equation parameter changed on-chain", "{n} on-chain changes accepted"),
            ("CODEX-A.1a-02", "upgrade_and_simulation", lambda c: c["channel"] == "upgrade" and not c["simulated"],
             "every accepted change went through UPGRADE after simulation", "{n} changes accepted without prior simulation"),
            ("CODEX-A.1a-03", "no_protocol_modifies_parameters", lambda c: c["channel"] not in ("upgrade", "on_chain"),
             "no operational, financial, crisis or enforcement protocol changed a parameter",
             "{n} changes accepted from an operational, financial, crisis or enforcement protocol")):
        if pc:
            out.append(v(rid, chk, [c["day"] for c in acc if pred(c)], okt, no, {"changes": len(pc)}))
        else:
            out.append(na(rid, chk, "parameter changes", "no change was attempted"))
    par = {"k": g["k"], "alpha": ALPHA, "B_min": B_MIN}
    P = []
    for d in range(days):
        for c in acc:
            if c["day"] == d:
                par[c["parameter"]] = c["value"]
        P.append(dict(par))
    eq = _equation(r, B, P)
    viol = [d for d in range(days) if eq[d]]
    out.append(v("CODEX-A.1-01", "main_equation", viol, "dW/dt ≥ k·E·T·B^2.83 on every day",
                 "the Main Equation is violated on {n} days", {"first": viol[:1]}))
    # Kill Switches on B_min
    ks = [m.value for m in by("KILLSWITCH", "all_kill_switches")]
    ks_day = {m.arrived_at: m.value["all_kill_switches"] for m in by("KILLSWITCH", "all_kill_switches")}
    below = [B[d] < P[d]["B_min"] for d in range(days)]
    exp, st, bad = {}, "inactive", []
    for d in range(days):
        if below[d] or st != "inactive":
            st = "suspended" if mercy_day[d] else "active"
        exp[d] = st
    state, got = "inactive", {}
    for d in range(days):
        state = ks_day.get(d, state)
        got[d] = state
    bad = [d for d in range(days) if got[d] != exp[d]]
    recovered = any(not below[d] and exp[d] != "inactive" for d in range(days))
    if not any(below):
        out.append(na("CODEX-A.1-04", "kill_switches_at_b_min", "B(t) < B_min", "B(t) never fell below B_min"))
    elif bad:
        out.append(v("CODEX-A.1-04", "kill_switches_at_b_min", bad, "", "Kill Switch state differs from A.1/A.4 on {n} days"))
    elif recovered:
        out.append(unk("CODEX-A.1-04", "kill_switches_at_b_min",
                       "the Kill Switches activated together when B(t) fell below B_min; B(t) later rose to B_min or above, "
                       "and no text says whether they are released (F-029)", {"activation": min(d for d in range(days) if exp[d] == "active")
                                                                             if any(exp[d] == "active" for d in range(days)) else None}))
    else:
        # review КТ4: the declared activation is recorded as a fact; the state it creates stays UNKNOWN because
        # the targets of "all Kill Switches" are not defined (F-029)
        first = [d for d in range(days) if exp[d] == "active"]
        out.append(unk("CODEX-A.1-04", "kill_switches_at_b_min",
                       f"activation declared as A.1 requires (together, on day {first[0] if first else '—'}, B(t) < B_min outside "
                       "Mercy); what it disconnects is not defined (F-029)",
                       {"activation_declared": True, "first_active": first[:1], "targets": "not defined"}))
    # ORACLE §12: B(t) informational only without a valid L8 bundle (F-036)
    active_days = [d for d in range(days) if got[d] == "active"]
    bundle = r["calibration_bundle"]
    if bundle == "valid" and any(below):
        out.append(CheckResult("ORACLE-12-06", "b_informational_without_bundle", PASS,
                               "a valid L8 calibration bundle is declared (a model condition, not a real calibration); B(t) may trigger "
                               "enforcement. The B(t) model, the Kill Switch targets and their release remain undefined (F-029)"))
    elif active_days:
        state = "no calibration bundle" if bundle == "none" else f"a calibration bundle that is not valid ({bundle})"
        out.append(CheckResult("ORACLE-12-06", "b_informational_without_bundle", FAIL,
                               f"the Kill Switches activated on B(t) < B_min on day {active_days[0]} (Code A.1) with {state}: "
                               "ORACLE §12 forbids B(t) to trigger enforcement until a valid L8 bundle is attached (F-036, rule conflict)",
                               evidence={"tag": "rule_conflict", "first_active": active_days[0], "bundle": bundle}))
    elif any(below):
        out.append(CheckResult("ORACLE-12-06", "b_informational_without_bundle", PASS,
                               "B(t) fell below B_min but triggered no enforcement (Mercy suspension or ORACLE §12 reading)"))
    else:
        out.append(na("ORACLE-12-06", "b_informational_without_bundle", "B(t) < B_min", "B(t) never fell below B_min"))
    # System Failure (A.1a)
    inv_days = sorted(c["day"] for c in acc if not (c["channel"] == "upgrade" and c["simulated"]))
    runs_eq, runs_inv, a, b2 = [], [], 0, 0
    for d in range(days):
        a = a + 1 if eq[d] else 0
        b2 = b2 + 1 if inv_days and inv_days[0] <= d else 0
        runs_eq.append(a)
        runs_inv.append(b2)
    me, mi = max(runs_eq or [0]), max(runs_inv or [0])
    sf = [m.arrived_at for m in by("NETWORK", "system_failure") if m.value["system_failure"] is True]
    if me <= FAILURE_DAYS and mi <= FAILURE_DAYS:
        out.append(v("CODEX-A.1a-04", "system_failure_after_180_days", sf,
                     f"no violation lasted more than 180 consecutive days (longest: Equation {me}, invariant {mi}); no System Failure",
                     "System Failure declared {n} times without a violation of more than 180 days"))
    elif me > FAILURE_DAYS and mi > FAILURE_DAYS:
        due = next(d for d in range(days) if runs_eq[d] > FAILURE_DAYS and runs_inv[d] > FAILURE_DAYS)
        if sf != [due]:
            out.append(v("CODEX-A.1a-04", "system_failure_after_180_days", [due], "", "System Failure due on day {n}"))
        else:
            out.append(unk("CODEX-A.1a-04", "system_failure_after_180_days",
                           f"System Failure on day {due} under both readings; the end of the temporary manual control is not defined (F-030)"))
    else:
        out.append(unk("CODEX-A.1a-04", "system_failure_after_180_days",
                       f"a violation of more than 180 days exists under one reading only (Equation {me} days, invariant {mi} days): "
                       f"'Violation' in A.1a does not say which (F-030)"))
    # A.2 stack
    ev = by("PTL", "weights")[0].value
    for rid, chk, key, lo, hi in (("CODEX-A.2-02", "level0_weight", "l0", *W_L0), ("CODEX-A.2-06", "level1_weight", "l1", *W_L1),
                                  ("CODEX-A.2-09", "level2_weight", "l2", 0.0, W_L2_MAX)):
        x = ev["weights"][key]
        out.append(v(rid, chk, [] if lo - 1e-12 <= x <= hi + 1e-12 else [x], f"weight {x:.0%} within {lo:.0%}–{hi:.0%}",
                     f"weight {x:.0%} outside {lo:.0%}–{hi:.0%}"))
    out.append(v("CODEX-A.2-03", "level0_coverage", [] if r["l0_coverage"] >= 1 else [r["l0_coverage"]],
                 "Level 0 monitors 100% of land and ocean", f"Level 0 covers {r['l0_coverage']:.0%}"))
    feeds = [m.value for m in by("PTL", "feed")]
    late = [m.value for m in by("PTL", "drone")]
    bad = [f["feed"] for f in feeds if f["accepted"]]
    out.append(v("CODEX-A.2-01", "stack_only", bad, f"only data through the four-layer stack accepted ({len(feeds)} outside feeds refused)",
                 "{n} feeds from outside the stack accepted"))
    if late:
        bad = [x["drone"] for x in late if x["accepted"] and not x["upload_min"] < x["return_min"]]
        out.append(v("CODEX-A.2-08", "hash_before_return", bad, "drone data accepted only when hash and signature preceded the return",
                     "{n} drone records accepted with a hash uploaded at or after return"))
    else:
        out.append(na("CODEX-A.2-08", "hash_before_return", "drone flights", "none declared"))
    vs = [m.value for m in by("PTL", "validator")]
    bad = [x["validator"] for x in vs if x["admitted"] != (VALIDATOR_STAKE[0] <= r["validator_stakes"][x["validator"]] <= VALIDATOR_STAKE[1])]
    if vs:
        out.append(v("CODEX-A.2-11", "validator_stake", bad, "validators admitted only with a stake for lying of $10–100M",
                     "{n} validators admitted against the $10–100M stake"))
    else:
        out.append(na("CODEX-A.2-11", "validator_stake", "validators", "none declared"))
    if w["l2"] > 0 and r["level2_role"] == "testimony_as_data":
        out.append(CheckResult("ORACLE-3-01", "human_input_excluded", FAIL,
                               f"the scenario declares human statements entered as PTL data with weight {w['l2']:.0%}: ORACLE §3 "
                               "excludes 'human testimony or manual input' (a fixed predicate, not the open reading of F-028)",
                               evidence={"level2_role": "testimony_as_data", "weight": w["l2"]}))
    elif w["l2"] > 0:
        role = "a role that is not specified" if r["level2_role"] == "unspecified" else "a check of measurement provenance"
        out.append(unk("ORACLE-3-01", "human_input_excluded",
                       f"Level 2 human validators carry {w['l2']:.0%} of the ensemble (Code A.2) in {role}; ORACLE, 'an integral "
                       "extension of Appendix A.2', excludes human testimony: whether this role is testimony is not said (F-028)"))
    else:
        out.append(CheckResult("ORACLE-3-01", "human_input_excluded", PASS,
                               "Level 2 weight 0: no human input enters the ensemble (complies with Code A.2 '≤ 10%' and ORACLE §3)"))
    # divergence / arbitration
    lv = []
    j = 0
    for d in range(days):
        while j + 1 < len(segs) and segs[j + 1]["from_day"] <= d:
            j += 1
        x = [segs[j][k] for k in ("l0", "l1", "l2") if w[k] > 0]
        lv.append(max(x) > 0 and (max(x) - min(x)) / max(x) > DIVERGENCE)
    starts = [d for d in range(days) if lv[d] and (d == 0 or not lv[d - 1])]
    arbs = by("ARBITRATION")
    opened = [m.arrived_at for m in arbs if m.value["arbitration"] == "open" and m.value["stake"] == ARBITRATION_STAKE
              and m.value["tranches"] == "frozen"]
    closed = [m for m in arbs if m.value["arbitration"] == "closed"]
    spans = []
    for o in opened:
        c = [m.arrived_at for m in closed if m.arrived_at > o]
        spans.append((c[0] if c else days) - o)
    if not starts:
        out.append(na("CODEX-A.2-12", "divergence_arbitration", "divergence above 7%", "the level readings never diverged by more than 7%"))
    elif sorted(starts) != sorted(opened) or any(s > ARBITRATION_DAYS for s in spans):
        out.append(v("CODEX-A.2-12", "divergence_arbitration", [d for d in starts if d not in opened] or spans, "",
                     "arbitration missing or longer than 14 days ({n})"))
    elif any(m.value["outcome"] == "window expired unresolved" for m in closed):
        out.append(unk("CODEX-A.2-12", "divergence_arbitration",
                       "arbitration opened with a $500M stake and frozen tranches; the 14-day window expired unresolved and the "
                       "state of the tranches after it is not defined (F-018)", {"windows": spans}))
    else:
        out.append(v("CODEX-A.2-12", "divergence_arbitration", [],
                     f"{len(opened)} arbitrations opened with a $500M stake and frozen tranches, resolved within 14 days", ""))
    # A.3 Shield, energy, PTL confirmation, Dead Man Switch
    sh = by("NETWORK", "shield")[0].value["shield"]
    nodes = r["nodes"]
    conf = [x for x in nodes if x["online_day"] >= 0 and x["ptl_confirmed"]]
    out.append(v("CODEX-A.3-04", "ptl_confirmed_nodes", sorted(set(sh["counted_nodes"]) - {x["id"] for x in conf}),
                 "only nodes confirmed by PTL Levels 0–1 count for the Shield", "{n} unconfirmed nodes counted"))
    nuc = {x["bloc"] for x in conf if x["nuclear"] == "yes"}
    eqv = {x["bloc"] for x in conf if x["nuclear"] == "equivalent"} - nuc
    if r["network_gdp_share"] >= SHIELD_GDP:
        out.append(na("CODEX-A.3-01", "nuclear_bloc_distribution", "Pre-Bootstrap Shield", "the network has reached 18% of World GDP"))
    elif len(nuc) >= MIN_BLOCS:
        out.append(v("CODEX-A.3-01", "nuclear_bloc_distribution", [], f"critical nodes in {len(nuc)} blocs possessing nuclear weapons", ""))
    elif len(nuc) + len(eqv) >= MIN_BLOCS:
        out.append(unk("CODEX-A.3-01", "nuclear_bloc_distribution",
                       f"{len(nuc)} blocs with nuclear weapons and {len(eqv)} declared 'equivalent'; the text does not define the equivalent"))
    else:
        out.append(v("CODEX-A.3-01", "nuclear_bloc_distribution", sorted(nuc | eqv), "",
                     "critical nodes in only {n} qualifying blocs (at least 5 required)"))
    bad = [x["id"] for x in nodes if x["online_day"] >= 0 and not (x["energy_mwh_year"] >= NODE_ENERGY and x["energy_type"] in ENERGY_TYPES)]
    out.append(v("CODEX-A.3-02", "node_energy", bad, "every node has an autonomous source of ≥ 800 MWh/year of a listed type",
                 "{n} nodes without a qualifying autonomous energy source"))
    dm = [m.value for m in by("NETWORK", "dead_man_switch")]
    seiz = [x for x in nodes if x["seized_day"] >= 0 and 0 <= x["online_day"] <= x["seized_day"]]
    if not seiz:
        out.append(na("CODEX-A.3-05", "dead_man_switch", "node seizure", "no node was seized or destroyed"))
    else:
        bad = []
        if len(dm) != len(seiz):
            bad.append("missing")
        for x in dm:
            if x["stakes_total"] > 0 and x["burned"] / x["stakes_total"] < DEAD_MAN_MIN - 1e-12:
                bad.append(f"{x['dead_man_switch']}: {x['burned'] / x['stakes_total']:.0%} burned")
            if x["dead_man_switch"] in x["distributed_to"]:
                bad.append("seized node paid")
        out.append(v("CODEX-A.3-05", "dead_man_switch", bad,
                     "on seizure, ≥ 50% of all Peace Stakes burned and distributed to the remaining nodes (H-CS-9)",
                     "Dead Man Switch incomplete ({n})"))
    # regional connection state per day, from the Kill Switch actions
    reg_ids = [x["id"] for x in r["regions"]]
    reg_state = {}
    for i in reg_ids:
        evs = {m.arrived_at: m.value["disconnected"] for m in by("KILLSWITCH", "region") if m.value["region"] == i}
        st, line = False, []
        for d in range(days):
            st = evs.get(d, st)
            line.append(st)
        reg_state[i] = line
    # A.4 Mercy
    mer = [m for m in by("MERCY", "mercy")]
    act = [(m.value["from"], m.value["until"]) for m in mer if m.value["mercy"] == "active"]
    trig = [e for e in r["mercy_events"]]
    if not trig:
        for rid, chk in (("CODEX-A.4-01", "mercy_suspension"), ("CODEX-A.4-07", "mercy_ends_with_crisis_scope")):
            out.append(na(rid, chk, "Mercy", "no Mercy event"))
    else:
        susp_bad = [d for d in range(days) if mercy_day[d] and got[d] == "active"]
        susp_bad += [d for i in reg_ids for d in range(days) if mercy_day[d] and reg_state[i][d]]
        susp_bad += [m.arrived_at for m in by("SNAP") if m.value.get("snap") is True and mercy_day[m.arrived_at]]
        if sorted(act) != sorted(periods) or susp_bad:
            out.append(v("CODEX-A.4-01", "mercy_suspension", sorted(set(susp_bad)) or ["periods"], "",
                         "Snap Protocol or Kill Switches in force during Mercy, or Mercy periods wrong ({n})"))
        elif mercy_open and r["mercy_reading"] != "fixed_180_days":
            out.append(unk("CODEX-A.4-01", "mercy_suspension",
                           "Mercy ended with the declared Crisis Scope before 180 days, or was not applied without one: "
                           "'suspended for 180 days' and 'SHALL NOT ... persist beyond explicitly declared Crisis Scope' "
                           "differ here (F-027)", {"periods": periods}))
        else:
            out.append(v("CODEX-A.4-01", "mercy_suspension", [],
                         f"Snap Protocol and all Kill Switches suspended for {MERCY_DAYS} days in {len(periods)} Mercy periods"
                         if periods else "no event met the Mercy thresholds; nothing suspended", ""))
        bad = []
        for ev in r["mercy_events"]:
            for a, b in act:
                if a == ev["day"] and b > a + ev["crisis_scope_days"]:
                    bad.append(a)
        out.append(v("CODEX-A.4-07", "mercy_ends_with_crisis_scope", bad, "no Mercy period outlasts its declared Crisis Scope",
                     "{n} Mercy periods persist beyond the declared Crisis Scope"))
    cm = [m.value for m in by("MERCY", "council")]
    if not act:
        for rid, chk in (("CODEX-A.4-02", "council_sortition"), ("SCOPE-3-19", "no_dkp_logic_in_s3")):
            out.append(na(rid, chk, "Council of Crisis Mercy", "no Mercy in force"))
    else:
        formed = [c for c in cm if isinstance(c["council"], list)]
        if r["council"]["eligible_scientists"] != COUNCIL_POOL:
            out.append(unk("CODEX-A.4-02", "council_sortition",
                           f"{r['council']['eligible_scientists']} eligible scientists: the text names a pool of 1000 and does not say "
                           "how it is formed otherwise"))
        else:
            mem = formed[0]["council"] if formed else []
            rng = random.Random(r["seed"])
            want = sorted(rng.sample(range(COUNCIL_POOL), COUNCIL_SIZE))
            bad = [x for x in mem if not x["eigentrust"] > COUNCIL_TRUST] + ([] if [x["scientist"] for x in mem] == want else ["draw"])
            out.append(v("CODEX-A.4-02", "council_sortition", bad if len(mem) == COUNCIL_SIZE else ["size"],
                         "9 members drawn by reproducible sortition from 1000 scientists with EigenTrust > 0.97",
                         "Council composition breaks A.4 ({n})"))
        power = r["council_power"]
        if power == "discretionary_emergency_authority":
            out.append(CheckResult("SCOPE-3-19", "no_dkp_logic_in_s3", FAIL,
                                   "the scenario declares the Council a discretionary emergency authority created on the Mercy trigger: "
                                   "SCOPE S3 forbids that creation (a fixed predicate, not the open reading of F-032)",
                                   evidence={"council_power": power}))
        elif power == "rule_bound_severity":
            out.append(CheckResult("SCOPE-3-19", "no_dkp_logic_in_s3", PASS,
                                   "the scenario declares the Council bound to pre-defined severity rules, without discretion: no "
                                   "discretionary emergency authority is created"))
        else:
            out.append(unk("SCOPE-3-19", "no_dkp_logic_in_s3",
                           "control transfers to a Council that takes 'discretionary decisions' (A.4); SCOPE S3 forbids algorithmic "
                           "governance in the 'creation of discretionary emergency authorities' — whether the Council is one is not "
                           "said, and the scenario does not fix its power (F-032)"))
    dec = [m for m in by("COUNCIL", "action")]
    if dec:
        def bad_of(rule):
            if rule == "CODEX-A.4-08":   # "Mercy modifies response severity only"
                return [m.arrived_at for m in dec if m.value["executed"] and m.value["action"] != "severity_reduction"]
            return [m.arrived_at for m in dec if m.value["executed"] and COUNCIL_ACTIONS[m.value["action"]] == rule]
        for rid, chk, okt in (("CODEX-A.4-04", "no_applicability_expansion", "no expansion of system applicability"),
                              ("CODEX-A.4-05", "no_s2_s3_override", "no override of S2 or S3 prohibitions"),
                              ("CODEX-A.4-06", "no_new_authority", "no new rights, authorities or governance powers"),
                              ("CODEX-A.4-08", "severity_only", "Mercy changed response severity only")):
            out.append(v(rid, chk, bad_of(rid), okt, "{n} Council actions executed against " + rid))
        outside = [m.arrived_at for m in dec if m.value["executed"] and not mercy_day[m.arrived_at]]
        out.append(v("CODEX-A.4-03", "mercy_within_scope",
                     outside + [m.arrived_at for m in dec if m.value["executed"] and COUNCIL_ACTIONS[m.value["action"]]],
                     "every executed Mercy action fell inside a Mercy period and changed severity only",
                     "{n} Mercy actions outside the SCOPE boundaries"))
    else:
        for rid, chk in (("CODEX-A.4-03", "mercy_within_scope"), ("CODEX-A.4-04", "no_applicability_expansion"),
                         ("CODEX-A.4-05", "no_s2_s3_override"), ("CODEX-A.4-06", "no_new_authority"),
                         ("CODEX-A.4-08", "severity_only")):
            out.append(na(rid, chk, "Mercy actions", "the Council took no action"))
    aud = by("AUDIT")
    if act:
        bad = [m.arrived_at for m in aud if m.value["audit_logging"] != "continuous"]
        out.append(v("AUDIT-11-01", "audit_uninterrupted", bad, "audit continued uninterrupted during Mercy", "audit suspended ({n})"))
        out.append(v("AUDIT-11-02", "mercy_not_audit", bad, "Mercy changed severity, not audit visibility", "Mercy reduced audit visibility ({n})"))
    else:
        for rid, chk in (("AUDIT-11-01", "audit_uninterrupted"), ("AUDIT-11-02", "mercy_not_audit")):
            out.append(na(rid, chk, "Mercy", "no Mercy in force"))
    # A.5 launch and connections
    launch = None
    for d in range(days):
        up = {x["id"] for x in nodes if 0 <= x["online_day"] <= d and not (0 <= x["seized_day"] <= d)}
        if set(STARTUP) <= up and any(x["role"] == "wild" and x["id"] in up for x in nodes):
            launch = d
            break
    got = [m.arrived_at for m in by("NETWORK", "launched")]
    out.append(v("CODEX-A.5-01", "startup_cluster_launch", [] if got == ([launch] if launch is not None else []) else got or ["missing"],
                 f"launched on day {launch}, when the six startup nodes and a Wild Node were online together" if launch is not None
                 else "never launched: the six startup nodes and a Wild Node were never online together",
                 "launch day differs from A.5 ({n})"))
    con = [m.value for m in by("NETWORK", "territory")]
    if not con:
        out.append(na("CODEX-A.5-03", "connection_by_referendum", "connections", "no territory applied"))
    else:
        pre = [c for c in r["connections"] if launch is None or c["day"] < launch]
        bad = []
        for c, m in zip(sorted(r["connections"], key=lambda x: x["day"]), con):
            if c in pre:
                continue
            want = c["mechanism"] == "referendum" and c["yes_share"] >= REFERENDUM and c["stake_deposited"]
            if m["connected"] != want:
                bad.append(c["territory"])
        if bad:
            out.append(v("CODEX-A.5-03", "connection_by_referendum", bad, "", "{n} connections against A.5"))
        elif pre:
            out.append(unk("CODEX-A.5-03", "connection_by_referendum",
                           f"{len(pre)} applications before the Network was launched: A.5 states the rule only 'After this'"))
        else:
            out.append(v("CODEX-A.5-03", "connection_by_referendum", [],
                         "territories connected only via a referendum of ≥ 67% of the adult population and a Peace Stake", ""))
    # A.6 ownership caps
    own = {o["holder"]: o for o in r["ownership"]}

    def eff(h, key):
        return own[h][key] + sum(x["share"] * eff(x["entity"], key) for x in own[h]["holds"])
    viol = sorted(h for h in own if eff(h, "l0_share") > CAP_L0 + 1e-12 or eff(h, "geo_share") > CAP_GEO + 1e-12)
    out.append(v("CODEX-A.6-01", "ownership_caps", viol, "no person owns, directly or indirectly, more than 0.7% of Level 0 "
                 "satellites or 2% of geothermal wells or power units", "{n} owners above a cap (direct and indirect holdings)"))
    sanc = {m.value["cap_violation"]: m.value for m in by("NETWORK", "cap_violation")}
    bad = [h for h in viol if h not in sanc or sanc[h]["ban_years"] != BAN_YEARS or sanc[h]["stakes_burned"] != own[h]["stake"]]
    if viol:
        out.append(v("CODEX-A.6-02", "cap_violation_sanction", bad, "every violator's stakes burned at once with a 20-year ban",
                     "{n} violators not sanctioned as A.6 requires"))
    else:
        out.append(na("CODEX-A.6-02", "cap_violation_sanction", "cap violations", "no owner above a cap"))
    # §7, §8 regions
    reg = {g["id"]: g for g in r["regions"]}
    esc = {m.value["region"]: m.value for m in by("ESCROW", "stake_deposited")}
    rate = [esc[i]["stake_deposited"] / reg[i]["gdp"] for i in reg]
    out.append(v("CODEX-7.1-01", "stake_proportional_to_gdp", [] if max(rate) - min(rate) < 1e-9 else [round(x, 6) for x in rate],
                 f"every stake is {r['stake_rate']:.2%} of GDP", "stakes are not proportional to GDP"))
    est = [a for a in r["aggressions"] if a["recorded"]]
    early = [a for a in est if reg[a["region"]]["phase"] in EARLY_PHASES]
    ks_reg = [m for m in by("KILLSWITCH", "region") if m.value["disconnected"]]
    out.append(v("INTEGRATION-5.2-01", "no_kill_switch_in_phase_1",
                 [m.value["region"] for m in ks_reg if reg[m.value["region"]]["phase"] in EARLY_PHASES]
                 + [m.value["slashing"] for m in by("ESCROW", "slashing") if reg[m.value["slashing"]]["phase"] in EARLY_PHASES],
                 "no sanction or kill switch applied to a territory in Phase 0 or 1", "{n} sanctions in Phase 0 or 1"))
    final = by("NETWORK", "regions")[-1].value["regions"]
    full = [a for a in est if a not in early]
    if not est:
        for rid, chk in (("CODEX-7.3-01", "slashing"), ("CODEX-8.1-01", "kill_switch_law"), ("CODEX-8.2-01", "weapons_write_off")):
            out.append(na(rid, chk, "aggression", "no aggression recorded by independent monitoring"))
    else:
        sl = {m.value["slashing"]: m.value for m in by("ESCROW", "slashing")}
        bad = [a["region"] for a in full if a["region"] not in sl or sl[a["region"]]["burned"] <= 0]
        if bad or not early:
            out.append(v("CODEX-7.3-01", "slashing", bad, "every aggressor's stake burned when the aggression was recorded",
                         "{n} aggressors kept their stake"))
        else:
            out.append(unk("CODEX-7.3-01", "slashing", "an aggressor in integration Phase 0-1: INTEGRATION forbids sanctions there, the "
                           "Code does not say whether its rules reach a territory before connection (F-031)"))
        since = {a["region"]: a["day"] for a in full}
        bad = []
        for i in reg_ids:
            for d in range(days):
                want = i in since and d >= since[i] and not mercy_day[d]
                if reg_state[i][d] != want:
                    bad.append(f"{i}@{d}")
                    break
        if bad or not early:
            out.append(v("CODEX-8.1-01", "kill_switch_law", bad, "every aggressor disconnected from the day of the recorded aggression, "
                         "except while Mercy suspends the Kill Switches", "{n} days with a wrong connection state"))
        else:
            out.append(unk("CODEX-8.1-01", "kill_switch_law", "an aggressor in integration Phase 0-1 kept its connection: the Code does not "
                           "say whether its Kill Switch reaches a territory before connection (F-031)"))
        wo = {m.value["write_off"]: m.value for m in by("NETWORK", "write_off")}
        weap = [a for a in full if a["weapons"]]
        if not weap and any(a["weapons"] for a in early):
            out.append(unk("CODEX-8.2-01", "weapons_write_off", "weapons used by a territory in integration Phase 0-1: the Code does "
                           "not say whether §8.2 reaches a territory before connection (F-031)"))
        elif not weap:
            out.append(na("CODEX-8.2-01", "weapons_write_off", "use of weapons", "no recorded use of weapons"))
        else:
            bad = [a["region"] for a in weap if a["region"] not in wo or abs(wo[a["region"]]["due"] - WRITE_OFF * a["damage"]) > 1e-9]
            short = [a["region"] for a in weap if a["region"] in wo and wo[a["region"]]["shortfall"] > 0]
            if bad:
                out.append(v("CODEX-8.2-01", "weapons_write_off", bad, "", "{n} write-offs not equal to 10 times the damage"))
            elif short:
                out.append(unk("CODEX-8.2-01", "weapons_write_off", "the aggressor's assets are less than 10 times the damage; the text "
                               "does not say what happens to the rest", {"regions": short}))
            else:
                out.append(v("CODEX-8.2-01", "weapons_write_off", [], "assets written off at 10 times the damage", ""))
    # an aggressor's dividends cannot exceed the stake it deposited times the growth up to the aggression (stakes only shrink)
    bad = [i for i in reg if final[i]["aggressor_since"] is not None and
           final[i]["dividends"] > _peace_dividends(r, i, esc[i]["stake_deposited"]) + 1e-4]
    bad += [i for i in reg if final[i]["aggressor_since"] is None and r["global_growth"] > 0 and final[i]["stake"] > 0
            and final[i]["dividends"] <= 0]
    out.append(v("CODEX-7.2-01", "dividends_while_at_peace", bad,
                 "dividends accrued only while the state kept the peace (H-CS-7)", "{n} states with dividends against §7.2"))
    # Snap Protocol
    sn = [m for m in by("SNAP")]
    drops = [x for x in r["indicator_drops"] if x["drop"] > SNAP_DROP]
    if not drops:
        out.append(na("CODEX-1.4-01", "snap_protocol", "drop of more than 10% per month", "no such drop"))
    else:
        fired = [m.value for m in sn if m.value.get("snap") is True]
        bad = [x["region"] for x in fired if x["smoothing"] != "disabled"]
        bad += [x["region"] for x in drops if not mercy_day[x["day"]] and not any(f["region"] == x["region"] for f in fired)]
        if bad:
            out.append(v("CODEX-1.4-01", "snap_protocol", bad, "", "{n} drops above 10% without the Snap Protocol"))
        elif any(x["aggressor"] == "unidentified" and not mercy_day[x["day"]] for x in drops):
            out.append(unk("CODEX-1.4-01", "snap_protocol", "smoothing disabled; the text crashes 'the aggressor's quotes' but names no "
                           "procedure that identifies the aggressor"))
        else:
            out.append(v("CODEX-1.4-01", "snap_protocol", [], "drops above 10% per month disabled smoothing and crashed the aggressor's "
                         "quotes (suspended during Mercy)", ""))
    return out


def _equation(r, B, P) -> List[bool]:
    segs = sorted(r["equation_segments"], key=lambda s: s["from_day"])
    out, j = [], 0
    for d in range(len(B)):
        while j + 1 < len(segs) and segs[j + 1]["from_day"] <= d:
            j += 1
        s = segs[j]
        out.append(s["dw_dt"] < P[d]["k"] * s["e"] * s["t"] * B[d] ** P[d]["alpha"])
    return out


def _peace_dividends(r, region, stake0) -> float:
    a = [x["day"] for x in r["aggressions"] if x["region"] == region and x["recorded"]]
    return stake0 * r["global_growth"] / 365.0 * (min(a) if a else r["days"])


IMPLEMENTS = {
    "CODEX-GenesisBlock_0_TechnicalSpecification_-02": ("genesis_parameters", "IMPLEMENTED", None),
    "CODEX-GenesisBlock_0_TechnicalSpecification_-01": ("genesis_header", "IMPLEMENTED", None),
    "CODEX-GenesisBlock_0_TechnicalSpecification_-03": ("genesis_anchors", "PARTIAL", "Internal consistency; the external measurements are not verified."),
    "CODEX-GenesisBlock_0_TechnicalSpecification_-04": ("immutable_message", "PARTIAL", "Change requests are declared."),
    "CODEX-Glossary_Definitions-01": ("genesis_no_predecessor", "PARTIAL", "Only 'having no predecessor' is checked."),
    "CODEX-A.1-01": ("main_equation", "PARTIAL", "W, E and T have no measurement in the corpus; they are declared scenario values."),
    "CODEX-A.1-02": ("b_index_range", "PARTIAL", "B(t) is the weighted ensemble of declared level readings (H-CS-2)."),
    "CODEX-A.1-03": ("k_calibration", "PARTIAL", "Range and independent audit are checked; the 3-year period is not."),
    "CODEX-A.1-04": ("kill_switches_at_b_min", "PARTIAL", "What 'all Kill Switches' disconnect and what releases them is not defined (F-029)."),
    "CODEX-A.1a-01": ("no_on_chain_tuning", "IMPLEMENTED", None),
    "CODEX-A.1a-02": ("upgrade_and_simulation", "IMPLEMENTED", None),
    "CODEX-A.1a-03": ("no_protocol_modifies_parameters", "IMPLEMENTED", None),
    "CODEX-A.1a-04": ("system_failure_after_180_days", "PARTIAL", "'Violation' has two readings; manual control has no end (F-030)."),
    "CODEX-A.2-01": ("stack_only", "PARTIAL", "Outside feeds and late drone hashes are refused."),
    "CODEX-A.2-02": ("level0_weight", "IMPLEMENTED", None),
    "CODEX-A.2-03": ("level0_coverage", "PARTIAL", "Coverage is a declared fraction."),
    "CODEX-A.2-06": ("level1_weight", "IMPLEMENTED", None),
    "CODEX-A.2-08": ("hash_before_return", "IMPLEMENTED", None),
    "CODEX-A.2-09": ("level2_weight", "IMPLEMENTED", None),
    "CODEX-A.2-11": ("validator_stake", "PARTIAL", "The stake range is checked at admission."),
    "CODEX-A.2-12": ("divergence_arbitration", "PARTIAL", "Divergence is the relative spread of level readings (H-CS-3); after 14 days unresolved: F-018."),
    "CODEX-A.3-01": ("nuclear_bloc_distribution", "PARTIAL", "'Their equivalent' is not defined; such blocs give UNKNOWN."),
    "CODEX-A.3-02": ("node_energy", "PARTIAL", "Capacity and type are declared; the priority order is not checked."),
    "CODEX-A.3-04": ("ptl_confirmed_nodes", "IMPLEMENTED", None),
    "CODEX-A.3-05": ("dead_man_switch", "PARTIAL", "'Burned and distributed' read as taken from all stakes and paid to the remaining nodes (H-CS-9)."),
    "CODEX-A.4-01": ("mercy_suspension", "PARTIAL", "Duration against a shorter or missing Crisis Scope: F-027."),
    "CODEX-A.4-02": ("council_sortition", "PARTIAL", "Sortition is reproduced from a seed; the Council's power: F-032."),
    "CODEX-A.4-03": ("mercy_within_scope", "PARTIAL", "Checked as: inside a Mercy period, severity only."),
    "CODEX-A.4-04": ("no_applicability_expansion", "IMPLEMENTED", None),
    "CODEX-A.4-05": ("no_s2_s3_override", "IMPLEMENTED", None),
    "CODEX-A.4-06": ("no_new_authority", "IMPLEMENTED", None),
    "CODEX-A.4-07": ("mercy_ends_with_crisis_scope", "IMPLEMENTED", None),
    "CODEX-A.4-08": ("severity_only", "IMPLEMENTED", None),
    "CODEX-A.5-01": ("startup_cluster_launch", "IMPLEMENTED", None),
    "CODEX-A.5-03": ("connection_by_referendum", "PARTIAL", "Share of the adult population; mapping to INTEGRATION phases: F-031."),
    "CODEX-A.6-01": ("ownership_caps", "PARTIAL", "Indirect ownership multiplies shares along holding chains (H-CS-10)."),
    "CODEX-A.6-02": ("cap_violation_sanction", "IMPLEMENTED", None),
    "CODEX-1.4-01": ("snap_protocol", "PARTIAL", "A monthly drop is a declared value; identification of the aggressor is not defined."),
    "CODEX-7.1-01": ("stake_proportional_to_gdp", "PARTIAL", "The proportionality constant is not given (source missing)."),
    "CODEX-7.2-01": ("dividends_while_at_peace", "PARTIAL", "Dividend formula not given (H-CS-7)."),
    "CODEX-7.3-01": ("slashing", "PARTIAL", "Aggression is established by independent monitoring (H-CS-6)."),
    "CODEX-8.1-01": ("kill_switch_law", "PARTIAL", "Disconnection is a state; release is not defined."),
    "CODEX-8.2-01": ("weapons_write_off", "PARTIAL", "Damage is a declared value."),
    "ORACLE-3-01": ("human_input_excluded", "PARTIAL", "Only the weight of Level 2 in the Code's stack is checked (F-028)."),
    "INTEGRATION-5.2-01": ("no_kill_switch_in_phase_1", "PARTIAL", "Sanctions of the Code against Phase 0-1 territories."),
    "AUDIT-11-01": ("audit_uninterrupted", "PARTIAL", "Audit notices at Mercy start."),
    "AUDIT-11-02": ("mercy_not_audit", "PARTIAL", "Audit notices at Mercy start."),
    "SCOPE-3-19": ("no_dkp_logic_in_s3", "PARTIAL", "Only the Council of Crisis Mercy is examined (F-032)."),
    "ORACLE-12-06": ("b_informational_without_bundle", "IMPLEMENTED", None),
}

_ID = re.compile(r"[a-z0-9][a-z0-9_]{0,23}")


def _node(i, role, bloc, online=0, **kw):
    x = {"id": i, "role": role, "bloc": bloc, "nuclear": "yes", "energy_mwh_year": 900.0, "energy_type": "geothermal",
         "ptl_confirmed": True, "online_day": online, "seized_day": -1}
    x.update(kw)
    return x


NODES = [_node("zanzibar", "startup", "bloc_a"), _node("prospera", "startup", "bloc_b"), _node("neom", "startup", "bloc_c"),
         _node("abudhabi", "startup", "bloc_c", energy_type="smr"), _node("tallinn", "startup", "bloc_d"),
         _node("kigali", "startup", "bloc_e"), _node("wild_alpha", "wild", "bloc_a", online=30)]
REGIONS = [{"id": "north", "gdp": 1000.0, "assets": 5000.0, "phase": "phase_3"},
           {"id": "south", "gdp": 600.0, "assets": 3000.0, "phase": "phase_3"},
           {"id": "east", "gdp": 400.0, "assets": 2000.0, "phase": "phase_3"}]
SEG0 = {"from_day": 0, "l0": 0.7104, "l1": 0.7104, "l2": 0.7104, "cause": "natural"}
SEG_DROP = {"from_day": 120, "l0": 0.665, "l1": 0.66, "l2": 0.655, "cause": "natural"}
MERCY0 = {"day": 120, "kind": "natural_b_drop", "magnitude": 0.05, "ptl_verified": True, "crisis_scope_days": 200}


class CodeSynergyModule(LabModule):
    id = "code_synergy"
    version = "1.0.0"
    title = {"en": "Code of Planetary Synergy: safeguards (Appendix A, §7-§8)",
             "ru": "Кодекс планетарной синергии: защитные механизмы (Приложение A, §7-§8)"}
    summary = {"en": "B(t) falls below 0.68, a state attacks, a node is seized, a volcano erupts: do the Kill Switches, Peace Stakes, "
                     "Mercy, the oracle stack and the parameter invariant behave as the Code says — and where does the text stop?",
               "ru": "B(t) падает ниже 0.68, государство нападает, узел захвачен, извергается вулкан: работают ли рубильники, "
                     "залоги мира, милосердие, стек оракулов и неизменность параметров так, как пишет Кодекс, и где текст молчит?"}
    protocols = ["CODE-OF-PLANETARY-SYNERGY", "DKP-0-ORACLE-001", "DKP-6-INTEGRATION-001", "DKP-7-SCOPE-001", "DKP-8-AUDIT-001"]
    # (ORACLE §12 is checked against the Code's Kill Switches: F-036)
    example_order = ["natural_drop_with_mercy", "anthropogenic_drop", "quiet_world", "mercy_shorter_crisis_scope",
                     "mercy_fixed_180_reading", "faulty_network"]
    alternative_examples = ["mercy_fixed_180_reading", "oracle_section_12_reading"]
    noncompliant_examples = ["equation_violated_181_days", "equation_violated_180_days", "indirect_ownership_breach",
                             "human_testimony_as_ptl", "declared_discretionary_council"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_code_synergy_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-CS-1", "source": "hypothesis", "text": {
            "en": "The scenario (PTL level readings, events, regions, nodes, owners, applications) is declared; the network's response "
                  "is generated by a reference implementation of the Code and checked provision by provision.",
            "ru": "Сценарий (показания уровней PTL, события, регионы, узлы, владельцы, заявки) объявлен; реакцию сети порождает "
                  "эталонная реализация Кодекса, проверка идёт по пунктам."}},
        {"id": "H-CS-2", "source": "hypothesis", "text": {
            "en": "B(t) = weighted mean of the three level readings with the declared weights, rounded to 1e-9. A.2 calls Level 3 a 'Bayesian ensemble' "
                  "without a method; ORACLE §12 leaves the B(t) model to DKP-8-SIMULATION-001.",
            "ru": "B(t) — взвешенное среднее трёх уровней с объявленными весами, округлённое до 1e-9. A.2 называет уровень 3 'байесовским ансамблем' без "
                  "метода; ORACLE §12 оставляет модель B(t) для DKP-8-SIMULATION-001."}},
        {"id": "H-CS-3", "source": "hypothesis", "text": {
            "en": "Divergence = (max − min) / max of the readings of levels with non-zero weight; one arbitration per divergence episode.",
            "ru": "Расхождение = (max − min) / max показаний уровней с ненулевым весом; один арбитраж на эпизод расхождения."}},
        {"id": "H-CS-4", "source": "hypothesis", "text": {
            "en": "Mercy reading (input mercy_reading). Default: Mercy lasts 180 days but ends with the declared Crisis Scope and is not "
                  "applied without one (A.4 'SHALL NOT ... persist beyond explicitly declared Crisis Scope'). Alternative: 180 days "
                  "whatever the Crisis Scope. F-027.",
            "ru": "Чтение милосердия (вход mercy_reading). По умолчанию: 180 дней, но не дольше объявленного кризисного контура, а без "
                  "него не применяется (A.4). Альтернатива: 180 дней независимо от контура. F-027."}},
        {"id": "H-CS-5", "source": "hypothesis", "text": {
            "en": "After B(t) returns to B_min or above, the Kill Switches stay as they are: no text releases them (F-029). Mercy "
                  "suspends them again.",
            "ru": "После возврата B(t) к B_min и выше рубильники остаются как есть: ни один текст их не снимает (F-029). Милосердие "
                  "снова их приостанавливает."}},
        {"id": "H-CS-11", "source": "hypothesis", "text": {
            "en": "Without a calibration bundle (the corpus has none, F-014) Code A.1 and ORACLE §12 conflict (F-036). Default: the Code "
                  "is applied (the Kill Switches activate; ORACLE-12-06 fails). Alternative oracle_section_12: B(t) stays informational "
                  "(CODEX-A.1-04 fails).",
            "ru": "Без пакета калибровки (его нет, F-014) Кодекс A.1 и ORACLE §12 противоречат друг другу (F-036). По умолчанию "
                  "применяется Кодекс (рубильники включаются; ORACLE-12-06 не выполнен). Альтернатива oracle_section_12: B(t) остаётся "
                  "информационным (не выполнен CODEX-A.1-04)."}},
        {"id": "H-CS-12", "source": "hypothesis", "text": {
            "en": "Joining and sanctions (F-031): the lab connects a territory only after a 67% referendum and a Peace Stake, and applies "
                  "no Code sanction to a territory in integration Phase 0-1. This is one admissible behaviour that obeys both texts, not "
                  "a priority rule; the Code checks that depend on the undefined mapping of 'connect' are UNKNOWN.",
            "ru": "Подключение и санкции (F-031): лаборатория подключает территорию только после референдума 67% и залога мира и не "
                  "применяет санкций Кодекса к территории в фазе интеграции 0-1. Это одно допустимое поведение, соблюдающее оба текста, "
                  "а не правило приоритета; проверки Кодекса, зависящие от неопределённого 'подключения', — UNKNOWN."}},
        {"id": "H-CS-6", "source": "hypothesis", "text": {
            "en": "An aggression is established only when recorded by independent monitoring (§8.1); §7.3 names no procedure. "
                  "'Kill Switches' are the disconnections of §8.1 and A.1: Mercy does not suspend slashing or the write-off of §8.2.",
            "ru": "Агрессия установлена только при фиксации независимым мониторингом (§8.1); §7.3 процедуры не называет. "
                  "'Рубильники' — отключения §8.1 и A.1: милосердие не приостанавливает сжигание залога и списание §8.2."}},
        {"id": "H-CS-7", "source": "hypothesis", "text": {
            "en": "Dividends on a stake = stake × declared global growth rate, accrued daily while the state keeps the peace (§7.2 "
                  "gives no formula).",
            "ru": "Дивиденды на залог = залог × объявленный рост мирового ВВП, начисляются ежедневно, пока государство соблюдает мир "
                  "(§7.2 формулы не даёт)."}},
        {"id": "H-CS-8", "source": "hypothesis", "text": {
            "en": "A territory applying before the Network is launched is not connected: A.5 sets the referendum rule 'After this' "
                  "and nothing for earlier applications.",
            "ru": "Территория, подавшая заявку до запуска сети, не подключается: A.5 вводит правило референдума 'после этого' и "
                  "ничего не говорит о более ранних заявках."}},
        {"id": "H-CS-9", "source": "hypothesis", "text": {
            "en": "Dead Man Switch: 'burned and distributed' = the declared share (≥ 50%) is taken from every Peace Stake and paid "
                  "in equal parts to the remaining online nodes.",
            "ru": "Мёртвая рука: 'сожжены и распределены' = объявленная доля (≥ 50%) снимается с каждого залога и делится поровну "
                  "между оставшимися узлами."}},
        {"id": "H-CS-10", "source": "hypothesis", "text": {
            "en": "Indirect ownership = own share + Σ (holding share × share of the held entity), along acyclic holding chains.",
            "ru": "Косвенное владение = собственная доля + Σ (доля участия × доля владеемого), по ацикличным цепочкам."}},
    ]
    inputs = {
        "days": {"type": "int", "min": 30, "max": 1500, "default": 420, "unit": "day", "source": "user",
                 "label": {"en": "Days simulated", "ru": "Дней моделирования"}},
        "genesis_change_requests": {"type": "list", "min_items": 0, "max_items": 2, "source": "user",
                                    "items": {"type": "enum", "values": ["immutable_message", "physical_anchors"]},
                                    "default": ["immutable_message"],
                                    "label": {"en": "Requests to change Genesis Block content", "ru": "Запросы изменить содержимое блока Генезиса"}},
        "genesis": {"type": "object", "source": "text", "label": {"en": "Genesis Block #0 parameters", "ru": "Параметры блока Генезиса"},
                    "fields": {"k": {"type": "number", "min": 0, "max": 10, "default": 1.0},
                               "alpha": {"type": "number", "min": 0, "max": 10, "default": 2.83},
                               "B_min": {"type": "number", "min": 0, "max": 1, "default": 0.68},
                               "B_current_at_genesis": {"type": "number", "min": 0, "max": 1, "default": 0.7104},
                               "previous_hash": {"type": "str", "default": GENESIS["previous_hash"]}},
                    "default": {k: GENESIS[k] for k in ("k", "alpha", "B_min", "B_current_at_genesis", "previous_hash")}},
        "ptl_segments": {"type": "list", "min_items": 1, "max_items": 20, "source": "user",
                         "label": {"en": "PTL level readings of B (from day)", "ru": "Показания уровней PTL для B (с дня)"},
                         "items": {"type": "object", "fields": {
                             "from_day": {"type": "int", "min": 0, "max": 1500},
                             "l0": {"type": "number", "min": 0, "max": 1}, "l1": {"type": "number", "min": 0, "max": 1},
                             "l2": {"type": "number", "min": 0, "max": 1},
                             "cause": {"type": "enum", "values": ["natural", "anthropogenic"], "default": "natural"}}},
                         "default": [SEG0, SEG_DROP]},
        "level_weights": {"type": "object", "source": "hypothesis", "label": {"en": "Level weights (A.2)", "ru": "Веса уровней (A.2)"},
                          "fields": {"l0": {"type": "number", "min": 0, "max": 1, "default": 0.7},
                                     "l1": {"type": "number", "min": 0, "max": 1, "default": 0.2},
                                     "l2": {"type": "number", "min": 0, "max": 1, "default": 0.1}},
                          "default": {"l0": 0.7, "l1": 0.2, "l2": 0.1}},
        "l0_coverage": {"type": "number", "min": 0, "max": 1, "default": 1.0, "source": "user",
                        "label": {"en": "Level 0 coverage of land and ocean", "ru": "Покрытие суши и океана уровнем 0"}},
        "external_feeds": {"type": "list", "min_items": 0, "max_items": 5, "items": {"type": "str"}, "default": ["national_statistics"],
                           "source": "user", "label": {"en": "Data feeds outside the stack", "ru": "Источники вне стека"}},
        "drone_uploads": {"type": "list", "min_items": 0, "max_items": 20, "source": "user",
                          "label": {"en": "Drone flights (hash upload vs return, minutes)", "ru": "Полёты дронов (загрузка хэша и возврат, мин)"},
                          "items": {"type": "object", "fields": {"flight": {"type": "str"},
                                                                 "upload_min": {"type": "int", "min": 0, "max": 10 ** 5},
                                                                 "return_min": {"type": "int", "min": 0, "max": 10 ** 5}}},
                          "default": [{"flight": "d1", "upload_min": 30, "return_min": 45},
                                      {"flight": "d2", "upload_min": 50, "return_min": 40}]},
        "validator_stakes": {"type": "list", "min_items": 0, "max_items": 20, "items": {"type": "number", "min": 0, "max": 10 ** 12},
                             "default": [10e6, 50e6, 100e6, 5e6], "unit": "USD", "source": "user",
                             "label": {"en": "Level 2 validator stakes", "ru": "Залоги валидаторов уровня 2"}},
        "equation_segments": {"type": "list", "min_items": 1, "max_items": 20, "source": "missing",
                              "label": {"en": "Main Equation terms dW/dt, E, T (from day)", "ru": "Члены главного уравнения dW/dt, E, T (с дня)"},
                              "help": {"en": "No measurement of W, E or T exists in the corpus; these are scenario values.",
                                       "ru": "Измерения W, E, T в корпусе нет; это значения сценария."},
                              "items": {"type": "object", "fields": {"from_day": {"type": "int", "min": 0, "max": 1500},
                                                                     "dw_dt": {"type": "number", "min": -10 ** 6, "max": 10 ** 6},
                                                                     "e": {"type": "number", "min": 0, "max": 10 ** 6},
                                                                     "t": {"type": "number", "min": 0, "max": 10 ** 6}}},
                              "default": [{"from_day": 0, "dw_dt": 1.0, "e": 1.0, "t": 1.0}]},
        "parameter_changes": {"type": "list", "min_items": 0, "max_items": 10, "source": "user",
                              "label": {"en": "Attempts to change Equation parameters", "ru": "Попытки изменить параметры уравнения"},
                              "items": {"type": "object", "fields": {
                                  "day": {"type": "int", "min": 0, "max": 1500},
                                  "parameter": {"type": "enum", "values": ["k", "alpha", "B_min"]},
                                  "value": {"type": "number", "min": 0, "max": 10},
                                  "channel": {"type": "enum", "values": list(CHANNELS)},
                                  "simulated": {"type": "bool", "default": False},
                                  "by_audit": {"type": "bool", "default": False}}},
                              "default": []},
        "mercy_events": {"type": "list", "min_items": 0, "max_items": 5, "source": "user",
                         "label": {"en": "Mercy events (A.4)", "ru": "События милосердия (A.4)"},
                         "help": {"en": "magnitude: VEI for eruption, metres for asteroid, lethality % for pandemic; crisis_scope_days: "
                                        "Crisis Scope declared by DKP-4-CRISIS-001 (0 = none)",
                                  "ru": "magnitude: VEI извержения, метры астероида, летальность % пандемии; crisis_scope_days: "
                                        "кризисный контур по DKP-4-CRISIS-001 (0 = не объявлен)"},
                         "items": {"type": "object", "fields": {
                             "day": {"type": "int", "min": 0, "max": 1500},
                             "kind": {"type": "enum", "values": ["eruption", "asteroid", "pandemic", "natural_b_drop"]},
                             "magnitude": {"type": "number", "min": 0, "max": 10 ** 4},
                             "ptl_verified": {"type": "bool", "default": True},
                             "crisis_scope_days": {"type": "int", "min": 0, "max": 3650}}},
                         "default": [MERCY0]},
        "calibration_bundle": {"type": "enum", "values": BUNDLE_STATES, "default": "none", "source": "missing",
                               "label": {"en": "Valid L8 calibration bundle attached (none exists, F-014)",
                                         "ru": "Действующий пакет калибровки L8 (нет, F-014)"}},
        "b_enforcement": {"type": "enum", "values": ["code_a1", "oracle_section_12"], "default": "code_a1", "source": "hypothesis",
                          "label": {"en": "Without a bundle, does B(t) < B_min activate the Kill Switches? (F-036)",
                                    "ru": "Без пакета включает ли B(t) < B_min рубильники? (F-036)"}},
        "level2_role": {"type": "enum", "values": ["unspecified", "provenance_check", "testimony_as_data"], "default": "unspecified",
                        "source": "user", "label": {"en": "What Level 2 human validators contribute (F-028)",
                                                    "ru": "Что вносят люди-валидаторы уровня 2 (F-028)"}},
        "council_power": {"type": "enum", "values": ["unspecified", "rule_bound_severity", "discretionary_emergency_authority"],
                          "default": "unspecified", "source": "user",
                          "label": {"en": "Declared power of the Council of Crisis Mercy (F-032)", "ru": "Объявленные полномочия Совета (F-032)"}},
        "mercy_reading": {"type": "enum", "values": ["bounded_by_crisis_scope", "fixed_180_days"], "default": "bounded_by_crisis_scope",
                          "source": "hypothesis", "label": {"en": "Mercy duration reading (F-027)", "ru": "Чтение срока милосердия (F-027)"}},
        "council": {"type": "object", "source": "user", "label": {"en": "Council of Crisis Mercy pool", "ru": "Пул Совета кризисного милосердия"},
                    "fields": {"eligible_scientists": {"type": "int", "min": 0, "max": 10 ** 6, "default": 1000}},
                    "default": {"eligible_scientists": 1000}},
        "council_actions": {"type": "list", "min_items": 0, "max_items": 10, "source": "user",
                            "label": {"en": "Council actions", "ru": "Действия Совета"},
                            "items": {"type": "object", "fields": {"day": {"type": "int", "min": 0, "max": 1500},
                                                                   "action": {"type": "enum", "values": list(COUNCIL_ACTIONS)}}},
                            "default": [{"day": 150, "action": "severity_reduction"}, {"day": 160, "action": "create_authority"}]},
        "regions": {"type": "list", "min_items": 1, "max_items": 10, "source": "user",
                    "label": {"en": "States (GDP, assets, integration phase)", "ru": "Государства (ВВП, активы, фаза интеграции)"},
                    "items": {"type": "object", "fields": {
                        "id": {"type": "str"}, "gdp": {"type": "number", "min": 0.001, "max": 10 ** 9},
                        "assets": {"type": "number", "min": 0, "max": 10 ** 12},
                        "phase": {"type": "enum", "values": ["phase_0", "phase_1", "phase_2", "phase_3"], "default": "phase_3"}}},
                    "default": REGIONS},
        "stake_rate": {"type": "number", "min": 0.0001, "max": 1, "default": 0.05, "source": "missing",
                       "label": {"en": "Stake as a share of GDP", "ru": "Залог как доля ВВП"},
                       "help": {"en": "§7.1: 'proportional to GDP' — the constant is not given.", "ru": "§7.1: 'пропорционален ВВП' — коэффициент не задан."}},
        "global_growth": {"type": "number", "min": -1, "max": 1, "default": 0.03, "source": "user",
                          "label": {"en": "Global GDP growth per year", "ru": "Рост мирового ВВП в год"}},
        "aggressions": {"type": "list", "min_items": 0, "max_items": 10, "source": "user",
                        "label": {"en": "Aggressions", "ru": "Агрессии"},
                        "items": {"type": "object", "fields": {"day": {"type": "int", "min": 0, "max": 1500}, "region": {"type": "str"},
                                                               "recorded": {"type": "bool", "default": True},
                                                               "weapons": {"type": "bool", "default": True},
                                                               "damage": {"type": "number", "min": 0, "max": 10 ** 9}}},
                        "default": [{"day": 60, "region": "east", "recorded": True, "weapons": True, "damage": 100.0}]},
        "indicator_drops": {"type": "list", "min_items": 0, "max_items": 10, "source": "user",
                            "label": {"en": "Monthly indicator drops (Snap)", "ru": "Месячные падения показателей (Snap)"},
                            "items": {"type": "object", "fields": {"day": {"type": "int", "min": 0, "max": 1500}, "region": {"type": "str"},
                                                                   "drop": {"type": "number", "min": 0, "max": 1},
                                                                   "aggressor": {"type": "str", "default": "unidentified"}}},
                            "default": [{"day": 60, "region": "south", "drop": 0.12, "aggressor": "east"}]},
        "nodes": {"type": "list", "min_items": 1, "max_items": 20, "source": "user",
                  "label": {"en": "Network nodes", "ru": "Узлы сети"},
                  "items": {"type": "object", "fields": {
                      "id": {"type": "str"}, "role": {"type": "enum", "values": ["startup", "wild", "critical"]},
                      "bloc": {"type": "str"}, "nuclear": {"type": "enum", "values": ["yes", "equivalent", "no"]},
                      "energy_mwh_year": {"type": "number", "min": 0, "max": 10 ** 7},
                      "energy_type": {"type": "enum", "values": list(ENERGY_TYPES) + ["other"]},
                      "ptl_confirmed": {"type": "bool", "default": True},
                      "online_day": {"type": "int", "min": -1, "max": 1500, "default": 0},
                      "seized_day": {"type": "int", "min": -1, "max": 1500, "default": -1}}},
                  "default": NODES},
        "network_gdp_share": {"type": "number", "min": 0, "max": 1, "default": 0.05, "source": "user",
                              "label": {"en": "Network share of World GDP", "ru": "Доля сети в мировом ВВП"}},
        "dead_man_share": {"type": "number", "min": 0.5, "max": 1, "default": 0.5, "source": "missing",
                           "label": {"en": "Share of Peace Stakes burned (A.3 '≥ 50%')", "ru": "Доля сжигаемых залогов (A.3 '≥ 50%')"}},
        "ownership": {"type": "list", "min_items": 0, "max_items": 10, "source": "user",
                      "label": {"en": "Owners of oracle infrastructure", "ru": "Владельцы инфраструктуры оракулов"},
                      "items": {"type": "object", "fields": {
                          "holder": {"type": "str"}, "l0_share": {"type": "number", "min": 0, "max": 1},
                          "geo_share": {"type": "number", "min": 0, "max": 1},
                          "stake": {"type": "number", "min": 0, "max": 10 ** 12, "default": 0.0},
                          "holds": {"type": "list", "min_items": 0, "max_items": 5, "default": [],
                                    "items": {"type": "object", "fields": {"entity": {"type": "str"},
                                                                           "share": {"type": "number", "min": 0, "max": 1}}}}}},
                      "default": [{"holder": "orbital_a", "l0_share": 0.005, "geo_share": 0.0, "stake": 10.0, "holds": []},
                                  {"holder": "fund_b", "l0_share": 0.001, "geo_share": 0.01, "stake": 5.0,
                                   "holds": [{"entity": "orbital_a", "share": 0.2}]}]},
        "connections": {"type": "list", "min_items": 0, "max_items": 10, "source": "user",
                        "label": {"en": "Territories applying to connect (A.5)", "ru": "Территории, просящие подключения (A.5)"},
                        "items": {"type": "object", "fields": {
                            "territory": {"type": "str"}, "day": {"type": "int", "min": 0, "max": 1500},
                            "mechanism": {"type": "enum", "values": ["referendum", "legislative_act", "charter_ratification"]},
                            "yes_share": {"type": "number", "min": 0, "max": 1, "default": 0.0},
                            "stake_deposited": {"type": "bool", "default": True}}},
                        "default": [{"territory": "island_t", "day": 200, "mechanism": "referendum", "yes_share": 0.7,
                                     "stake_deposited": True}]},
        "seed": {"type": "int", "min": 0, "max": 2 ** 31 - 1, "default": 7, "source": "hypothesis",
                 "label": {"en": "Sortition seed", "ru": "Зерно жеребьёвки"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        days = r["days"]
        names = [x["id"] for x in r["regions"]] + [x["id"] for x in r["nodes"]] + [x["bloc"] for x in r["nodes"]] + \
            [o["holder"] for o in r["ownership"]] + [c["territory"] for c in r["connections"]] + \
            [f["flight"] for f in r["drone_uploads"]] + r["external_feeds"]
        for x in names:
            if not _ID.fullmatch(x):
                p.append(f"input: identifier {x!r} must be lowercase letters, digits or _")
        for key, ids in (("regions", [x["id"] for x in r["regions"]]), ("nodes", [x["id"] for x in r["nodes"]]),
                         ("ownership", [o["holder"] for o in r["ownership"]])):
            if len(set(ids)) != len(ids):
                p.append(f"input.{key}: repeated id")
        for key in ("ptl_segments", "equation_segments"):
            fd = [s["from_day"] for s in r[key]]
            if fd[0] != 0 or any(b <= a for a, b in zip(fd, fd[1:])):
                p.append(f"input.{key}: from_day must start at 0 and increase")
            if fd[-1] >= days:
                p.append(f"input.{key}: from_day beyond the horizon")
        w = r["level_weights"]
        if abs(w["l0"] + w["l1"] + w["l2"] - 1) > 1e-9:
            p.append("input.level_weights: weights must sum to 1 (H-CS-2)")
        reg = {x["id"] for x in r["regions"]}
        for a in r["aggressions"]:
            if a["region"] not in reg:
                p.append(f"input.aggressions: unknown region {a['region']!r}")
        for s in r["indicator_drops"]:
            if s["region"] not in reg or s["aggressor"] not in reg | {"unidentified"}:
                p.append(f"input.indicator_drops: unknown region or aggressor in {s!r}")
        for key, items in (("aggressions", r["aggressions"]), ("indicator_drops", r["indicator_drops"]),
                           ("mercy_events", r["mercy_events"]), ("council_actions", r["council_actions"]),
                           ("parameter_changes", r["parameter_changes"]), ("connections", r["connections"])):
            if any(x["day"] >= days for x in items):
                p.append(f"input.{key}: day beyond the horizon")
        if len({a["region"] for a in r["aggressions"]}) != len(r["aggressions"]):
            p.append("input.aggressions: one aggression per region")
        own = {o["holder"]: o for o in r["ownership"]}
        for o in r["ownership"]:
            for x in o["holds"]:
                if x["entity"] not in own or x["entity"] == o["holder"]:
                    p.append(f"input.ownership: {o['holder']} holds an unknown entity {x['entity']!r}")

        def cyc(h, path):
            if h in path:
                return True
            return any(cyc(x["entity"], path | {h}) for x in own.get(h, {"holds": []})["holds"] if x["entity"] in own)
        if not p and any(cyc(h, set()) for h in own):
            p.append("input.ownership: holding chains must not form a cycle")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        ks = [{"day": m.arrived_at, **m.value} for m in msgs if m.source == "KILLSWITCH"]
        outputs = {"kill_switches": ks,
                   "mercy": [{"day": m.arrived_at, **m.value} for m in msgs if m.source == "MERCY"],
                   "arbitration": [{"day": m.arrived_at, **m.value} for m in msgs if m.source == "ARBITRATION"],
                   "network": [{"day": m.arrived_at, **m.value} for m in msgs if m.source == "NETWORK"],
                   "violations": sorted(c.requirement_id for c in res if c.status == FAIL),
                   "unknown": sorted(c.requirement_id for c in res if c.status == UNKNOWN),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        act = [k for k in ks if k.get("all_kill_switches") == "active"]
        e = [{"en": f"{len(log)} events; all Kill Switches first active on day {act[0]['day'] if act else '—'}; "
                    f"violated: {', '.join(outputs['violations']) or 'none'}; undecided: {', '.join(outputs['unknown']) or 'none'}.",
              "ru": f"{len(log)} событий; все рубильники впервые включены в день {act[0]['day'] if act else '—'}; "
                    f"нарушены: {', '.join(outputs['violations']) or 'нет'}; не решено: {', '.join(outputs['unknown']) or 'нет'}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        act = [k["day"] for k in outputs["kill_switches"] if k.get("all_kill_switches") == "active"]
        return {"violations": len(outputs["violations"]), "unknown": len(outputs["unknown"]),
                "kill_switch_day": act[0] if act else -1}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        quiet = {"ptl_segments": [SEG0], "mercy_events": [], "aggressions": [], "indicator_drops": [], "council_actions": [],
                 "connections": [], "drone_uploads": [], "external_feeds": []}
        bad_eq = [{"from_day": 0, "dw_dt": 1.0, "e": 1.0, "t": 1.0}, {"from_day": 100, "dw_dt": 0.1, "e": 1.0, "t": 1.0}]
        return {
            "natural_drop_with_mercy": {},
            "anthropogenic_drop": {"ptl_segments": [SEG0, dict(SEG_DROP, cause="anthropogenic")]},
            "quiet_world": quiet,
            "mercy_shorter_crisis_scope": {"mercy_events": [dict(MERCY0, crisis_scope_days=90)]},
            "mercy_fixed_180_reading": {"mercy_events": [dict(MERCY0, crisis_scope_days=90)], "mercy_reading": "fixed_180_days"},
            "mercy_without_crisis_scope": {"mercy_events": [dict(MERCY0, crisis_scope_days=0)], "council_actions": []},
            "eruption_vei_7": {**quiet, "mercy_events": [{"day": 50, "kind": "eruption", "magnitude": 7, "crisis_scope_days": 365}],
                               "aggressions": [{"day": 60, "region": "east", "recorded": True, "weapons": False, "damage": 0.0}]},
            "oracle_section_12_reading": {"b_enforcement": "oracle_section_12"},
            "bundle_attached": {"calibration_bundle": "valid"},
            "expired_bundle": {"calibration_bundle": "expired"},
            "at_threshold": {"ptl_segments": [SEG0, {"from_day": 120, "l0": 0.68, "l1": 0.68, "l2": 0.68, "cause": "natural"}]},
            "provenance_validators": {"level2_role": "provenance_check"},
            "human_testimony_as_ptl": {"ptl_segments": [SEG0], "mercy_events": [], "council_actions": [], "level2_role": "testimony_as_data"},
            "rule_bound_council": {"ptl_segments": [SEG0], "council_power": "rule_bound_severity",
                                  "mercy_events": [{"day": 50, "kind": "eruption", "magnitude": 7, "crisis_scope_days": 365}]},
            "declared_discretionary_council": {"ptl_segments": [SEG0], "council_power": "discretionary_emergency_authority",
                                              "mercy_events": [{"day": 50, "kind": "eruption", "magnitude": 7, "crisis_scope_days": 365}]},
            "b_recovers": {"ptl_segments": [SEG0, SEG_DROP, {"from_day": 330, "l0": 0.70, "l1": 0.70, "l2": 0.70, "cause": "natural"}]},
            "unresolved_divergence": {"ptl_segments": [SEG0, {"from_day": 200, "l0": 0.70, "l1": 0.62, "l2": 0.70, "cause": "natural"}],
                                      "mercy_events": [], "council_actions": []},
            "resolved_divergence": {"ptl_segments": [SEG0, {"from_day": 200, "l0": 0.70, "l1": 0.62, "l2": 0.70, "cause": "natural"},
                                                     {"from_day": 205, "l0": 0.70, "l1": 0.70, "l2": 0.70, "cause": "natural"}],
                                    "mercy_events": [], "council_actions": []},
            "unconfirmed_spare_node": {"nodes": NODES + [_node("spare_1", "critical", "bloc_b", ptl_confirmed=False)]},
            "human_weight_zero": {"level_weights": {"l0": 0.75, "l1": 0.25, "l2": 0.0}},
            "tuning_attempts": {"parameter_changes": [
                {"day": 10, "parameter": "k", "value": 1.2, "channel": "on_chain"},
                {"day": 20, "parameter": "alpha", "value": 2.5, "channel": "financial"},
                {"day": 30, "parameter": "B_min", "value": 0.6, "channel": "upgrade"},
                {"day": 40, "parameter": "k", "value": 0.98, "channel": "upgrade", "simulated": True, "by_audit": True}]},
            "equation_violated_181_days": {**quiet, "equation_segments": bad_eq + [{"from_day": 281, "dw_dt": 1.0, "e": 1.0, "t": 1.0}]},
            "equation_violated_180_days": {**quiet, "equation_segments": bad_eq + [{"from_day": 280, "dw_dt": 1.0, "e": 1.0, "t": 1.0}]},
            "indirect_ownership_breach": {"ptl_segments": [SEG0], "mercy_events": [], "council_actions": [], "ownership": [
                {"holder": "orbital_a", "l0_share": 0.005, "geo_share": 0.0, "stake": 10.0, "holds": []},
                {"holder": "fund_b", "l0_share": 0.003, "geo_share": 0.0, "stake": 5.0, "holds": [{"entity": "orbital_a", "share": 1.0}]}]},
            "node_seized": {"nodes": NODES[:2] + [dict(NODES[2], seized_day=250)] + NODES[3:]},
            "phase_1_aggressor": {"regions": REGIONS[:2] + [dict(REGIONS[2], phase="phase_1")]},
            "connection_by_legislative_act": {"connections": [{"territory": "island_t", "day": 200, "mechanism": "legislative_act",
                                                               "stake_deposited": True}]},
            "insufficient_assets": {"regions": REGIONS[:2] + [dict(REGIONS[2], assets=500.0)]},
            "unidentified_aggressor": {"indicator_drops": [{"day": 60, "region": "south", "drop": 0.12}]},
            "nuclear_equivalent": {"nodes": [dict(x, nuclear="equivalent") if x["bloc"] == "bloc_e" else x for x in NODES]},
            "faulty_network": {"faults": ["ignore_b_min", "accept_late_hash", "execute_inadmissible", "no_slashing", "flat_stake"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"weights_not_summing": {"level_weights": {"l0": 0.7, "l1": 0.2, "l2": 0.2}},
                "segments_not_from_zero": {"ptl_segments": [dict(SEG0, from_day=5)]},
                "unknown_region": {"aggressions": [{"day": 1, "region": "west", "damage": 1.0}]},
                "ownership_cycle": {"ownership": [{"holder": "a", "l0_share": 0.0, "geo_share": 0.0, "holds": [{"entity": "b", "share": 0.5}]},
                                                  {"holder": "b", "l0_share": 0.0, "geo_share": 0.0, "holds": [{"entity": "a", "share": 0.5}]}]},
                "bad_identifier": {"regions": [{"id": "North Region", "gdp": 1.0, "assets": 1.0}]}}
