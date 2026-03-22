"""
Metrics collector — accumulates per-event and per-subject measurements.

Protocol-agnostic: stores (key, value) tuples with timestamps.
The protocol adapter decides what to record.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class MetricRecord:
    timestamp: float
    zone_id: str
    event_id: int
    metric_name: str
    value: float
    details: Dict[str, Any] = field(default_factory=dict)


class MetricsCollector:
    """Append-only metrics accumulator."""

    def __init__(self) -> None:
        self._records: List[MetricRecord] = []
        self._subject_totals: Dict[str, float] = {}

    def record(self, rec: MetricRecord) -> None:
        self._records.append(rec)

    def add_subject_contribution(self, subject_id: str, spd: float) -> None:
        self._subject_totals[subject_id] = self._subject_totals.get(subject_id, 0.0) + spd

    @property
    def records(self) -> List[MetricRecord]:
        return list(self._records)

    @property
    def subject_totals(self) -> Dict[str, float]:
        return dict(self._subject_totals)

    def summary(self) -> Dict[str, Any]:
        total_events = len(self._records)
        spd_records = [r for r in self._records if r.metric_name == "SPD"]
        total_spd = sum(r.value for r in spd_records)
        informational = sum(1 for r in self._records if r.metric_name == "SPD_informational")
        zero_spd = sum(1 for r in spd_records if r.value == 0.0)
        positive_spd = sum(1 for r in spd_records if r.value > 0.0)
        return {
            "total_metric_records": total_events,
            "total_spd_events": len(spd_records),
            "positive_spd_events": positive_spd,
            "zero_spd_events": zero_spd,
            "informational_events": informational,
            "total_spd_value": round(total_spd, 6),
            "subject_count": len(self._subject_totals),
            "subject_totals": {k: round(v, 6) for k, v in self._subject_totals.items()},
        }

    def to_json(self) -> str:
        return json.dumps([asdict(r) for r in self._records], indent=2)

    def to_csv(self, path: str) -> None:
        if not self._records:
            return
        fieldnames = ["timestamp", "zone_id", "event_id", "metric_name", "value", "details"]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in self._records:
                row = asdict(r)
                row["details"] = json.dumps(row["details"])
                writer.writerow(row)

    def write_outputs(self, output_dir: str) -> None:
        os.makedirs(output_dir, exist_ok=True)

        # metrics.json — full record
        with open(os.path.join(output_dir, "metrics.json"), "w") as f:
            f.write(self.to_json())

        # metrics.csv
        self.to_csv(os.path.join(output_dir, "metrics.csv"))

        # summary.txt
        s = self.summary()
        with open(os.path.join(output_dir, "summary.txt"), "w") as f:
            f.write("DKP L8 Simulation — Run Summary\n")
            f.write("=" * 40 + "\n\n")
            for k, v in s.items():
                if k == "subject_totals":
                    f.write(f"\n  Subject totals:\n")
                    for sid, val in v.items():
                        f.write(f"    {sid}: {val}\n")
                else:
                    f.write(f"  {k}: {v}\n")
