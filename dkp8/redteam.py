"""Red-team models for the v3 remediation proposals T1-T7 (critic registry v3, sha256 6cb827ac...; 2026-11-18).

Every model here is a SYNTHETIC, deterministic illustration of how a rule behaves under valid operation, attack,
partial failure and compound attack. It tests the logic of a proposal - which subjects are affected, who gains
authority, whether a missing input can turn into enforcement - never physical truth. Numbers are fixtures, not
measurements; where a bound cannot be computed it is reported as UNKNOWN and treated as blocking.

Public entry point: :func:`run_all` returns one record per scenario; ``tests/dkp8/test_redteam.py`` pins them.
"""
from __future__ import annotations

import hashlib
from fractions import Fraction
from itertools import combinations
from typing import Any, Dict, Iterable, List, Optional, Set

from dkp8 import ed25519, trust
from dkp8.canonical import canonical, digest

LABEL = "SYNTHETIC RED-TEAM MODEL - rule logic only; not empirical evidence; no operational claim"
UNKNOWN = "UNKNOWN"


# ── T1: collective enforcement and obsolete authority ───────────────────────────────────────────────────────────

def regional_kill_switch(population: int, aggressors: int, essential_share: Fraction = Fraction(1)) -> Dict[str, Any]:
    """Code Art. 8.1 / Glossary 'Kill Switch Law': the violating region is disconnected from financial, energy and
    logistical infrastructure. Everyone who depends on that infrastructure is affected, attributable or not."""
    affected = population
    uninvolved = population - aggressors
    return {"mechanism": "regional Kill Switch (Code 8.1)", "affected": affected, "uninvolved_affected": uninvolved,
            "essential_services_removed_from_uninvolved": int(uninvolved * essential_share),
            "violates": [inv for inv, hit in (("ANTITERROR no collective punishment (TXT 3776)", uninvolved > 0),
                                              ("JUSTICE isolation targeted and minimal (TXT 2289-2299)", uninvolved > 0),
                                              ("LABOR survival access not conditional (TXT 3402)", essential_share > 0 and uninvolved > 0))
                         if hit]}


def proportional_liability(damage: Fraction, collateral: Fraction, multiplier: Optional[Fraction]) -> Dict[str, Any]:
    """Code Art. 8.2: write-off of the aggressor's assets = 10 x damage. Proposal: only the aggressor's own pledged
    collateral, bounded by proven damage. Proportionality (IDENTITY 1731: 'proportional to measurable causal
    contribution') is checked as liability / proven damage == 1 for restitution-type liability."""
    if multiplier is None:
        liability = min(collateral, damage)
    else:
        liability = damage * multiplier
    uncovered = max(Fraction(0), liability - collateral)
    return {"liability": liability, "ratio_to_damage": (liability / damage) if damage else UNKNOWN,
            "taken_beyond_collateral": uncovered, "unpaid_damage": max(Fraction(0), damage - min(collateral, liability)),
            "proportional": damage > 0 and liability <= damage}


def composite_index_trigger(true_inputs: List[Fraction], manipulated: Set[int], shift: Fraction, b_min: Fraction,
                            trigger_active: bool, regions: int) -> Dict[str, Any]:
    """Code A.1 (TXT 273): 'if B(t) < B_min, all Kill Switches activate simultaneously' versus ORACLE §12 (TXT 737):
    B(t) informational only until a valid L8 bundle exists. No B(t) model exists, so any monotone aggregate is a
    stand-in; the mean is used. An attacker who shifts a few inputs can cross B_min."""
    observed = [x - shift if i in manipulated else x for i, x in enumerate(true_inputs)]
    b_true = sum(true_inputs, Fraction(0)) / len(true_inputs)
    b_obs = sum(observed, Fraction(0)) / len(observed)
    fires = trigger_active and b_obs < b_min
    return {"b_true": b_true, "b_observed": b_obs, "true_state_above_min": b_true >= b_min, "kill_switches_fired": fires,
            "regions_disconnected": regions if fires else 0, "blast_radius": "GLOBAL" if fires else "NONE",
            "manipulated_inputs": len(manipulated), "of_inputs": len(true_inputs)}


def dead_man_switch(stakers: int, seized_nodes: int, staged_by_insider: bool, active: bool) -> Dict[str, Any]:
    """Appendix A.3.3: seizure of any node burns >= 50% of all Peace Stakes globally and pays the remaining nodes."""
    fires = active and seized_nodes > 0
    return {"fires": fires, "stakers_losing": (stakers + 1) // 2 if fires else 0,
            "beneficiaries": "remaining nodes" if fires else None,
            "insider_gain": fires and staged_by_insider, "uninvolved_losing": ((stakers + 1) // 2) if fires else 0}


def authority_after_failure(mechanism: str) -> Dict[str, Any]:
    """Who may act when the system fails. Canon: PATCH 4.1 'No Fallback Authority' (TXT 5073-5081), 'DKP either
    operates correctly or does not operate' (TXT 5184-5191); A.4 Mercy 'SHALL NOT create new ... authorities'."""
    table = {
        "A.1a six-node manual control": {"new_normative_authority": True, "bounded_scope": False, "can_restore_enforcement": True},
        "A.4 Council of Crisis Mercy (control + discretion)": {"new_normative_authority": True, "bounded_scope": False, "can_restore_enforcement": UNKNOWN},
        "ORACLE 14 Mercy deferral (severity only, PTL-confirmed)": {"new_normative_authority": False, "bounded_scope": True, "can_restore_enforcement": False},
        "proposal: enumerated infrastructure operations only": {"new_normative_authority": False, "bounded_scope": True, "can_restore_enforcement": False},
        "external emergency operator (outside DKP)": {"new_normative_authority": False, "bounded_scope": True, "can_restore_enforcement": False,
                                                       "note": "acts under its own law; its acts are not DKP outputs"},
    }
    r = dict(table[mechanism])
    r["violates_no_fallback_authority"] = r["new_normative_authority"] is True or r["can_restore_enforcement"] is True
    return r


# ── T2: Canonical State Manifest (prototype for testing the proposal; not a normative instrument) ──────────────

def genesis(signers: Dict[str, bytes], threshold: int, protocols: Dict[str, str]) -> Dict[str, Any]:
    keys = {name: ed25519.public_key(seed).hex() for name, seed in signers.items()}
    body = {"seq": 0, "prev": None, "protocols": protocols, "authorizers": keys, "threshold": threshold,
            "founding_assumption": "the genesis signer set and threshold are a declared convention of this branch"}
    return {"body": body, "signatures": {}}


def transition(prev: Dict[str, Any], protocols: Dict[str, str], signer_seeds: Dict[str, bytes]) -> Dict[str, Any]:
    body = {"seq": prev["body"]["seq"] + 1, "prev": digest(prev["body"]), "protocols": protocols,
            "authorizers": prev["body"]["authorizers"], "threshold": prev["body"]["threshold"],
            "founding_assumption": prev["body"]["founding_assumption"]}
    sigs = {name: ed25519.sign(seed, canonical(body)).hex() for name, seed in signer_seeds.items()}
    return {"body": body, "signatures": sigs}


def verify_chain(chain: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Integrity (hash links), origin (signatures by the genesis authorizers) and authorization (threshold) - three
    separate properties. Legitimacy of the genesis convention itself is NOT verifiable here."""
    if not chain or chain[0]["body"]["seq"] != 0:
        return {"state": "INVALID", "reason": "no genesis"}
    keys, threshold = chain[0]["body"]["authorizers"], chain[0]["body"]["threshold"]
    for prev, cur in zip(chain, chain[1:]):
        b = cur["body"]
        if b["prev"] != digest(prev["body"]) or b["seq"] != prev["body"]["seq"] + 1:
            return {"state": "INVALID", "reason": f"broken link at seq {b['seq']}", "integrity": False}
        if b["authorizers"] != keys or b["threshold"] != threshold:
            return {"state": "INVALID", "reason": "authorizer set changed outside a root transition", "integrity": True}
        good = [n for n, s in cur["signatures"].items() if n in keys and
                ed25519.verify(bytes.fromhex(keys[n]), canonical(b), bytes.fromhex(s))]
        if len(set(good)) < threshold:
            return {"state": "UNAUTHORIZED", "reason": f"seq {b['seq']}: {len(set(good))} of {threshold} valid signatures",
                    "integrity": True, "origin": bool(good)}
    return {"state": "VALID", "head": digest(chain[-1]["body"]), "seq": chain[-1]["body"]["seq"], "integrity": True,
            "origin": True, "authorized": True, "legitimacy": "FOUNDING_ASSUMPTION (not verifiable inside the system)"}


def resolve_heads(chains: List[List[Dict[str, Any]]], last_seen_seq: int) -> Dict[str, Any]:
    """Two valid chains from the same genesis with different heads at the same or later sequence = competing
    authorized histories: dependent enforcement is NON_ENFORCEABLE. A valid chain shorter than the last seen
    sequence is a rollback. Timestamps, repository ownership or node preference never break ties."""
    valid = [c for c in chains if verify_chain(c)["state"] == "VALID"]
    if not valid:
        return {"state": "NON_ENFORCEABLE", "reason": "no valid authorized chain"}
    if any(c[-1]["body"]["seq"] < last_seen_seq for c in valid) and len({digest(c[-1]["body"]) for c in valid}) == 1:
        return {"state": "NON_ENFORCEABLE", "reason": "rollback below the last seen sequence"}
    heads = {digest(c[-1]["body"]) for c in valid if c[-1]["body"]["seq"] >= last_seen_seq}
    if len(heads) > 1:
        return {"state": "NON_ENFORCEABLE", "reason": "competing authorized histories (fork)"}
    if not heads:
        return {"state": "NON_ENFORCEABLE", "reason": "rollback below the last seen sequence"}
    return {"state": "VALID", "head": heads.pop()}


# ── T3 / T6: attribution ────────────────────────────────────────────────────────────────────────────────────────

def attribute(contributions: Dict[str, Fraction], identifiability: Fraction) -> Dict[str, Any]:
    """Each subject is attributable only if its own contribution is identifiable (>= threshold). Below it: NO
    attribution for that subject (IDENTITY 4.1 NO_ATTRIBUTION), the impact record is kept."""
    total = sum(contributions.values(), Fraction(0))
    attributed = {s: c for s, c in contributions.items() if c >= identifiability}
    return {"impact_recorded": total, "attributed": attributed,
            "unattributed_share": total - sum(attributed.values(), Fraction(0)),
            "state": "ATTRIBUTED" if attributed else "NO_ATTRIBUTION", "liability_imposed_on_unidentified": False}


def resource_cap(load_history: List[Fraction], unattributed: Fraction, cap_growth: Fraction,
                 authorized_by: Optional[str], survival_floor: Fraction, applies_to: str = "resource") -> Dict[str, Any]:
    """Prospective protective limit on further load growth of a shared resource with cumulative unattributed damage.
    Fails the collective-sanction test if it is retrospective, addressed to persons, cuts below the survival floor or
    has no independent authorization."""
    current = load_history[-1]
    limit = current * (1 + cap_growth)
    problems = []
    if applies_to != "resource":
        problems.append("addressed to subjects, not to the resource")
    if limit < survival_floor:
        problems.append("limit below the survival floor")
    if authorized_by is None:
        problems.append("no independent authorization (who may impose the limit is undefined)")
    return {"limit": limit, "retrospective": False, "problems": problems,
            "verdict": "NEEDS_AUTHOR_DECISION" if problems == ["no independent authorization (who may impose the limit is undefined)"]
            else ("BLOCKED" if problems else "CONDITIONAL_PASS")}


def combine_models(estimates: List[Dict[str, Any]], max_disagreement: Fraction) -> Dict[str, Any]:
    """Models sharing structural assumptions count as one; disagreement above the bound gives UNATTRIBUTABLE,
    never an average (critic case 1 additions (a), (b))."""
    groups: Dict[frozenset, List[Fraction]] = {}
    for e in estimates:
        groups.setdefault(frozenset(e["assumptions"]), []).append(Fraction(e["value"]))
    independent = len(groups)
    reps = [vals[0] for vals in groups.values()]
    if independent < 2:
        return {"independent_models": independent, "state": "INFORMATIONAL_ONLY", "value": None}
    spread = max(reps) - min(reps)
    if spread > max_disagreement:
        return {"independent_models": independent, "state": "UNATTRIBUTABLE", "value": None, "spread": spread}
    return {"independent_models": independent, "state": "ATTRIBUTED", "value": min(reps), "spread": spread}


def recovery_after_halt(outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Outputs produced (or attempted) during a halt never become enforceable by recovery: they need fresh adjudication
    under the rules in force at the time of the act (ERROR/EPISTEMIC-TRANSITIONS; critic case 12 (a))."""
    promoted = [o for o in outputs if o.get("produced_during_halt") and o.get("auto_enforce_after_recovery")]
    return {"auto_promoted": len(promoted), "require_fresh_adjudication": sum(1 for o in outputs if o.get("produced_during_halt")),
            "records_kept": sum(1 for o in outputs if o.get("kind") == "record")}


def reserve_lawfare(reserve: Fraction, claims: List[Dict[str, Any]], tariff: Fraction) -> Dict[str, Any]:
    """Parametric compensation reserve: pays only formally reversed verdicts at a published tariff, life-critical first.
    Mass claims without reversal drain nothing; exhaustion state is reported, not hidden."""
    paid, left, refused = [], reserve, 0
    for c in sorted(claims, key=lambda c: (not c.get("life_critical"), c["id"])):
        if not c.get("formally_reversed"):
            refused += 1
            continue
        amount = min(tariff, left)
        left -= amount
        paid.append((c["id"], amount))
    unpaid = [c["id"] for c in claims if c.get("formally_reversed") and dict(paid).get(c["id"], 0) < tariff]
    return {"paid": len([p for p in paid if p[1] > 0]), "refused_without_reversal": refused, "left": left,
            "exhausted": left == 0 and bool(unpaid), "unpaid_reversed": unpaid,
            "funding_rule": UNKNOWN, "verdict": "NEEDS_AUTHOR_DECISION"}


# ── T4: electorate snapshot and branching ──────────────────────────────────────────────────────────────────────

def ratify(electorate: Dict[str, str], active: Set[str], yes: Set[str], threshold: Fraction, snapshot: bool,
           owner_graph: bool) -> Dict[str, Any]:
    """67% ratification (AXIOMS TXT 1256). ``electorate`` maps node -> owner. Without a snapshot the denominator is
    the nodes active at the end of the vote; with a snapshot it is the electorate at opening. With an owner graph,
    one owner = one vote."""
    def count(nodes):
        return len({electorate[n] for n in nodes}) if owner_graph else len(nodes)
    denominator = count(set(electorate) if snapshot else (active & set(electorate)))
    ayes = count(yes & set(electorate) & (set(electorate) if snapshot else active))
    share = Fraction(ayes, denominator) if denominator else Fraction(0)
    return {"ayes": ayes, "denominator": denominator, "share": share, "passes": denominator > 0 and share >= threshold}


def fork(participants: Dict[str, Fraction], consenting: Set[str], ownership_follows_protocol: bool) -> Dict[str, Any]:
    """A root change by branching: consenting participants move to the new branch with their own assets. If ownership
    followed the protocol, non-consenting participants' assets would move with the majority branch."""
    moved_non_consenting = {p: a for p, a in participants.items() if p not in consenting} if ownership_follows_protocol else {}
    return {"new_branch_assets": sum((participants[p] for p in consenting), Fraction(0)) + sum(moved_non_consenting.values(), Fraction(0)),
            "non_consenting_assets_transferred": sum(moved_non_consenting.values(), Fraction(0)),
            "compulsory_transfer": bool(moved_non_consenting),
            "verdict": "BLOCKED" if moved_non_consenting else "CONDITIONAL_PASS"}


# ── T5: measurement provenance, N_eff and admissibility states ─────────────────────────────────────────────────

def n_eff(sensors: Dict[str, Iterable[str]], unknown: Iterable[str] = ()) -> Dict[str, Any]:
    """Effective independent sources = the largest set of sensors whose failure-domain roots (manufacturer, firmware,
    calibration chain, operator, data processor ...) are pairwise disjoint. Unknown provenance is fail-closed: a sensor
    of unknown provenance is presumed to depend on every known root and on every other unknown sensor, so it can only
    count when it is the sole sensor. Exact search; fine for registry-sized inputs."""
    unknown = set(unknown)
    known_roots = set().union(*(set(r) for s, r in sensors.items() if s not in unknown)) if sensors else set()
    roots = {s: (set(r) | {"UNKNOWN"} | known_roots) if s in unknown else set(r) for s, r in sensors.items()}
    names = sorted(roots)
    best: List[str] = []
    for size in range(len(names), 0, -1):
        for combo in combinations(names, size):
            if all(not (roots[a] & roots[b]) for a, b in combinations(combo, 2)):
                best = list(combo)
                break
        if best:
            break
    return {"n_eff": len(best), "independent_set": best, "sensor_count": len(names)}


STATES = ("NORMAL", "DIVERGENCE_FREEZE", "SYSTEMIC_HALT", "NULL_OUTPUT")


def admissibility_state(domains: Dict[str, Dict[str, Any]], n_eff_min: Optional[int]) -> Dict[str, Any]:
    """Candidate decomposition mapped onto the canonical states: Divergence Event freeze (ORACLE 11, domain-scoped),
    Systemic Halt (ORACLE 13, L2+ blocked, L1 kept), null-output / NO_ENFORCEMENT (CRISIS PATCH, no attribution or
    enforcement outputs). A domain is degraded when its own N_eff falls below N_eff_min or it diverges. The system is
    systemic only if every independent root is degraded - computed from the pre-registered graph, not from routing.
    With N_eff_min undefined nothing is admissible: NULL_OUTPUT."""
    if n_eff_min is None:
        return {"state": "NULL_OUTPUT", "reason": "N_eff_min undefined (specification gap): no admissible enforcement",
                "frozen_domains": sorted(domains)}
    degraded = sorted(d for d, info in domains.items() if info["n_eff"] < n_eff_min or info.get("diverged"))
    if not degraded:
        return {"state": "NORMAL", "frozen_domains": []}
    shared_roots = set.intersection(*(set(info["roots"]) for info in domains.values())) if domains else set()
    if len(degraded) == len(domains) or shared_roots & set().union(*(set(domains[d]["roots"]) for d in degraded)):
        return {"state": "NULL_OUTPUT", "reason": "no independent admissible domain remains", "frozen_domains": sorted(domains)}
    return {"state": "DIVERGENCE_FREEZE", "frozen_domains": degraded}


def restore_request(current: str, requested_by: str, deterministic_trigger_met: bool) -> Dict[str, Any]:
    allowed = deterministic_trigger_met and requested_by == "deterministic_trigger"
    return {"from": current, "restored": allowed and current != "NORMAL",
            "refused_reason": None if allowed else "only the deterministic re-entry conditions restore enforcement; no participant may"}


def detection_and_dispute(divergence: Fraction, threshold: Fraction, stake_required: Optional[Fraction],
                          complainant_funds: Fraction) -> Dict[str, Any]:
    """C11: ORACLE 11 starts arbitration automatically on divergence; Code A.2 attaches a $500M stake. Model: detection
    never needs a stake; the stake only gates contesting the exclusion of a source."""
    detected = divergence > threshold
    can_dispute = stake_required is None or complainant_funds >= stake_required
    return {"detected": detected, "detection_needs_stake": False, "complainant_can_contest_exclusion": can_dispute,
            "wealth_gates_detection": False, "wealth_gates_dispute": stake_required is not None and not can_dispute}


# ── T7: economic and external boundaries ───────────────────────────────────────────────────────────────────────

def ubr_access(need: str, participation_score: Fraction) -> Dict[str, Any]:
    """Critic case 10 criterion: a good is in the guaranteed minimum iff refusing it leads to (a) death, (b) irreversible
    loss of functional capacity or (c) a state that excludes future choice. Code Art. 18.1 ties 'additional benefits'
    to a participation rating; LABOR (TXT 3402) forbids conditioning survival access on labor, obedience, loyalty or
    productivity."""
    guaranteed = need in ("death", "irreversible_loss", "excludes_future_choice")
    return {"guaranteed": guaranteed, "granted": guaranteed or participation_score > 0,
            "depends_on_score": not guaranteed}


def coordination_sanction(signs: Dict[str, bool]) -> Dict[str, Any]:
    """Critic case 14: four observable signs (simultaneity, contractual linkage, dependency asymmetry, causal effect);
    no motive is inferred; fewer than four -> no sanction (recorded for pattern review only)."""
    keys = ("simultaneous_uniform", "contractually_linked", "dependency_asymmetry", "causal_effect")
    present = [k for k in keys if signs.get(k)]
    return {"present": present, "sanction_admissible": len(present) == 4,
            "recorded_for_pattern_review": 0 < len(present) < 4}


def dti_operand(kind: str, value: int) -> Dict[str, Any]:
    """Critic case 11: typed time operands. DTI operands use the author's clarified convention (2026-11-18)."""
    if kind == "DTI":
        if value == 0:
            return {"kind": kind, "epoch": True}
        if value < 0:
            return {"kind": kind, "error": "before the DTI epoch"}
        k = value - 1
        return {"kind": kind, "dy": k // 360 + 1, "doy": k % 360 + 1}
    if kind in ("CALENDAR", "ASTRONOMICAL"):
        return {"kind": kind, "value": value}
    if kind == "OBSERVABLE":
        return {"kind": kind, "requires_declared_fallback": True}
    return {"kind": kind, "error": "untyped operand: the contract is inactive until the type is declared"}


# ── scenario catalogue ─────────────────────────────────────────────────────────────────────────────────────────

def _r(sid, package, cases, collisions, proposal, kind, result, outcome, blast=None):
    return {"id": sid, "package": package, "cases": cases, "collisions": collisions, "proposal": proposal,
            "kind": kind, "outcome": outcome, "blast_radius": blast, "result": result, "label": LABEL}


def run_all() -> List[Dict[str, Any]]:
    F = Fraction
    out: List[Dict[str, Any]] = []
    # T1 - regional Kill Switch and 10x
    ks = regional_kill_switch(population=1_000_000, aggressors=120)
    out.append(_r("T1-KS-current", "T1", [8], ["C2"], "current Code 8.1", "adversarial (aggressor shields behind population)",
                  ks, "BLOCKED: existing rule hits uninvolved population", {"uninvolved_subjects": ks["uninvolved_affected"]}))
    tenx = proportional_liability(F(100), F(400), F(10))
    out.append(_r("T1-10x-on-collateral", "T1", [8], ["C2"], "keep 10x but take it from the aggressor's collateral", "valid",
                  tenx, "BLOCKED: liability 10x proven damage is not proportional even when taken from the aggressor's own collateral",
                  {"taken_beyond_damage": str(tenx["liability"] - F(100))}))
    own = proportional_liability(F(100), F(400), None)
    out.append(_r("T1-collateral-bounded", "T1", [8], ["C2"], "aggressor's own pledged collateral, bounded by proven damage", "valid",
                  own, "CONDITIONAL_PASS: proportional; needs attribution, jurisdiction, ownership, collateral terms", {"uninvolved_subjects": 0}))
    short = proportional_liability(F(900), F(400), None)
    out.append(_r("T1-collateral-insufficient", "T1", [8], ["C2"], "same, collateral smaller than damage", "partial failure",
                  short, "CONDITIONAL_PASS: unpaid damage stays a claim; no spill-over to third parties", {"unpaid_damage": str(short["unpaid_damage"])}))
    # T1 - B(t) trigger (C14)
    inputs = [F(80, 100)] * 9 + [F(72, 100)]
    attack = composite_index_trigger(inputs, manipulated={0, 1, 2}, shift=F(45, 100), b_min=F(68, 100), trigger_active=True, regions=190)
    out.append(_r("T1-Bt-trigger-current", "T1", [4], ["C14", "C4"], "current Code A.1 line 273", "compound (case 3 sensor manipulation + global trigger)",
                  attack, "BLOCKED: 3 of 10 inputs shifted push the stand-in aggregate below B_min while the true state is above it; all regions disconnected",
                  {"regions": attack["regions_disconnected"]}))
    cancelled = composite_index_trigger(inputs, manipulated={0, 1, 2}, shift=F(45, 100), b_min=F(68, 100), trigger_active=False, regions=190)
    out.append(_r("T1-Bt-diagnostic", "T1", [4], ["C14"], "B(t) diagnostic only until L8 calibration (ORACLE 12)", "adversarial",
                  cancelled, "CONDITIONAL_PASS: no enforcement path; requires a canonical transition (T2) that supersedes line 273",
                  {"regions": 0}))
    # T1 - Dead Man Switch
    dms = dead_man_switch(stakers=200, seized_nodes=1, staged_by_insider=True, active=True)
    out.append(_r("T1-DMS-current", "T1", [16], ["C9"], "current A.3.3", "adversarial (staged seizure of own node)",
                  dms, "BLOCKED: one staged seizure burns half of all stakes of uninvolved participants and pays the remaining nodes",
                  {"stakers_losing": dms["stakers_losing"]}))
    out.append(_r("T1-DMS-removed", "T1", [16], ["C9"], "remove DMS; key revocation and exclusion of the seized node", "adversarial",
                  dead_man_switch(200, 1, True, False), "CONDITIONAL_PASS: no collective loss; residual deterrence loss declared; needs T2 transition", {"stakers_losing": 0}))
    # T1 - authority after failure
    for mech in ("A.1a six-node manual control", "A.4 Council of Crisis Mercy (control + discretion)",
                 "ORACLE 14 Mercy deferral (severity only, PTL-confirmed)", "proposal: enumerated infrastructure operations only",
                 "external emergency operator (outside DKP)"):
        res = authority_after_failure(mech)
        out.append(_r(f"T1-authority-{mech[:12]}", "T1", [15, 17], ["C1", "C12"], mech, "partial failure (System Failure / degraded PTL)",
                      res, "BLOCKED" if res["violates_no_fallback_authority"] else "PASS within declared scope", None))
    # T2 - manifest
    seeds = {f"g{i}": hashlib.sha256(f"genesis-{i}".encode()).digest() for i in range(5)}
    g = genesis(seeds, 3, {"DKP-1-IDENTITY-001": "a" * 64})
    t1 = transition(g, {"DKP-1-IDENTITY-001": "b" * 64}, {k: seeds[k] for k in ("g0", "g1", "g2")})
    chain = [g, t1]
    out.append(_r("T2-valid", "T2", [6], [], "hash-chained manifest, 3-of-5 genesis authorizers", "valid", verify_chain(chain), "VALID", None))
    forged = [g, transition(g, {"DKP-1-IDENTITY-001": "c" * 64}, {"g0": seeds["g0"], "x": hashlib.sha256(b"attacker").digest(),
                                                                   "y": hashlib.sha256(b"attacker2").digest()})]
    out.append(_r("T2-forged", "T2", [6], [], "transition signed by non-authorizers", "adversarial", verify_chain(forged), "UNAUTHORIZED -> NON_ENFORCEABLE", None))
    rival = [g, transition(g, {"DKP-1-IDENTITY-001": "d" * 64}, {k: seeds[k] for k in ("g2", "g3", "g4")})]
    out.append(_r("T2-competing-histories", "T2", [6, 18], [], "two authorized transitions from the same state", "adversarial",
                  resolve_heads([chain, rival], last_seen_seq=1), "NON_ENFORCEABLE (fork); no tie-break by time, owner or node", None))
    out.append(_r("T2-rollback", "T2", [6], [], "replay of the genesis state after seq 1 was seen", "adversarial",
                  resolve_heads([[g]], last_seen_seq=1), "NON_ENFORCEABLE (rollback)", None))
    captured = [g, transition(g, {"DKP-1-AXIOMS-001": "e" * 64}, {k: seeds[k] for k in ("g0", "g1", "g3")})]
    out.append(_r("T2-signer-capture", "T2", [6, 18], [], "3 of 5 authorizers captured", "adversarial", verify_chain(captured),
                  "UNTESTABLE inside the system: a captured quorum produces a VALID chain; legitimacy rests on the declared founding convention",
                  {"detectable_internally": False}))
    # T3 - attribution evasion
    evasion = attribute({f"s{i}": F(4, 100) for i in range(50)}, identifiability=F(10, 100))
    out.append(_r("T3-distributed-evasion", "T3", [1], ["C13"], "evaluate attribution under admissible evidence; NO_ATTRIBUTION below threshold",
                  "adversarial (50 actors x 0.04, threshold 0.10)", evasion,
                  "PASS for the attribution rule (no liability on unidentified subjects; impact record kept); cumulative harm unaddressed", {"unattributed": str(evasion["unattributed_share"])}))
    cap = resource_cap([F(100), F(130)], evasion["unattributed_share"], F(0), authorized_by=None, survival_floor=F(60))
    out.append(_r("T3-resource-cap", "T3", [1], [], "prospective cap on load growth of the affected resource", "compound (evasion + cap)",
                  cap, cap["verdict"] + ": who may impose a protective resource limit is undefined", None))
    cap_bad = resource_cap([F(100), F(50)], evasion["unattributed_share"], F(-1, 2), authorized_by="audit", survival_floor=F(60), applies_to="subjects")
    out.append(_r("T3-cap-as-sanction", "T3", [1], [], "cap addressed to residents and below survival floor", "adversarial", cap_bad, cap_bad["verdict"] + ": disguised collective sanction", None))
    # T4 - electorate
    electorate = {f"n{i}": f"o{i}" for i in range(30)}
    yes = {f"n{i}" for i in range(18)}                       # 60% support
    active_after = yes | {"n18", "n19"}                      # 10 dissenters deactivated during the vote
    out.append(_r("T4-deactivation-no-snapshot", "T4", [5], ["C6"], "denominator = currently active nodes", "adversarial (deactivate dissenters)",
                  ratify(electorate, active_after, yes, F(2, 3), snapshot=False, owner_graph=False), "BLOCKED: 60% minority becomes 90% of the active set", None))
    out.append(_r("T4-deactivation-snapshot", "T4", [5], ["C6"], "electorate snapshot at opening", "adversarial (deactivate dissenters)",
                  ratify(electorate, active_after, yes, F(2, 3), snapshot=True, owner_graph=False), "CONDITIONAL_PASS: attack fails (60% < 67%)", None))
    sybil = dict(electorate)
    sybil.update({f"sy{i}": "o0" for i in range(40)})
    out.append(_r("T4-sybil-no-owner-graph", "T4", [5], ["C6"], "snapshot, one node one vote", "adversarial (40 Sybil nodes of one owner)",
                  ratify(sybil, set(sybil), yes | {f"sy{i}" for i in range(40)}, F(2, 3), snapshot=True, owner_graph=False), "BLOCKED: Sybil owner decides", None))
    out.append(_r("T4-sybil-owner-graph", "T4", [5], ["C6"], "snapshot + one owner one vote", "adversarial (40 Sybil nodes of one owner)",
                  ratify(sybil, set(sybil), yes | {f"sy{i}" for i in range(40)}, F(2, 3), snapshot=True, owner_graph=True),
                  "CONDITIONAL_PASS only if the owner graph is truthful; hidden ownership = residual (UNKNOWN)", None))
    out.append(_r("T4-blocking-minority", "T4", [5], [], "34% oppose", "partial failure (deadlock)",
                  ratify(electorate, set(electorate), {f"n{i}" for i in range(19)}, F(2, 3), True, True), "status quo kept: no authority created", None))
    out.append(_r("T4-fork-compulsory", "T4", [18], [], "majority branch takes non-consenting assets", "adversarial",
                  fork({"a": F(70), "b": F(30)}, {"a"}, ownership_follows_protocol=True), "BLOCKED: compulsory transfer of non-consenting assets", None))
    out.append(_r("T4-fork-ownership-stays", "T4", [18], [], "'ownership does not follow the protocol'", "valid",
                  fork({"a": F(70), "b": F(30)}, {"a"}, ownership_follows_protocol=False), "CONDITIONAL_PASS: needs codification + genesis split formula", None))
    # T5 - N_eff
    common = n_eff({"s1": {"fwX", "m1", "opA"}, "s2": {"fwX", "m2", "opB"}, "s3": {"fwX", "m3", "opC"}})
    out.append(_r("T5-common-firmware", "T5", [3, 17], ["C7"], "N_eff by independent failure domains", "adversarial (common-mode firmware)",
                  common, "N_eff = 1 although 3 sensors: common root detected", None))
    indep = n_eff({"s1": {"fw1", "m1", "opA"}, "s2": {"fw2", "m2", "opB"}, "s3": {"fw3", "m3", "opC"}, "s4": {"fw1", "m4", "opD"}})
    out.append(_r("T5-independent", "T5", [3], ["C7"], "same", "valid", indep, "N_eff = 3", None))
    unk = n_eff({"s1": {"fw1"}, "s2": {"fw2"}, "s3": set(), "s4": set()}, unknown={"s3", "s4"})
    out.append(_r("T5-unknown-provenance", "T5", [3], ["C7"], "unknown provenance is fail-closed", "partial failure", unk,
                  "N_eff = 2: sensors of unknown provenance are presumed dependent and add nothing", None))
    out.append(_r("T5-state-no-threshold", "T5", [13, 17], ["C7"], "states with N_eff_min undefined", "partial failure",
                  admissibility_state({"air": {"n_eff": 3, "roots": ["fw1"]}, "water": {"n_eff": 2, "roots": ["fw2"]}}, None),
                  "NULL_OUTPUT: N_eff_min undefined (SPECIFICATION_GAP); nothing enforceable", None))
    local = admissibility_state({"air": {"n_eff": 1, "roots": ["fw1"]}, "water": {"n_eff": 3, "roots": ["fw2"]}}, 2)
    out.append(_r("T5-local-degradation", "T5", [13], [], "domain-scoped freeze", "partial failure", local, "freeze only the independent degraded domain", None))
    systemic = admissibility_state({"air": {"n_eff": 1, "roots": ["fwX"]}, "water": {"n_eff": 3, "roots": ["fwX"]}}, 2)
    out.append(_r("T5-hidden-systemic", "T5", [13], [], "selective routing through a domain sharing the failed root", "adversarial",
                  systemic, "NULL_OUTPUT: shared root makes the loss systemic; routing cannot hide it", None))
    out.append(_r("T5-manual-restore", "T5", [15, 17], ["C1"], "participant asks to restore enforcement", "adversarial",
                  restore_request("NULL_OUTPUT", "consortium", deterministic_trigger_met=False), "refused", None))
    out.append(_r("T5-C11-roles", "T5", [13], ["C11"], "automatic detection; stake only to contest exclusion", "adversarial (poor complainant)",
                  detection_and_dispute(F(9, 100), F(7, 100), F(500_000_000), F(10_000)),
                  "CONDITIONAL_PASS: detection independent of wealth; stake still gates contesting (amount needs author decision)", None))
    # T6
    out.append(_r("T6-shared-assumptions", "T6", [1], [], "two implementations, same structural assumptions", "adversarial",
                  combine_models([{"assumptions": {"linear", "local"}, "value": 30}, {"assumptions": {"linear", "local"}, "value": 31}], F(5)),
                  "INFORMATIONAL_ONLY: one independent model", None))
    out.append(_r("T6-disagreement", "T6", [1], [], "independent models disagree", "partial failure",
                  combine_models([{"assumptions": {"linear"}, "value": 30}, {"assumptions": {"agent-based"}, "value": 70}], F(10)),
                  "UNATTRIBUTABLE (no averaging)", None))
    out.append(_r("T6-recovery", "T6", [12], [], "recovery after NO_ENFORCEMENT", "partial failure",
                  recovery_after_halt([{"produced_during_halt": True, "auto_enforce_after_recovery": True}, {"kind": "record", "produced_during_halt": True}]),
                  "BLOCKED: a design that auto-promotes halt-time outputs (here 1) fails; recovery must re-adjudicate", None))
    out.append(_r("T6-recovery-proposal", "T6", [12], [], "records kept, outputs re-adjudicated under the rules of the time of the act", "valid",
                  recovery_after_halt([{"produced_during_halt": True, "auto_enforce_after_recovery": False}, {"kind": "record", "produced_during_halt": True}]),
                  "PASS within scope: nothing auto-promoted, records preserved", None))
    out.append(_r("T6-reserve-lawfare", "T6", [2], [], "parametric reserve under mass claims", "adversarial (mass lawfare)",
                  reserve_lawfare(F(10), [{"id": i, "formally_reversed": i % 10 == 0, "life_critical": i % 20 == 0} for i in range(100)], F(3)),
                  "NEEDS_AUTHOR_DECISION: funding and exhaustion rules undefined", None))
    # T7
    out.append(_r("T7-ubr", "T7", [10], ["C8"], "criterion (a)-(c)", "adversarial (low participation score)",
                  {"life": ubr_access("death", F(0)), "extra": ubr_access("comfort", F(0))}, "survival access independent of score; Code 18.1 rating applies only beyond (a)-(c)", None))
    out.append(_r("T7-coordination", "T7", [14], [], "four observable signs", "partial evidence (2 of 4)",
                  coordination_sanction({"simultaneous_uniform": True, "contractually_linked": True}), "no sanction", None))
    out.append(_r("T7-dti-operand", "T7", [11], [], "typed time operands", "valid / boundary",
                  {k: dti_operand(*k.split(":")[0:1], int(k.split(":")[1])) for k in ("DTI:0", "DTI:1", "DTI:361", "UNTYPED:5")},
                  "DTI operands follow the clarified convention; untyped operand -> inactive", None))
    return out
