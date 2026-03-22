# DKP L8 Simulation Engine

Deterministic simulation engine for verifying **DKP-1-PREVENTION-001 v1.0** —
Preventive Impact Attribution Protocol.

## Architecture

```
simulation/
├── core/               # Protocol-agnostic engine primitives
│   ├── rng.py          # Deterministic xoshiro256** PRNG
│   ├── zones.py        # Protected Zone generator
│   ├── oracles.py      # Multi-class oracle sensor models
│   ├── actors.py       # Subject strategy models (5 types)
│   ├── events.py       # Event engine — threat activation loop
│   ├── metrics.py      # Metrics accumulator + output writer
│   └── config.py       # YAML config loader
├── modules/
│   └── prevention/     # DKP-1-PREVENTION-001 implementation
│       ├── protocol_adapter.py   # EXACT protocol math (§3–§9)
│       ├── scenarios.py          # Threat scenario presets
│       ├── calibration.py        # §14 parameter calibration
│       ├── test_vectors.py       # Hand-calculated expected values
│       └── domain_childcare.py   # Childcare sandbox domain
├── configs/            # YAML run configurations
├── specs/imports/      # Frozen protocol specifications
├── outputs/            # Simulation output artifacts
└── run_prevention_simulation.py  # CLI entry point
```

## Protocol Math

```
TAₖ valid       ⇔ confirmations ≥ 2 independent oracle classes
Δ_oracle         = max(intensity) − min(intensity)
Consistent:      Δ_oracle ≤ ε_consistency → TAₖ_intensity = min(intensities)
Inconsistent:    Δ_oracle > ε_consistency → SPDₖ = informational

Sₖ = clamp(0, 1, (TAₖ_intensity − SEₖ_intensity) / TAₖ_intensity)
If SE ≥ TA:      Sₖ = 0, SPDₖ = 0

SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ
PS_subject = Σ SPDₖ

Self-induced:    linkage > θ → Tₖ = 0
Pattern repeat:  Tₖ ↓ (decay after 3 occurrences)
Low coverage:    Cₖ ↓; no data → SPDₖ = 0
```

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Smoke test (fast — 1 zone, 2 days, 4 ticks/day)
python -m simulation.run_prevention_simulation --smoke

# Full childcare simulation
python -m simulation.run_prevention_simulation \
  --config simulation/configs/prevention_childcare_v0_1.yaml \
  --verbose

# Override seed + zones
python -m simulation.run_prevention_simulation \
  --config simulation/configs/prevention_childcare_v0_1.yaml \
  --seed 123 --zones 5 --days 60
```

## CLI Options

| Flag | Description |
|------|-------------|
| `--config PATH` | YAML config file |
| `--smoke` | Fast smoke test (ignores --config) |
| `--seed INT` | Override simulation seed |
| `--zones INT` | Override zone count |
| `--days INT` | Override day count |
| `--output-dir DIR` | Override output directory |
| `--verbose` | Print day-level progress |

## Testing

```bash
pytest tests/ -v
```

### Test Coverage

| Test File | Protocol Section |
|-----------|-----------------|
| `test_vectors.py` | §5 SPDₖ calculation, §3.6 suppression |
| `test_oracle_consistency.py` | §3.3 regime switching |
| `test_reproducibility.py` | Determinism: same seed → same output |
| `test_self_induced.py` | §9.1 self-induced risk, §9.3 recurrence |
| `test_informational.py` | §3.3.2 informational downgrade |

## Determinism

All randomness flows through a single seeded xoshiro256** PRNG.
Each zone gets a deterministic fork keyed by zone ID.
Same seed → identical output on any platform.

## Domain: Childcare

6 threats × 5 actor types × 4 oracle classes:

**Threats:** unauthorized_adult_proximity, intrusion, unattended_child_exit,
hazardous_trajectory, dangerous_object, congestion_escalation

**Actors:** patrol_worker, weak_worker, passive, adversarial, optimizer

**Oracles:** optical, thermal, lidar, access

## Dependencies

- Python ≥ 3.9
- PyYAML ≥ 6.0
- pytest ≥ 7.0 (test only)
- No runtime dependency on market-lens or external services

## Output

Each run writes to the configured output directory:
- `metrics.json` — full event-level records
- `metrics.csv` — tabular export
- `summary.txt` — human-readable summary
- `summary.json` — machine-readable summary
- `config_snapshot.json` — exact config used

## Protocol Reference

Frozen spec: `simulation/specs/imports/DKP-1-PREVENTION-001_v1_0.md`
