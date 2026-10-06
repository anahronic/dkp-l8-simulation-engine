"""
Inter-module contract (lab specification §6.3).

A ``Message`` is what one part of an experiment tells another: an observation from a
generator, an evaluation, a decision, an action.  It carries

    event_id      unique id inside the log
    kind          observation | evaluation | decision | action | notice
    source        who produced it (oracle class, module, actor)
    measured_at   when the measured state existed (None for messages that measure nothing)
    arrived_at    when the message became available to consumers
    decided_at    when a decision was taken (None unless kind is decision or action)
    unit, value, uncertainty
    epistemic     EPISTEMIC-BOUNDARIES §5 fields, when the message is an output used operationally
    provenance    event ids this message derives from (all must have arrived no later)
    order         explicit tie-break key for messages that arrive at the same time

Times are integers in the unit the experiment declares (``EventLog.time_unit``).

``EventLog`` keeps messages in a declared order: (arrived_at, order, event_id).  The
``order`` field is the declared rule for simultaneous events; an experiment whose meaning
depends on the order of simultaneous events must set it from an explicit input.  Appending
the same messages in another sequence gives the same log and digest.  A consumer reads
through ``view(at)``, which returns only messages that have arrived by ``at`` — there is no
way to read the future through a view.
"""

from __future__ import annotations

import bisect
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

KINDS = ("observation", "evaluation", "decision", "action", "notice")
VALIDITY = ("VALID", "CONDITIONAL", "INVALID")
CONFIDENCE = ("SUFFICIENT_DATA", "INSUFFICIENT_DATA", "DEGRADED_SIGNAL")
CONSISTENCY = ("CONSISTENT", "ORACLE_CONFLICT", "UNRESOLVED")
EPISTEMIC_FIELDS = ("validity_state", "confidence_state", "consistency_state",
                    "scope_ref", "revalidation_required", "dispute_allowed")


class ContractError(ValueError):
    """A message or a log operation violates the §6.3 contract."""


def epistemic_problems(md: Optional[Dict[str, Any]]) -> List[str]:
    """Why an EB §5 metadata set is incomplete or undefined (empty list = complete)."""
    if md is None:
        return ["no epistemic metadata"]
    out = [f"missing {f}" for f in EPISTEMIC_FIELDS if md.get(f) is None]
    for f, allowed in (("validity_state", VALIDITY), ("confidence_state", CONFIDENCE),
                       ("consistency_state", CONSISTENCY)):
        if md.get(f) is not None and md[f] not in allowed:
            out.append(f"{f} {md[f]!r} undefined")
    for f in ("revalidation_required", "dispute_allowed"):
        if md.get(f) is not None and not isinstance(md[f], bool):
            out.append(f"{f} not boolean")
    return out


@dataclass(frozen=True)
class Message:
    event_id: str
    kind: str
    source: str
    arrived_at: int
    value: Any = None
    unit: Optional[str] = None
    measured_at: Optional[int] = None
    decided_at: Optional[int] = None
    uncertainty: Optional[float] = None
    epistemic: Optional[Dict[str, Any]] = None
    provenance: Tuple[str, ...] = ()
    order: int = 0

    def __post_init__(self) -> None:
        if not self.event_id or not isinstance(self.event_id, str):
            raise ContractError("event_id must be a non-empty string")
        if self.kind not in KINDS:
            raise ContractError(f"{self.event_id}: kind {self.kind!r} not in {KINDS}")
        for name in ("arrived_at", "measured_at", "decided_at", "order"):
            v = getattr(self, name)
            if v is not None and (not isinstance(v, int) or isinstance(v, bool)):
                raise ContractError(f"{self.event_id}: {name} must be an integer time")
        if self.measured_at is not None and self.measured_at > self.arrived_at:
            raise ContractError(f"{self.event_id}: arrives before it is measured")
        if self.decided_at is not None and self.decided_at > self.arrived_at:
            raise ContractError(f"{self.event_id}: arrives before it is decided")
        if self.kind in ("decision", "action") and self.decided_at is None:
            raise ContractError(f"{self.event_id}: a {self.kind} needs decided_at")

    def as_dict(self) -> Dict[str, Any]:
        return {"event_id": self.event_id, "kind": self.kind, "source": self.source,
                "measured_at": self.measured_at, "arrived_at": self.arrived_at, "decided_at": self.decided_at,
                "unit": self.unit, "value": self.value, "uncertainty": self.uncertainty,
                "epistemic": self.epistemic, "provenance": list(self.provenance), "order": self.order}


def _key(m: Message) -> Tuple[int, int, str]:
    return (m.arrived_at, m.order, m.event_id)


def _measured(m: Message) -> Tuple[int, int, int, str]:
    return (m.measured_at if m.measured_at is not None else m.arrived_at,) + _key(m)


_END = (float("inf"), "\U0010ffff")      # sorts after every (order, event_id) of the same time


@dataclass
class EventLog:
    time_unit: str
    tie_rule: str = "order field, then event_id"
    _msgs: List[Message] = field(default_factory=list)
    _keys: List[Tuple[int, int, str]] = field(default_factory=list)
    _ids: Dict[str, Message] = field(default_factory=dict)
    _streams: Optional[Dict[Tuple[str, str], Tuple[list, list]]] = None

    def append(self, m: Message) -> Message:
        if m.event_id in self._ids:
            raise ContractError(f"duplicate event_id {m.event_id}")
        for ref in m.provenance:
            src = self._ids.get(ref)
            if src is None:
                raise ContractError(f"{m.event_id}: provenance {ref} is not in the log")
            if src.arrived_at > m.arrived_at:
                raise ContractError(f"{m.event_id}: provenance {ref} arrives later ({src.arrived_at} > {m.arrived_at})")
        k = _key(m)
        i = bisect.bisect_right(self._keys, k)
        self._keys.insert(i, k)
        self._msgs.insert(i, m)
        self._ids[m.event_id] = m
        self._streams = None
        return m

    def extend(self, msgs: Iterable[Message]) -> None:
        """Append messages whose provenance may refer to each other, in arrival order."""
        for m in sorted(msgs, key=_key):
            self.append(m)

    def get(self, event_id: str) -> Message:
        return self._ids[event_id]

    def __len__(self) -> int:
        return len(self._msgs)

    def messages(self) -> List[Message]:
        return list(self._msgs)

    def _stream(self, kind: str, source: str) -> Tuple[list, list]:
        """Per (kind, source): arrival keys and, for each prefix, the message measured latest."""
        if self._streams is None:
            streams: Dict[Tuple[str, str], Tuple[list, list]] = {}
            for m in self._msgs:
                keys, best = streams.setdefault((m.kind, m.source), ([], []))
                prev = best[-1] if best else None
                keys.append(_key(m))
                best.append(m if prev is None or _measured(m) >= _measured(prev) else prev)
            self._streams = streams
        return self._streams.get((kind, source), ([], []))

    def view(self, at: int) -> "LogView":
        return LogView(self, at)

    def digest(self) -> str:
        body = json.dumps({"time_unit": self.time_unit, "tie_rule": self.tie_rule,
                           "messages": [m.as_dict() for m in self._msgs]},
                          sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


class LogView:
    """Read-only window on a log: only messages with arrived_at <= at."""

    def __init__(self, log: EventLog, at: int) -> None:
        self._log, self.at = log, at
        self._n = bisect.bisect_right(log._keys, (at,) + _END)

    def messages(self, kind: Optional[str] = None, source: Optional[str] = None) -> List[Message]:
        return [m for m in self._log._msgs[:self._n]
                if (kind is None or m.kind == kind) and (source is None or m.source == source)]

    def latest(self, kind: str, source: str) -> Optional[Message]:
        """The available message of this kind and source with the latest measurement (then arrival)."""
        keys, best = self._log._stream(kind, source)
        n = bisect.bisect_right(keys, (self.at,) + _END)
        return best[n - 1] if n else None

    def get(self, event_id: str) -> Message:
        m = self._log.get(event_id)
        if m.arrived_at > self.at:
            raise ContractError(f"{event_id} is not available at {self.at} (arrives at {m.arrived_at})")
        return m
