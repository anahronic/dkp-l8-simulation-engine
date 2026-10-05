"""Schema v2: every key required, unknown keys rejected, cross-field checks (L1, N6)."""

import copy

import pytest

from simulation.core.config import ConfigError, config_digest, load_config, validate_config
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import MAIN, SMOKE, main_config


def test_shipped_configs_validate():
    validate_config(load_config(MAIN))
    validate_config(load_config(SMOKE))


def test_missing_key_is_an_error():
    cfg = load_config(MAIN)
    del cfg["protocol"]["recurrence"]["threshold"]
    with pytest.raises(ConfigError, match=r"recurrence\.threshold: required key missing"):
        validate_config(cfg)


def test_missing_channel_weight_is_an_error():
    """v1 silently used W = 1.0 for a channel without weight."""
    cfg = load_config(MAIN)
    del cfg["domain"]["channels"]["intrusion"]["weight"]
    with pytest.raises(ConfigError, match=r"intrusion\.weight: required key missing"):
        validate_config(cfg)


def test_unknown_key_is_an_error():
    """v1 accepted oracles.bias_range and never used it (N6)."""
    cfg = load_config(MAIN)
    cfg["oracles"]["bias_rang"] = [0.0, 0.1]
    with pytest.raises(ConfigError, match=r"oracles\.bias_rang: unknown key"):
        validate_config(cfg)


def test_ticks_must_partition_the_civil_day():
    cfg = load_config(MAIN)
    cfg["time"]["tick_seconds"] = 3000
    with pytest.raises(ConfigError, match="one civil day"):
        validate_config(cfg)


def test_ttl_required_for_every_class():
    cfg = load_config(MAIN)
    del cfg["oracles"]["ttl_seconds"]["lidar"]
    with pytest.raises(ConfigError, match="one TTL per oracle class"):
        validate_config(cfg)


def test_weight_above_one_is_allowed_negative_is_not():
    """PREVENTION §3.7: non-negative scalar, no upper bound (L1)."""
    cfg = load_config(MAIN)
    cfg["domain"]["channels"]["intrusion"]["weight"] = 2.5
    validate_config(cfg)
    cfg["domain"]["channels"]["intrusion"]["weight"] = -0.1
    with pytest.raises(ConfigError, match="weight: must be >= 0"):
        validate_config(cfg)


def test_only_adversarial_actors_induce_threats():
    cfg = load_config(MAIN)
    cfg["domain"]["actors"]["patrol_worker"]["self_induce_rate"] = 0.1
    with pytest.raises(ConfigError, match="only adversarial actors induce threats"):
        validate_config(cfg)


def test_run_refuses_invalid_config():
    cfg = main_config()
    del cfg["attack"]
    with pytest.raises(ConfigError):
        run_simulation(cfg, write=False)


def test_config_digest_ignores_output_path_only():
    a = main_config(out="x/one")
    b = main_config(out="y/two")
    assert config_digest(a) == config_digest(b)
    c = copy.deepcopy(a)
    c["protocol"]["epsilon_consistency"] = 0.2
    assert config_digest(c) != config_digest(a)
