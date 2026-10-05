#!/usr/bin/env python3
"""
Candidate comparison bench (audit items B1–B4 of the S1 draft review).

    python -m simulation.compare_candidates --spec simulation/configs/comparison/example.yaml \
        --output-dir simulation/outputs/comparison

What it does:
    - runs the baseline (the configuration in force) on every declared seed;
    - runs each candidate (an overlay on the baseline) on the same seeds;
    - runs every non-conflicting pair and, if no overlays conflict, all candidates
      together, and reports the interaction (joint delta − sum of single deltas);
    - checks declared invariants on every run;
    - reports metric vectors with *declared* directions.

What it does not do:
    - it selects nothing (no Pareto or lexicographic choice): the selection rule is
      the open S1 decision;
    - metric directions are a proposal, not a norm.

Guarantees tested in tests/simulation/test_compare_candidates.py:
    candidate identity is the digest of its overlay (names are labels); the report
    does not depend on candidate order; identical overlays are reported as copies
    and run once; adding a candidate does not change any other candidate's row;
    the baseline is always present; a joint violation of an invariant is detected
    even when each candidate alone passes (r = a·b example).

Provenance (audit item R1): every evaluated configuration is stored in full
(``config``; replay a seed by setting simulation.seed), each seed's run has
its input_id and result_id, ``package`` names the engine code and the spec
digests, and ``content_sha256`` seals the document (SHA-256 of canonical JSON
without that field).  Machine, git commit, time and paths go to
comparison_provenance.json.
"""

from __future__ import annotations

import argparse
import datetime
import itertools
import math
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.core.config import (
    canonical_json, config_digest, deep_merge, load_config, overlay_paths, run_inputs, sha256_text,
)
from simulation.core.manifest import engine_identity, platform_provenance, seal
from simulation.modules.prevention.protocol_adapter import POSITIVE
from simulation.modules.prevention.reporting import dumps, write_text

Metric = Tuple[Callable[[Any], float], str, str]   # (extractor, direction, note)

DIRECTIONS_STATUS = ("Directions are a proposal for the S1 procedure (review item B1); "
                     "they are not normative and no selection is made from them.")

METRICS: Dict[str, Metric] = {
    "total_spd": (lambda r: r.summary["total_spd"], "none",
                  "more recognized reward is not better by itself"),
    "honest_spd": (lambda r: r.summary["evaluation"]["honest_spd"], "none",
                   "reward on threats the subject did not create"),
    "self_induced_spd_to_creator": (lambda r: r.summary["evaluation"]["self_induced_spd_to_creator"],
                                    "lower", "reward reaching subjects on threats they created"),
    "honest_decayed_fraction": (lambda r: r.summary["evaluation"]["honest_decayed_fraction"], "lower",
                                "recognized honest interventions with Tₖ < 1"),
    "honest_zeroed_by_linkage": (lambda r: float(r.summary["evaluation"]["honest_zeroed_by_linkage"]),
                                 "lower", "honest subjects zeroed as self-induced"),
    "ambiguity_fraction": (lambda r: r.summary["evaluation"]["ambiguity_fraction"], "lower",
                           "evaluated records ending in NO_ATTRIBUTION by ambiguity"),
    "informational_fraction": (lambda r: r.summary["evaluation"]["informational_fraction"], "none",
                               "records downgraded by oracle inconsistency"),
}


def _records_ok(pred: Callable[[Dict[str, Any]], bool]) -> Callable[[Any], bool]:
    return lambda r: all(pred(rec) for rec in r.records)


INVARIANTS: Dict[str, Callable[[Any], bool]] = {
    "sum_A_per_event_le_1": lambda r: r.summary["evaluation"]["max_sum_A_per_event"] <= 1.0,
    "spd_nonnegative": _records_ok(lambda rec: rec["SPD"] >= 0.0),
    "S_in_unit_interval": _records_ok(lambda rec: rec["factors"]["S"] is None or 0.0 <= rec["factors"]["S"] <= 1.0),
    "every_non_positive_record_has_reason": _records_ok(
        lambda rec: rec["status"] == POSITIVE or rec["reason"] is not None),
}


def default_run(cfg: Dict[str, Any]) -> Any:
    from simulation.run_prevention_simulation import run_simulation
    return run_simulation(cfg, write=False)


def overlay_digest(overlay: Dict[str, Any]) -> str:
    return sha256_text(canonical_json(overlay))


def _mean(xs: List[float]) -> float:
    return math.fsum(xs) / len(xs)


def _evaluate(cfg: Dict[str, Any], seeds: List[int], run_fn: Callable[[Dict[str, Any]], Any],
              metrics: Dict[str, Metric], invariants: Dict[str, Callable[[Any], bool]]) -> Dict[str, Any]:
    per_seed = {}
    for seed in seeds:
        res = run_fn(deep_merge(cfg, {"simulation": {"seed": seed}}))
        manifest = getattr(res, "manifest", None)
        per_seed[str(seed)] = {
            "input_id": None if manifest is None else manifest["input_id"],
            "result_id": None if manifest is None else manifest["result_id"],
            "metrics": {m: float(fn(res)) for m, (fn, _, _) in sorted(metrics.items())},
            "invariants": {i: bool(fn(res)) for i, fn in sorted(invariants.items())},
        }
    mean = {m: _mean([per_seed[str(s)]["metrics"][m] for s in seeds]) for m in sorted(metrics)}
    inv = {i: all(per_seed[str(s)]["invariants"][i] for s in seeds) for i in sorted(invariants)}
    return {"config": run_inputs(cfg), "config_digest": config_digest(cfg), "mean": mean,
            "invariants_hold": inv, "per_seed": per_seed}


def _delta(row: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, float]:
    return {m: row["mean"][m] - base["mean"][m] for m in row["mean"]}


def find_conflicts(overlays: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Paths set to different values by different overlays (keyed by digest)."""
    seen: Dict[str, Dict[str, Any]] = {}
    for dig in sorted(overlays):
        for path, val in overlay_paths(overlays[dig]).items():
            seen.setdefault(path, {})[dig] = val
    out = []
    for path in sorted(seen):
        vals = seen[path]
        if len({canonical_json(v) for v in vals.values()}) > 1:
            out.append({"path": path, "values": {d: vals[d] for d in sorted(vals)}})
    return out


def compare(baseline_cfg: Dict[str, Any], candidates: Dict[str, Dict[str, Any]], seeds: List[int],
            run_fn: Optional[Callable[[Dict[str, Any]], Any]] = None,
            metrics: Optional[Dict[str, Metric]] = None,
            invariants: Optional[Dict[str, Callable[[Any], bool]]] = None) -> Dict[str, Any]:
    run_fn = run_fn or default_run
    metrics = METRICS if metrics is None else metrics
    invariants = INVARIANTS if invariants is None else invariants
    seeds = sorted(set(seeds))

    by_digest: Dict[str, Dict[str, Any]] = {}
    names: Dict[str, List[str]] = {}
    for name in sorted(candidates):
        d = overlay_digest(candidates[name])
        by_digest.setdefault(d, candidates[name])
        names.setdefault(d, []).append(name)

    base = _evaluate(baseline_cfg, seeds, run_fn, metrics, invariants)
    rows = {}
    for d in sorted(by_digest):
        row = _evaluate(deep_merge(baseline_cfg, by_digest[d]), seeds, run_fn, metrics, invariants)
        row["names"] = names[d]
        row["copies"] = names[d][1:]
        row["overlay"] = by_digest[d]
        row["delta_vs_baseline"] = _delta(row, base)
        rows[d] = row

    def joint(digests: List[str]) -> Dict[str, Any]:
        subset = {d: by_digest[d] for d in digests}
        conflicts = find_conflicts(subset)
        entry: Dict[str, Any] = {"members": digests, "conflicts": conflicts}
        if conflicts:
            entry["evaluated"] = False
            return entry
        merged: Dict[str, Any] = {}
        for d in digests:
            merged = deep_merge(merged, by_digest[d])
        row = _evaluate(deep_merge(baseline_cfg, merged), seeds, run_fn, metrics, invariants)
        row["delta_vs_baseline"] = _delta(row, base)
        row["interaction"] = {m: row["delta_vs_baseline"][m] - math.fsum(rows[d]["delta_vs_baseline"][m]
                                                                         for d in digests)
                              for m in row["mean"]}
        row["joint_breaks_invariant"] = sorted(
            i for i, ok in row["invariants_hold"].items()
            if not ok and all(rows[d]["invariants_hold"][i] for d in digests))
        entry.update(row, evaluated=True)
        return entry

    digests = sorted(by_digest)
    pairs = [joint(list(p)) for p in itertools.combinations(digests, 2)]
    all_joint = joint(digests) if len(digests) > 2 else None

    return seal({
        "schema": "dkp-l8-comparison/2",
        "package": {**engine_identity(), "generator": "simulation.compare_candidates"},
        "baseline": base,
        "seeds": seeds,
        "candidates": rows,
        "pairwise_joint": pairs,
        "all_joint": all_joint,
        "metric_directions": {m: {"direction": dirn, "note": note}
                              for m, (_, dirn, note) in sorted(metrics.items())},
        "directions_status": DIRECTIONS_STATUS,
        "selection": None,
        "selection_note": "No candidate is selected: the selection rule is the open S1 decision.",
    })


def report_text(rep: Dict[str, Any]) -> str:
    lines = ["Candidate comparison (no selection made)", "=" * 40,
             f"seeds: {rep['seeds']}", f"baseline config: {rep['baseline']['config_digest']}", ""]
    metrics = list(rep["baseline"]["mean"])
    for d, row in rep["candidates"].items():
        lines.append(f"{d[:12]}  {', '.join(row['names'])}")
        for m in metrics:
            lines.append(f"    {m:30s} {row['mean'][m]:12.6f}  Δ {row['delta_vs_baseline'][m]:+.6f}"
                         f"  [{rep['metric_directions'][m]['direction']}]")
        bad = [i for i, ok in row["invariants_hold"].items() if not ok]
        lines.append(f"    invariants: {'all hold' if not bad else 'BROKEN ' + ', '.join(bad)}")
    for p in rep["pairwise_joint"]:
        tag = " + ".join(rep["candidates"][d]["names"][0] for d in p["members"])
        if not p["evaluated"]:
            lines.append(f"joint {tag}: not evaluated, conflicts on "
                         + ", ".join(c["path"] for c in p["conflicts"]))
        elif p["joint_breaks_invariant"]:
            lines.append(f"joint {tag}: BREAKS {', '.join(p['joint_breaks_invariant'])}")
    lines.append("")
    lines.append(rep["directions_status"])
    lines.append(rep["selection_note"])
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Compare candidate overlays against the baseline")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--output-dir", default="simulation/outputs/comparison")
    args = ap.parse_args(argv)
    spec = load_config(args.spec)
    unknown = set(spec) - {"baseline", "baseline_overlay", "scenario_seeds", "candidates"}
    if unknown:
        raise SystemExit(f"unknown keys in comparison spec: {sorted(unknown)}")
    base_path = spec["baseline"]
    if not os.path.isabs(base_path):
        base_path = os.path.join(os.path.dirname(os.path.abspath(args.spec)), base_path)
    baseline = deep_merge(load_config(base_path), spec["baseline_overlay"])
    t0 = time.time()
    rep = compare(baseline, spec["candidates"], spec["scenario_seeds"])
    os.makedirs(args.output_dir, exist_ok=True)
    write_text(os.path.join(args.output_dir, "comparison.json"), dumps(rep))
    write_text(os.path.join(args.output_dir, "comparison_provenance.json"), dumps({
        **platform_provenance(),
        "elapsed_seconds": time.time() - t0,
        "output_dir": os.path.abspath(args.output_dir),
        "finished_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "argv": sys.argv,
        "comparison_content_sha256": rep["content_sha256"],
    }))
    write_text(os.path.join(args.output_dir, "comparison.txt"), report_text(rep))
    print(report_text(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
