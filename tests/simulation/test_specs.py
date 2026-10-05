"""The rules the bench relies on are present in the pinned canonical texts."""

import os

from simulation.core.manifest import SPECS_DIR


def _text(name):
    with open(os.path.join(SPECS_DIR, name), encoding="utf-8") as f:
        return f.read()


def test_prevention_rules_used_by_the_bench():
    t = _text("DKP-1-PREVENTION-001.md")
    assert "Residual remains unallocated." in t                 # §6
    assert "attribution ambiguity → SPDₖ = 0" in t              # §12, basis of H-A-2
    assert "Non-negative scalar." in t                          # §3.7, no upper bound (L1)
    assert "repeat(TAₖ pattern) → Tₖ ↓" in t                    # §9.3, H-T-1
    assert "0 \\< (t₁ − t₀) ≤ Δt_int" in t                      # §3.6


def test_identity_no_attribution_state():
    t = _text("DKP-1-IDENTITY-001.md")
    assert "NO_ATTRIBUTION" in t and "INSUFFICIENT_DATA" in t   # §4.1


def test_epistemic_boundaries_fields():
    t = _text("DKP-1-EPISTEMIC-BOUNDARIES-001.md")
    for field in ("scope_ref", "revalidation_required", "dispute_allowed", "ORACLE_CONFLICT",
                  "DEGRADED_SIGNAL", "CONDITIONAL"):
        assert field in t


def test_oracle_ttl_and_time_base_unit():
    assert "All data types SHALL have an explicit TTL." in _text("DKP-0-ORACLE-001.md")
    assert "The base temporal unit of DKP-TIME-001 MUST be the **civil day**." in _text("DKP-0-TIME-001.md")
