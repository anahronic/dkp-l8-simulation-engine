"""
Config loader and schema — every run is fully declared.

Schema version 3 rules:
    - every key listed in SCHEMA is required (no silent defaults);
    - unknown keys are rejected (no declared-but-ignored settings);
    - numbers must be finite (no NaN, no infinity, no booleans);
    - channel, actor and oracle-class names are identifiers (NAME_PATTERN): they become
      parts of event ids and of random-stream addresses, whose separators (":" and "/")
      therefore cannot occur inside a name (audit item V21-N2);
    - cross-field constraints are checked (time partition, TTL per class, ranges);
    - the order of mapping keys carries no meaning: the engine iterates mappings in
      sorted key order; the one order that matters (attribution under list_order)
      is the explicit list ``domain.actor_order``.

The resolved configuration minus the ``output`` section is the run input
that the manifest digests (see simulation.core.manifest).  Because no
meaning is carried by mapping order, canonical JSON (sorted keys) loses
nothing: a run replayed from config_resolved.json is the same run.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

SCHEMA_VERSION = 3

# Names used inside event ids and random-stream addresses: letters, digits, "_" and "-",
# starting with a letter or digit.  No ":" or "/" (the id and address separators).
NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
SECONDS_PER_DAY = 86400

STRATEGIES = ("patrol", "weak", "passive", "adversarial", "optimizer")

# Leaf type markers
NUM = "number"
INT = "int"
STR = "str"
BOOL = "bool"
PAIR = "pair"            # [lo, hi] numbers, lo <= hi
OPT_PAIR = "pair|null"
OPT_NUM = "number|null"
STR_LIST = "list[str]"


def ENUM(*values: str) -> tuple:
    return ("enum", values)


def ENUM_LIST(*values: str) -> tuple:
    return ("enum_list", values)


def MAPPING(value_schema: Any) -> tuple:
    return ("mapping", value_schema)


def NULLABLE(schema: Any) -> tuple:
    return ("nullable", schema)


SCHEMA: Dict[str, Any] = {
    "schema_version": INT,
    "scenario": {"id": STR, "description": STR, "synthetic": BOOL},
    "simulation": {"seed": INT, "num_zones": INT, "num_days": INT, "ticks_per_day": INT},
    "time": {"tick_seconds": NUM, "start_dti_day": INT},
    "protocol": {
        "epsilon_consistency": NUM,
        "delta_t_int_seconds": NUM,
        "theta_self_induced": NUM,
        "coverage_floor": NUM,
        "ta_time_basis": ENUM("measurement", "registration"),
        "ttl_reference": ENUM("signal", "decision"),
        "se_aggregation": ENUM("max", "min"),
        "confidence_rule": ENUM("class_coverage", "mean_reported_confidence"),
        "attribution_rule": ENUM("ambiguity_zero", "proportional", "list_order"),
        "recurrence": {
            "key": ENUM_LIST("actor", "zone", "channel"),
            "threshold": INT,
            "decay": NUM,
            "window_seconds": OPT_NUM,
            "history": ENUM("as_of_decision", "retrospective"),
        },
    },
    "domain": {
        "name": STR,
        "include_adversarial": BOOL,
        "actor_order": STR_LIST,
        "channels": MAPPING({"weight": NUM, "activation_rate": NUM, "intensity_range": PAIR}),
        "actors": MAPPING({
            "strategy": ENUM(*STRATEGIES),
            "effectiveness": NUM,
            "effectiveness_range": OPT_PAIR,
            "response_rate": NUM,
            "response_delay_seconds": PAIR,
            "attribution_claim": NUM,
            "self_induce_rate": NUM,
        }),
    },
    "oracles": {
        "classes": STR_LIST,
        "noise_sigma": NUM,
        "dropout_rate": NUM,
        "bias_range": PAIR,
        "measurement_delay_seconds": PAIR,
        "arrival_delay_seconds": PAIR,
        "ttl_seconds": MAPPING(NUM),
        "linkage_detection": {
            "detection_probability": NUM,
            "detected_score_range": PAIR,
            "undetected_score_range": PAIR,
        },
    },
    "attack": {
        "oracle_bias": NULLABLE({
            "classes": STR_LIST,
            "bias": NUM,
            "phase": ENUM("ta", "se", "both"),
        }),
    },
    "output": {"directory": STR},
}


class ConfigError(ValueError):
    """Raised when a configuration does not satisfy the schema."""


# ── loading ─────────────────────────────────────────────────────────────

def load_config(path: str) -> Dict[str, Any]:
    """Load a YAML config file (not yet validated)."""
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if cfg is None:
        raise ConfigError(f"Empty config file: {path}")
    return cfg


# ── validation ──────────────────────────────────────────────────────────

def _is_num(v: Any) -> bool:
    """A finite real number (bool, NaN and ±inf are rejected)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _check(value: Any, schema: Any, path: str, errors: List[str]) -> None:
    if isinstance(schema, dict):
        if not isinstance(value, dict):
            errors.append(f"{path}: expected mapping")
            return
        for key in schema:
            if key not in value:
                errors.append(f"{path}.{key}: required key missing")
        for key in value:
            if key not in schema:
                errors.append(f"{path}.{key}: unknown key")
        for key, sub in schema.items():
            if key in value:
                _check(value[key], sub, f"{path}.{key}", errors)
        return

    if isinstance(schema, tuple):
        kind = schema[0]
        if kind == "enum":
            if value not in schema[1]:
                errors.append(f"{path}: {value!r} not in {list(schema[1])}")
        elif kind == "enum_list":
            if (not isinstance(value, list) or not value
                    or any(v not in schema[1] for v in value)
                    or len(set(value)) != len(value)):
                errors.append(f"{path}: expected non-empty list of distinct {list(schema[1])}")
        elif kind == "mapping":
            if not isinstance(value, dict) or not value:
                errors.append(f"{path}: expected non-empty mapping")
                return
            for k, v in value.items():
                if not isinstance(k, str):
                    errors.append(f"{path}: keys must be strings")
                _check(v, schema[1], f"{path}.{k}", errors)
        elif kind == "nullable":
            if value is not None:
                _check(value, schema[1], path, errors)
        return

    if schema == NUM:
        if not _is_num(value):
            errors.append(f"{path}: expected finite number")
    elif schema == INT:
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{path}: expected integer")
    elif schema == STR:
        if not isinstance(value, str) or not value:
            errors.append(f"{path}: expected non-empty string")
    elif schema == BOOL:
        if not isinstance(value, bool):
            errors.append(f"{path}: expected boolean")
    elif schema in (PAIR, OPT_PAIR):
        if value is None and schema == OPT_PAIR:
            return
        if (not isinstance(value, list) or len(value) != 2
                or not all(_is_num(x) for x in value) or value[0] > value[1]):
            errors.append(f"{path}: expected [lo, hi] of finite numbers with lo <= hi")
    elif schema == OPT_NUM:
        if value is not None and not _is_num(value):
            errors.append(f"{path}: expected finite number or null")
    elif schema == STR_LIST:
        if (not isinstance(value, list) or not value
                or not all(isinstance(x, str) and x for x in value)
                or len(set(value)) != len(value)):
            errors.append(f"{path}: expected non-empty list of distinct strings")
    else:  # pragma: no cover - schema programming error
        raise AssertionError(f"unknown schema marker {schema!r}")


def _in_unit(v: float) -> bool:
    return 0.0 <= v <= 1.0


def _cross_checks(cfg: Dict[str, Any], errors: List[str]) -> None:
    if cfg["schema_version"] != SCHEMA_VERSION:
        errors.append(f"schema_version: expected {SCHEMA_VERSION}")

    actors = set(cfg["domain"]["actors"])
    if sorted(cfg["domain"]["actor_order"]) != sorted(actors):
        errors.append("domain.actor_order: must list every key of domain.actors exactly once")

    named = [("domain.channels", list(cfg["domain"]["channels"])),
             ("domain.actors", list(cfg["domain"]["actors"])),
             ("oracles.classes", list(cfg["oracles"]["classes"]))]
    for where, names in named:
        for name in names:
            if not NAME_PATTERN.fullmatch(name):
                errors.append(f"{where}: name {name!r} must match {NAME_PATTERN.pattern} "
                              "(letters, digits, '_' and '-'; no ':' or '/')")

    sim, time_cfg, proto = cfg["simulation"], cfg["time"], cfg["protocol"]
    for key in ("num_zones", "num_days", "ticks_per_day"):
        if sim[key] < 1:
            errors.append(f"simulation.{key}: must be >= 1")

    # DKP-0-TIME-001 §4.1: the civil day is the base unit; ticks partition it.
    if time_cfg["tick_seconds"] <= 0:
        errors.append("time.tick_seconds: must be > 0")
    elif sim["ticks_per_day"] * time_cfg["tick_seconds"] != SECONDS_PER_DAY:
        errors.append("time: ticks_per_day * tick_seconds must equal 86400 (one civil day)")

    if not _in_unit(proto["epsilon_consistency"]) or proto["epsilon_consistency"] < 0:
        errors.append("protocol.epsilon_consistency: must be in [0, 1]")
    if proto["delta_t_int_seconds"] <= 0:
        errors.append("protocol.delta_t_int_seconds: must be > 0")
    if not _in_unit(proto["theta_self_induced"]):
        errors.append("protocol.theta_self_induced: must be in [0, 1]")
    if not _in_unit(proto["coverage_floor"]):
        errors.append("protocol.coverage_floor: must be in [0, 1]")
    rec = proto["recurrence"]
    if rec["threshold"] < 0:
        errors.append("protocol.recurrence.threshold: must be >= 0")
    if not (0.0 < rec["decay"] <= 1.0):
        errors.append("protocol.recurrence.decay: must be in (0, 1]")
    if rec["window_seconds"] is not None and rec["window_seconds"] <= 0:
        errors.append("protocol.recurrence.window_seconds: must be > 0 or null")

    for ch, spec in cfg["domain"]["channels"].items():
        # PREVENTION §3.7: weight is a non-negative scalar (no upper bound).
        if spec["weight"] < 0:
            errors.append(f"domain.channels.{ch}.weight: must be >= 0")
        if not _in_unit(spec["activation_rate"]):
            errors.append(f"domain.channels.{ch}.activation_rate: must be in [0, 1]")
        if spec["intensity_range"][0] < 0:
            errors.append(f"domain.channels.{ch}.intensity_range: must be >= 0")

    for name, a in cfg["domain"]["actors"].items():
        for key in ("effectiveness", "response_rate", "attribution_claim", "self_induce_rate"):
            if not _in_unit(a[key]):
                errors.append(f"domain.actors.{name}.{key}: must be in [0, 1]")
        if a["response_delay_seconds"][0] < 0:
            errors.append(f"domain.actors.{name}.response_delay_seconds: must be >= 0")
        if a["self_induce_rate"] > 0 and a["strategy"] != "adversarial":
            errors.append(f"domain.actors.{name}.self_induce_rate: only adversarial actors induce threats")

    orc = cfg["oracles"]
    if len(orc["classes"]) < 2:
        errors.append("oracles.classes: at least 2 classes (PREVENTION §9.5)")
    if set(orc["ttl_seconds"]) != set(orc["classes"]):
        errors.append("oracles.ttl_seconds: exactly one TTL per oracle class (ORACLE §9)")
    for cls, ttl in orc["ttl_seconds"].items():
        if _is_num(ttl) and ttl <= 0:
            errors.append(f"oracles.ttl_seconds.{cls}: must be > 0")
    if orc["noise_sigma"] < 0:
        errors.append("oracles.noise_sigma: must be >= 0")
    if not _in_unit(orc["dropout_rate"]):
        errors.append("oracles.dropout_rate: must be in [0, 1]")
    for key in ("measurement_delay_seconds", "arrival_delay_seconds"):
        if orc[key][0] < 0:
            errors.append(f"oracles.{key}: must be >= 0")
    ld = orc["linkage_detection"]
    if not _in_unit(ld["detection_probability"]):
        errors.append("oracles.linkage_detection.detection_probability: must be in [0, 1]")
    for key in ("detected_score_range", "undetected_score_range"):
        if not (_in_unit(ld[key][0]) and _in_unit(ld[key][1])):
            errors.append(f"oracles.linkage_detection.{key}: must be within [0, 1]")

    attack = cfg["attack"]["oracle_bias"]
    if attack is not None:
        unknown = set(attack["classes"]) - set(orc["classes"])
        if unknown:
            errors.append(f"attack.oracle_bias.classes: unknown classes {sorted(unknown)}")


def validate_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a configuration; raise ConfigError listing every problem."""
    if isinstance(cfg, dict) and cfg.get("schema_version") == 2:
        raise ConfigError(
            "schema_version 2 is not accepted by engine 2.1: add domain.actor_order, "
            "protocol.ttl_reference and protocol.recurrence.history, set schema_version: 3; "
            "or run schema 2 configs with tag v2.0.0")
    errors: List[str] = []
    _check(cfg, SCHEMA, "config", errors)
    if not errors:
        _cross_checks(cfg, errors)
    if errors:
        raise ConfigError("invalid configuration:\n  " + "\n  ".join(errors))
    return cfg


# ── canonical form and digests ──────────────────────────────────────────

def canonical_json(obj: Any) -> str:
    """Deterministic JSON text: sorted keys, no whitespace, ASCII only."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_inputs(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """The configuration that determines the computation (output path excluded)."""
    return {k: copy.deepcopy(v) for k, v in cfg.items() if k != "output"}


def config_digest(cfg: Dict[str, Any]) -> str:
    return sha256_text(canonical_json(run_inputs(cfg)))


# ── overlays (CLI overrides, candidates) ────────────────────────────────

def deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Return base with overlay applied; mappings merge, everything else replaces."""
    out = copy.deepcopy(base)
    for key, val in overlay.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = copy.deepcopy(val)
    return out


def overlay_assignments(overlay: Dict[str, Any], prefix: Tuple[str, ...] = ()) -> Dict[Tuple[str, ...], Any]:
    """What an overlay assigns under deep_merge, as {path tuple: value}.

    A non-empty mapping is merged into the base, so its keys are walked; any other
    value (scalar, list, null) and an empty mapping (whose effect depends on the base:
    it replaces a null) is an assignment of that whole value at its path.  Paths are
    tuples of segments, never dotted strings, because mapping keys are data.
    """
    flat: Dict[Tuple[str, ...], Any] = {}
    for key, val in overlay.items():
        path = prefix + (key,)
        if isinstance(val, dict) and val:
            flat.update(overlay_assignments(val, path))
        else:
            flat[path] = val
    return flat


def apply_cli_overrides(cfg: Dict[str, Any], seed: Optional[int] = None,
                        zones: Optional[int] = None, days: Optional[int] = None,
                        output_dir: Optional[str] = None) -> Dict[str, Any]:
    overlay: Dict[str, Any] = {}
    sim: Dict[str, Any] = {}
    if seed is not None:
        sim["seed"] = seed
    if zones is not None:
        sim["num_zones"] = zones
    if days is not None:
        sim["num_days"] = days
    if sim:
        overlay["simulation"] = sim
    if output_dir is not None:
        overlay["output"] = {"directory": output_dir}
    return deep_merge(cfg, overlay)
