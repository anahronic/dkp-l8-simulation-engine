"""§8 ZKP: placeholder only — the bench never claims verification."""

import pytest

from simulation.core.privacy import PlaceholderZKPProvider, ZKPProof, ZKPProvider
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import main_config


def test_provider_interface_exists():
    assert hasattr(ZKPProvider, "create_proof") and hasattr(ZKPProvider, "verify_proof")


def test_placeholder_creates_stub_proof():
    proof = PlaceholderZKPProvider().create_proof("actor-001", 0.3)
    assert isinstance(proof, ZKPProof)
    assert proof.verified is False and proof.metadata.get("l8_stub") is True
    assert len(proof.proof_data) == 0


def test_placeholder_verify_raises():
    provider = PlaceholderZKPProvider()
    with pytest.raises(NotImplementedError, match="L8 simulation scope"):
        provider.verify_proof(provider.create_proof("actor-001", 0.5))


def test_records_say_proofs_are_unverified():
    res = run_simulation(main_config(days=2), write=False)
    zkp = [r["zkp"] for r in res.records if r["zkp"] is not None]
    assert zkp and all(z == {"provider": "PlaceholderZKPProvider", "verified": False} for z in zkp)


def test_manifest_lists_zkp_as_unverified(tmp_path):
    res = run_simulation(main_config(days=1, out=str(tmp_path / "o")), write=True)
    assert any("zero-knowledge" in u for u in res.manifest["unverified"])


def test_no_raw_behavioral_logs_in_records():
    res = run_simulation(main_config(days=1), write=False)
    forbidden = {"raw_log", "behavior_log", "trajectory", "video", "position"}
    for r in res.records:
        assert not (set(r) & forbidden)
