"""
Module contract (TZ §6.3).

A lab module declares what it covers and how it is run:

    id, version, title          identity of the model (part of every input_id)
    protocols                   document ids whose provisions it evaluates
    inputs                      field specs (lab.core.schema); defaults are visible
    hypotheses                  declared assumptions not fixed by the text
    validate(input)             strict validation -> resolved input (dict)
    evaluate(resolved)          pure computation -> ModuleResult
    examples()                  normal, boundary and failure inputs for the UI

``evaluate`` sees only what the experiment declares as observable; when a
model generates "truth" (as PREVENTION's scenario does), the truth may be used
to score the adapter but never as hidden evidence of causality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from lab.core.checks import CheckResult
from lab.core.schema import describe, resolve


@dataclass
class ModuleResult:
    outputs: Dict[str, Any]                       # machine-readable results (no timings, no paths)
    checks: List[CheckResult]
    explain: List[Dict[str, str]] = field(default_factory=list)   # [{"en": ..., "ru": ...}]
    records: Optional[List[Dict[str, Any]]] = None                 # optional detailed rows
    attachments: Dict[str, bytes] = field(default_factory=dict)    # extra files for the package


class LabModule:
    id: str = ""
    version: str = ""
    title: Dict[str, str] = {}
    summary: Dict[str, str] = {}
    protocols: List[str] = []
    inputs: Dict[str, Dict[str, Any]] = {}
    hypotheses: List[Dict[str, Any]] = []
    causal_note: Optional[Dict[str, str]] = None   # shown when causality is a scenario input
    #: requirement id -> (check name, "IMPLEMENTED" | "PARTIAL", note); synced into the registry
    implements: Dict[str, Any] = {}
    #: test files that exercise the module's checks
    tests: List[str] = []
    #: examples shown first in the UI ("try example" runs the first two as variants)
    example_order: List[str] = []
    #: examples computed under an alternative reading (source 'alternative'), not the text in force;
    #: their statuses are reported apart from the reference examples
    alternative_examples: List[str] = []
    #: optional progress callback set by the runner: fn(fraction 0..1, message)
    progress: Optional[Callable[[float, str], None]] = None

    def manifest(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "title": self.title,
            "summary": self.summary,
            "protocols": self.protocols,
            "inputs": describe(self.inputs),
            "hypotheses": self.hypotheses,
            "causal_note": self.causal_note,
            "examples": self.ordered_examples(),
            "failure_examples": sorted(self.failure_examples()),
        }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        return resolve(value, self.inputs)

    def evaluate(self, resolved: Dict[str, Any]) -> ModuleResult:  # pragma: no cover - abstract
        raise NotImplementedError

    def examples(self) -> Dict[str, Dict[str, Any]]:
        """Valid inputs (normal and boundary cases)."""
        return {}

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        """Inputs that must be refused by validate()."""
        return {}

    def ordered_examples(self) -> List[str]:
        names = list(self.examples())
        return [n for n in self.example_order if n in names] + sorted(n for n in names if n not in self.example_order)

    def report_progress(self, fraction: float, message: str) -> None:
        if self.progress is not None:
            self.progress(fraction, message)
