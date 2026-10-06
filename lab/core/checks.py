"""
Check results and coverage summaries (TZ §3).

A check evaluates ONE registry requirement in ONE experiment:
    PASS            the provision holds in this experiment
    FAIL            the provision is violated (evidence given)
    UNKNOWN         cannot be decided here (missing model, data or definition)
    NOT_APPLICABLE  the provision does not apply to this experiment (reason required)

Requirements of the module's documents that no check evaluated are "uncovered".
UNKNOWN and uncovered never count as PASS, and no summary says "the protocol
passed" unless every requirement of the document was applicable and passed.

These statuses are the lab's evaluation of an output.  They do not replace the
EPISTEMIC-BOUNDARIES §5 fields of the output itself, which stay in the output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"
STATUSES = (PASS, FAIL, UNKNOWN, NOT_APPLICABLE)


@dataclass
class CheckResult:
    requirement_id: str
    check: str                      # check name inside the module
    status: str
    explanation: str                # plain-language reason
    evidence: Dict[str, Any] = field(default_factory=dict)
    applicability: Optional[str] = None   # required for NOT_APPLICABLE

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unknown check status {self.status!r}")
        if self.status == NOT_APPLICABLE and not self.applicability:
            raise ValueError(f"{self.requirement_id}: NOT_APPLICABLE needs an applicability reason")

    def as_dict(self) -> Dict[str, Any]:
        return {"requirement_id": self.requirement_id, "check": self.check, "status": self.status,
                "explanation": self.explanation, "evidence": self.evidence,
                "applicability": self.applicability}


def summarize(results: Iterable[CheckResult], document_requirements: Iterable[str]) -> Dict[str, Any]:
    """Counts by status plus the requirements of the documents that were not evaluated."""
    results = list(results)
    counts = {s: 0 for s in STATUSES}
    for r in results:
        counts[r.status] += 1
    evaluated = {r.requirement_id for r in results}
    uncovered = sorted(set(document_requirements) - evaluated)
    applicable = len(results) - counts[NOT_APPLICABLE]
    complete = not uncovered and counts[UNKNOWN] == 0 and counts[FAIL] == 0
    return {
        "counts": counts,
        "applicable": applicable,
        "uncovered": uncovered,
        "uncovered_count": len(uncovered),
        "all_document_requirements_passed": complete,
        "sentence": {
            "en": (f"{counts[PASS]} of {applicable} applicable checks passed; {counts[FAIL]} failed; "
                   f"{counts[UNKNOWN]} undecided (need a model or data); "
                   f"{len(uncovered)} provisions of the documents not covered by this experiment."),
            "ru": (f"Выполнено {counts[PASS]} из {applicable} применимых проверок; нарушено {counts[FAIL]}; "
                   f"не определено {counts[UNKNOWN]} (нужна модель или данные); "
                   f"положений документов вне охвата эксперимента: {len(uncovered)}."),
        },
    }
