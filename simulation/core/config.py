"""
Config loader — reads YAML configuration files.

All simulation parameters come from config. No hardcoded thresholds
except deterministic test vectors.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

import yaml


def load_config(path: str) -> Dict[str, Any]:
    """Load a YAML config file and return as dict."""
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    if cfg is None:
        raise ValueError(f"Empty config file: {path}")
    return cfg


def save_config_snapshot(cfg: Dict[str, Any], output_dir: str) -> None:
    """Persist the exact config used for a run — reproducibility."""
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "config_snapshot.json"), "w") as f:
        json.dump(cfg, f, indent=2, default=str)


def merge_cli_overrides(cfg: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Apply CLI-provided overrides on top of file config."""
    merged = dict(cfg)
    for key, val in overrides.items():
        if val is not None:
            merged[key] = val
    return merged
