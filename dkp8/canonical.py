"""Canonical JSON for signed L8 artifacts (DKP-8-SIMULATION-001 §9, §11).

The byte form is the JSON Canonicalization Scheme (RFC 8785) restricted to a subset that has exactly one
representation in every language: objects with string keys sorted by UTF-16 code units, no insignificant
whitespace, UTF-8, the JSON short escapes and lowercase ``\\u00xx`` for other control characters.

Numbers: only integers within ±(2**53 - 1).  Non-integer quantities (thresholds, weights, bounds) are written as
decimal strings such as ``"0.68"`` and validated with :data:`DECIMAL`; binary floating point never enters a signed
artifact, so no platform or library can round a calibration value differently.  Anything else is refused.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

MAX_SAFE_INTEGER = 2 ** 53 - 1
DECIMAL = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")


class CanonicalError(ValueError):
    """The value has no canonical form under this profile."""


def _check(value: Any, path: str) -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalError(f"{path}: integer outside ±(2**53-1)")
        return
    if isinstance(value, float):
        raise CanonicalError(f"{path}: binary floating point is not allowed; write a decimal string")
    if isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _check(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalError(f"{path}: object keys must be strings")
            _check(item, f"{path}.{key}")
        return
    raise CanonicalError(f"{path}: unsupported type {type(value).__name__}")


def _sort(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sort(value[k]) for k in sorted(value, key=lambda k: k.encode("utf-16-be"))}
    if isinstance(value, (list, tuple)):
        return [_sort(v) for v in value]
    return value


def canonical(value: Any) -> bytes:
    """Canonical UTF-8 bytes of ``value`` (raises :class:`CanonicalError`)."""
    _check(value, "$")
    # sort_keys=False: the order produced by _sort (UTF-16 code units, as RFC 8785 requires) is kept.
    return json.dumps(_sort(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    """Lowercase hex SHA-256 of the canonical form."""
    return hashlib.sha256(canonical(value)).hexdigest()


def is_decimal(text: Any) -> bool:
    return isinstance(text, str) and DECIMAL.fullmatch(text) is not None
