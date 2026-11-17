"""Cross-protocol rules that DKP-8-SIMULATION-001 specifies formally.

* §4: protocols lacking an attached and valid L8 Calibration Bundle are NON-ENFORCEABLE (and the provisions the corpus
  defers to L8 are informational only) - :func:`enforceability`;
* §13: AUDIT verifies deployed against simulated behaviour, flags divergence beyond tolerance and triggers rollback
  or halt - :func:`audit_divergence` (tolerances are calibration values: without them the result is NOT_ESTABLISHED);
* §14: a change to a protocol requires full re-simulation of all dependent protocols - :func:`dependents`, using the
  normative dependencies recorded in the lab registry (exact quotes, checked against World).

Only these interactions are implemented: others are not formally specified in the corpus.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "lab" / "registry"


@lru_cache(maxsize=1)
def documents() -> List[str]:
    return sorted(json.loads(p.read_text(encoding="utf-8"))["doc_id"] for p in (REGISTRY / "requirements").glob("*.json"))


def _normalize(name: str, docs: List[str]) -> Optional[str]:
    if name in docs:
        return name
    hits = [d for d in docs if d.startswith(name + "-") or d.startswith(name)]
    return hits[0] if len(hits) == 1 else None


@lru_cache(maxsize=1)
def graph() -> Dict[str, List[str]]:
    """doc -> documents it depends on (normative_dependencies of its provisions), normalised to registry ids."""
    docs = documents()
    out: Dict[str, Set[str]] = {d: set() for d in docs}
    for p in (REGISTRY / "requirements").glob("*.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        for req in data["requirements"]:
            for dep in req.get("normative_dependencies") or []:
                name = dep if isinstance(dep, str) else (dep.get("doc") or dep.get("document") or dep.get("id") or "")
                target = _normalize(str(name), docs)
                if target and target != data["doc_id"]:
                    out[data["doc_id"]].add(target)
    return {k: sorted(v) for k, v in out.items()}


def dependents(doc: str) -> List[str]:
    """Every document that depends on ``doc`` directly or transitively (§14: all must be re-simulated)."""
    g = graph()
    reverse: Dict[str, Set[str]] = {}
    for src, targets in g.items():
        for t in targets:
            reverse.setdefault(t, set()).add(src)
    seen, todo = set(), [doc]
    while todo:
        for nxt in reverse.get(todo.pop(), ()):
            if nxt not in seen and nxt != doc:
                seen.add(nxt)
                todo.append(nxt)
    return sorted(seen)


def enforceability(bundle_statuses: Iterable[Dict[str, Any]] = (), bundles: Iterable[Dict[str, Any]] = ()) -> List[Dict[str, Any]]:
    """§4 and the corpus's L8 deferrals: which provisions may bind, given the bundles and their statuses."""
    cmap = json.loads((REGISTRY / "calibration_map.json").read_text(encoding="utf-8"))
    covered: Set[str] = set()
    for b, s in zip(bundles, bundle_statuses):
        if s.get("enforceable"):
            covered.add(b["body"]["target"]["protocol_id"])
    rows = []
    for e in cmap["bundle_required"]:
        if e["doc"] == "DKP-8-SIMULATION-001" and e["scope"] != "every protocol":
            continue
        scope = e["scope"]
        doc = e["doc"]
        state = "ENFORCEABLE" if (doc in covered and scope != "every protocol") else "NON-ENFORCEABLE"
        rows.append({"doc": doc, "at": e["at"], "scope": scope, "state": state, "text": e["text"],
                     "reason": "valid authoritative bundle attached" if state == "ENFORCEABLE"
                     else "no valid, authoritatively signed L8 Calibration Bundle"})
    for e in cmap["deferred_to_l8"]:
        rows.append({"doc": e["doc"], "at": e["at"], "scope": e["parameter"],
                     "state": "ENFORCEABLE" if e["doc"] in covered else "UNCALIBRATED",
                     "text": e["text"], "reason": "value defined only by L8 calibration; none exists"
                     if e["doc"] not in covered else "covered by a valid bundle"})
    return rows


def _dec(v):
    try:
        return Decimal(v)
    except (InvalidOperation, TypeError, ValueError):
        return None


def audit_divergence(deployed: Dict[str, List[str]], simulated: Dict[str, List[str]],
                     tolerances: Dict[str, Dict[str, Any]], rollback_available: Optional[bool]) -> Dict[str, Any]:
    """§13: compare deployed with simulated series per metric; flag divergence beyond tolerance; choose the action.

    ``tolerances[metric] = {"value": decimal string, "provenance": {...}}`` - calibration values; a metric without a
    tolerance cannot be judged (NOT_ESTABLISHED), never silently accepted.  Action on divergence: ROLLBACK when a
    tested rollback exists, otherwise HALT (§13 "trigger rollback or halt when required").
    """
    findings, missing = [], []
    for metric in sorted(set(deployed) | set(simulated)):
        d, s = [_dec(x) for x in deployed.get(metric, [])], [_dec(x) for x in simulated.get(metric, [])]
        tol = tolerances.get(metric) or {}
        limit = _dec(tol.get("value"))
        if not d or not s or len(d) != len(s) or None in d or None in s:
            missing.append(f"{metric}: deployed and simulated series missing, unequal or not decimal")
            continue
        if limit is None or not (tol.get("provenance") or {}).get("kind"):
            missing.append(f"{metric}: no calibrated tolerance (DKP8-Q-03)")
            continue
        worst = max(abs(a - b) for a, b in zip(d, s))
        findings.append({"metric": metric, "max_divergence": str(worst), "tolerance": str(limit),
                         "beyond_tolerance": worst > limit})
    flagged = [f for f in findings if f["beyond_tolerance"]]
    if flagged:
        action = "ROLLBACK" if rollback_available else "HALT"
        state = "DIVERGENCE"
    elif missing:
        action, state = None, "NOT_ESTABLISHED"
    else:
        action, state = None, "CONSISTENT"
    return {"state": state, "action": action, "findings": findings, "missing": missing}
