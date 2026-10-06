"""
Strict input validation for lab modules (TZ §6.2, §11.2).

A module declares its inputs as a mapping of field specs:

    {"seed": {"type": "int", "min": 0, "default": 42, "source": "hypothesis",
              "unit": None, "label": {"en": "...", "ru": "..."}}}

Types: int, number, bool, str, enum (``values``), pair (two numbers lo <= hi),
list (``items`` spec), object (``fields`` spec).  Unknown keys are rejected,
numbers must be finite, booleans are not numbers.  ``default`` values are
shown to the user and copied into the resolved input — nothing is filled in
silently.  ``source`` says where a value comes from (TZ §9): text, calibration,
hypothesis, alternative, missing.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional

SOURCES = ("text", "calibration", "hypothesis", "alternative", "missing", "user")


class LabInputError(ValueError):
    def __init__(self, problems: List[str]) -> None:
        super().__init__("invalid input:\n  " + "\n  ".join(problems))
        self.problems = problems


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _check(value: Any, spec: Dict[str, Any], path: str, problems: List[str]) -> Any:
    t = spec["type"]
    if t == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            problems.append(f"{path}: expected integer")
            return value
    elif t == "number":
        if not _is_num(value):
            problems.append(f"{path}: expected finite number")
            return value
    elif t == "bool":
        if not isinstance(value, bool):
            problems.append(f"{path}: expected true/false")
        return value
    elif t == "str":
        if not isinstance(value, str) or not value:
            problems.append(f"{path}: expected non-empty string")
        return value
    elif t == "enum":
        if value not in spec["values"]:
            problems.append(f"{path}: {value!r} not one of {list(spec['values'])}")
        return value
    elif t == "pair":
        if (not isinstance(value, list) or len(value) != 2 or not all(_is_num(x) for x in value)
                or value[0] > value[1]):
            problems.append(f"{path}: expected [lo, hi] of finite numbers with lo <= hi")
            return value
        for x in value:
            _bounds(x, spec, path, problems)
        return value
    elif t == "list":
        if not isinstance(value, list):
            problems.append(f"{path}: expected list")
            return value
        if "min_items" in spec and len(value) < spec["min_items"]:
            problems.append(f"{path}: at least {spec['min_items']} items")
        if "max_items" in spec and len(value) > spec["max_items"]:
            problems.append(f"{path}: at most {spec['max_items']} items")
        return [_check(v, spec["items"], f"{path}[{i}]", problems) for i, v in enumerate(value)]
    elif t == "object":
        return resolve(value, spec["fields"], path, problems)
    else:  # pragma: no cover
        raise AssertionError(f"unknown spec type {t}")
    _bounds(value, spec, path, problems)
    return value


def _bounds(value: Any, spec: Dict[str, Any], path: str, problems: List[str]) -> None:
    if "min" in spec and value < spec["min"]:
        problems.append(f"{path}: must be >= {spec['min']}")
    if "max" in spec and value > spec["max"]:
        problems.append(f"{path}: must be <= {spec['max']}")


def resolve(value: Any, fields: Dict[str, Dict[str, Any]], path: str = "input",
            problems: Optional[List[str]] = None) -> Dict[str, Any]:
    """Validate ``value`` against ``fields``; fill declared defaults; return the resolved input."""
    top = problems is None
    problems = [] if top else problems
    out: Dict[str, Any] = {}
    if not isinstance(value, dict):
        problems.append(f"{path}: expected mapping")
        value = {}
    for key in value:
        if key not in fields:
            problems.append(f"{path}.{key}: unknown key")
    for key, spec in fields.items():
        if key in value:
            out[key] = _check(value[key], spec, f"{path}.{key}", problems)
        elif "default" in spec:
            out[key] = copy.deepcopy(spec["default"])
        else:
            problems.append(f"{path}.{key}: required")
    if top and problems:
        raise LabInputError(problems)
    return out


def describe(fields: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """JSON-safe description of the input form (for the catalog and the UI)."""
    out = {}
    for k, spec in fields.items():
        d = {kk: vv for kk, vv in spec.items() if kk not in ("fields", "items")}
        if spec["type"] == "object":
            d["fields"] = describe(spec["fields"])
        if spec["type"] == "list":
            item = spec["items"]
            d["items"] = describe(item["fields"]) if item["type"] == "object" else dict(item)
        out[k] = d
    return out
