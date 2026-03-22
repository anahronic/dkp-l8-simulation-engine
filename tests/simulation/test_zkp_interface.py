"""
Test: ZKP interface — §8 privacy placeholder.

Verifies that:
- ZKPProvider interface exists
- PlaceholderZKPProvider returns stub proofs
- PlaceholderZKPProvider raises NotImplementedError on verify
- Simulation can run with placeholder provider
- No raw behavioral logs in output artifacts
"""

import json
import os
import pytest

from simulation.core.privacy import ZKPProof, ZKPProvider, PlaceholderZKPProvider


class TestZKPInterface:
    """§8: ZKP provider interface exists and is wired in."""

    def test_provider_interface_exists(self):
        """ZKPProvider ABC exists with required methods."""
        assert hasattr(ZKPProvider, "create_proof")
        assert hasattr(ZKPProvider, "verify_proof")

    def test_placeholder_creates_stub_proof(self):
        """PlaceholderZKPProvider.create_proof returns a ZKPProof stub."""
        provider = PlaceholderZKPProvider()
        proof = provider.create_proof("actor-001", 0.3)

        assert isinstance(proof, ZKPProof)
        assert proof.subject_id == "actor-001"
        assert proof.verified is False
        assert proof.metadata.get("l8_stub") is True
        assert len(proof.proof_data) == 0  # no real crypto at L8

    def test_placeholder_verify_raises(self):
        """PlaceholderZKPProvider.verify_proof raises NotImplementedError."""
        provider = PlaceholderZKPProvider()
        proof = provider.create_proof("actor-001", 0.5)

        with pytest.raises(NotImplementedError, match="L8 simulation scope"):
            provider.verify_proof(proof)

    def test_simulation_runs_with_placeholder(self):
        """Full simulation completes successfully with placeholder ZKP."""
        from simulation.run_prevention_simulation import run_simulation

        cfg = {
            "simulation": {
                "seed": 11111,
                "num_zones": 1,
                "num_days": 1,
                "ticks_per_day": 2,
                "se_ge_ta_probability": 0.0,
                "temporal_invalid_probability": 0.0,
                "se_delay_min": 1.0,
            },
            "protocol": {
                "epsilon_consistency": 0.15,
                "delta_t_int": 30.0,
                "theta_self_induced": 0.5,
                "recurrence_decay": 0.9,
                "recurrence_threshold": 3,
                "coverage_floor": 0.1,
            },
            "domain": {
                "name": "childcare",
                "include_adversarial": False,
                "threat_weights": {
                    "unauthorized_adult_proximity": 0.9,
                    "intrusion": 1.0,
                    "unattended_child_exit": 0.95,
                    "hazardous_trajectory": 0.7,
                    "dangerous_object": 0.8,
                    "congestion_escalation": 0.5,
                },
                "threat_profiles": {
                    "unauthorized_adult_proximity": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                    "intrusion": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                    "unattended_child_exit": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                    "hazardous_trajectory": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                    "dangerous_object": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                    "congestion_escalation": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                },
            },
            "oracles": {"noise_sigma": 0.05, "dropout_rate": 0.0, "bias_range": [0.0, 0.0]},
            "output": {"directory": "/tmp/dkp-l8-zkp-test"},
        }

        summary = run_simulation(cfg)
        assert summary["total_metric_records"] > 0

    def test_no_raw_behavioral_logs_in_output(self):
        """Output artifacts must not contain raw behavioral data."""
        from simulation.run_prevention_simulation import run_simulation

        cfg = {
            "simulation": {
                "seed": 22222,
                "num_zones": 1,
                "num_days": 1,
                "ticks_per_day": 2,
                "se_ge_ta_probability": 0.0,
                "temporal_invalid_probability": 0.0,
                "se_delay_min": 1.0,
            },
            "protocol": {
                "epsilon_consistency": 0.15,
                "delta_t_int": 30.0,
                "theta_self_induced": 0.5,
                "recurrence_decay": 0.9,
                "recurrence_threshold": 3,
                "coverage_floor": 0.1,
            },
            "domain": {
                "name": "childcare",
                "include_adversarial": False,
                "threat_weights": {
                    "unauthorized_adult_proximity": 0.9,
                    "intrusion": 1.0,
                    "unattended_child_exit": 0.95,
                    "hazardous_trajectory": 0.7,
                    "dangerous_object": 0.8,
                    "congestion_escalation": 0.5,
                },
                "threat_profiles": {
                    "unauthorized_adult_proximity": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                    "intrusion": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                    "unattended_child_exit": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                    "hazardous_trajectory": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                    "dangerous_object": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                    "congestion_escalation": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                },
            },
            "oracles": {"noise_sigma": 0.05, "dropout_rate": 0.0, "bias_range": [0.0, 0.0]},
            "output": {"directory": "/tmp/dkp-l8-zkp-output-test"},
        }

        run_simulation(cfg)

        output_dir = "/tmp/dkp-l8-zkp-output-test"
        forbidden_keys = {"gps", "location", "identity", "address", "ssn", "dob"}

        for fname in os.listdir(output_dir):
            if fname.endswith(".json"):
                with open(os.path.join(output_dir, fname)) as f:
                    content = f.read().lower()
                    for key in forbidden_keys:
                        assert key not in content, f"Forbidden key '{key}' found in {fname}"
