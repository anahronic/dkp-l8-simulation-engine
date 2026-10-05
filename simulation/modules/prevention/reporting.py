"""
Reporting — PREVENTION run summary and deterministic output files.

Output files are written with LF line endings and canonical JSON so that
the same computation yields the same bytes on every platform.  Floats are
written with Python's shortest round-trip repr (hypothesis H-NUM); rounding
happens only in summary.txt, which is for humans and is not part of the
result digest.
"""

from __future__ import annotations

import csv
import json
import math
import os
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List

from simulation.modules.prevention.protocol_adapter import (
    INFORMATIONAL, NO_ATTRIBUTION, POSITIVE, STATUSES, ZERO_MERIT,
)

CSV_COLUMNS = [
    "event_id", "zone_id", "risk_channel", "actor_id", "tick", "dti_day",
    "status", "reason", "SPD", "W", "S", "A", "C", "T", "claim", "linkage_observed",
    "intervention_time", "ta_time", "se_time", "validity_state", "confidence_state",
    "consistency_state", "truth_self_induced", "truth_own_threat",
]


def dumps(obj: Any, indent: int = 2) -> str:
    return json.dumps(obj, sort_keys=True, indent=indent, ensure_ascii=True, allow_nan=False) + "\n"


def write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def summarize(records: List[Dict[str, Any]], event_stats: Dict[str, int], scenario_id: str) -> Dict[str, Any]:
    by_status = Counter(r["status"] for r in records)
    by_reason = Counter(r["reason"] for r in records if r["reason"] is not None)
    subject_totals: Dict[str, List[float]] = defaultdict(list)
    sum_a: Dict[str, List[float]] = defaultdict(list)
    for r in records:
        subject_totals[r["actor_id"]].append(r["SPD"])
        if r["factors"]["A"] is not None:
            sum_a[r["event_id"]].append(r["factors"]["A"])

    own = [r for r in records if r["truth"]["own_threat"]]
    honest = [r for r in records if not r["truth"]["own_threat"]]
    honest_eligible = [r for r in honest if r["factors"]["T"] not in (None, 0.0)]
    honest_decayed = [r for r in honest_eligible if r["factors"]["T"] < 1.0]
    evaluated = [r for r in records if r["status"] in (POSITIVE, ZERO_MERIT, NO_ATTRIBUTION)]
    ambiguity = [r for r in records if r["status"] == NO_ATTRIBUTION and r["reason"] == "attribution_ambiguity"]
    positive = [r for r in records if r["status"] == POSITIVE]

    def frac(a: int, b: int) -> float:
        return a / b if b else 0.0

    return {
        "schema": "dkp-l8-summary/2",
        "scenario_id": scenario_id,
        "events": dict(sorted(event_stats.items())),
        "records_total": len(records),
        "by_status": {s: by_status.get(s, 0) for s in STATUSES},
        "by_reason": dict(sorted(by_reason.items())),
        "total_spd": math.fsum(r["SPD"] for r in records),
        "subject_count": len(subject_totals),
        "subject_totals": {k: math.fsum(v) for k, v in sorted(subject_totals.items())},
        "evaluation": {
            "self_induced_records_by_creator": len(own),
            "self_induced_spd_to_creator": math.fsum(r["SPD"] for r in own),
            "self_induced_positive_records": sum(1 for r in own if r["status"] == POSITIVE),
            "honest_records": len(honest),
            "honest_spd": math.fsum(r["SPD"] for r in honest),
            "honest_eligible_records": len(honest_eligible),
            "honest_decayed_records": len(honest_decayed),
            "honest_decayed_fraction": frac(len(honest_decayed), len(honest_eligible)),
            "honest_zeroed_by_linkage": sum(1 for r in honest if r["reason"] == "self_induced_linkage"),
            "ambiguity_records": len(ambiguity),
            "ambiguity_fraction": frac(len(ambiguity), len(evaluated)),
            "informational_fraction": frac(by_status.get(INFORMATIONAL, 0), len(records)),
            "positive_records": len(positive),
            "mean_spd_per_positive_record": frac(math.fsum(r["SPD"] for r in positive), len(positive)),
            "max_sum_A_per_event": max((math.fsum(v) for v in sum_a.values()), default=0.0),
        },
    }


def csv_row(r: Dict[str, Any]) -> List[Any]:
    f, ep = r["factors"], r["epistemic"]
    se_time = None if r["se"] is None else r["se"]["time"]
    return [
        r["event_id"], r["zone_id"], r["risk_channel"], r["actor_id"], r["tick"], r["dti_day"],
        r["status"], r["reason"], r["SPD"], f["W"], f["S"], f["A"], f["C"], f["T"], r["claim"],
        r["linkage_observed"], r["intervention_time"], r["ta"]["time"], se_time,
        ep["validity_state"], ep["confidence_state"], ep["consistency_state"],
        r["truth"]["self_induced"], r["truth"]["own_threat"],
    ]


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def write_records(output_dir: str, records: Iterable[Dict[str, Any]]) -> None:
    records = list(records)
    with open(os.path.join(output_dir, "metrics.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                               allow_nan=False))
            f.write("\n")
    with open(os.path.join(output_dir, "metrics.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(CSV_COLUMNS)
        for r in records:
            w.writerow([_cell(v) for v in csv_row(r)])


def summary_text(summary: Dict[str, Any]) -> str:
    """Human-readable summary (rounded; not part of the result digest)."""
    lines = ["DKP L8 PREVENTION research bench - run summary",
             "=" * 48,
             f"scenario: {summary['scenario_id']}",
             "events:"]
    lines += [f"  {k}: {v}" for k, v in summary["events"].items()]
    lines.append(f"records: {summary['records_total']}")
    lines += [f"  {k}: {v}" for k, v in summary["by_status"].items()]
    lines.append("zero/invalid reasons:")
    lines += [f"  {k}: {v}" for k, v in summary["by_reason"].items()]
    lines.append(f"total SPD: {summary['total_spd']:.6f}")
    lines.append(f"subjects: {summary['subject_count']}")
    lines += [f"  {k}: {v:.6f}" for k, v in summary["subject_totals"].items()]
    lines.append("evaluation against scenario truth:")
    for k, v in summary["evaluation"].items():
        lines.append(f"  {k}: {v:.6f}" if isinstance(v, float) else f"  {k}: {v}")
    lines.append("")
    lines.append("Synthetic simulation output. Not an operational output and not a")
    lines.append("DKP-8-SIMULATION-001 admission. See run_manifest.json.")
    return "\n".join(lines) + "\n"
