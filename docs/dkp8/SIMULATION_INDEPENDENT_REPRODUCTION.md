# DKP-8-SIMULATION-001 — independent reproduction (2026-11-17)

§8: a change is eligible only if it is "reproducible by independent nodes"; §11: simulations are deterministic,
expose configuration/assumptions/parameters and allow independent re-execution.

## 1. Mechanism (`dkp8.reproduction`)

- **Package** `dkp-l8-repro-package/1` (`python -m dkp8 repro pack OUT.zip [--config C]`): resolved inputs
  (`config_resolved.json`), the expected manifest (`input_id`, `result_id`, result core digests), engine commit and code
  identity, `REPRODUCE.md`, `SHA256SUMS`. Fixed ZIP timestamps → the package is byte-stable.
- **Verification** (`python -m dkp8 repro verify ZIP --operator NAME [--level R1|R2] [--node-key FILE]`): checks
  SHA256SUMS, re-runs the bench, writes a record `dkp-l8-reproduction/1` (expected vs observed ids, platform, host
  fingerprint, operator, level; signed with the node key for R3/R4).
- **Assessment** (`reproduction.assess`, used by the gate): counts levels; a mismatch blocks the change; only R3/R4
  records signed by a node registered in the trust store count as independent nodes.

| Level | Meaning | Counts for §8 |
|---|---|---|
| R0 | same process | no |
| R1 | same host, fresh process | no |
| R2 | different host/OS, same operator | no |
| R3 | different registered operator, signed record | **yes** |
| R4 | R3 + independent implementation | **yes** |

## 2. Evidence today

| Run | Level | Result |
|---|---|---|
| Workstation, Windows, Python 3.12: pack + verify of the smoke scenario | R1 | `result_id 77d06a9bcae39161…` reproduced; package `9c8aaf2f31034855…` byte-stable |
| GitHub Actions matrix (Linux/Windows/macOS × 3.10/3.12/3.13): pinned result ids + pack/verify step per OS | R2-equivalent (one operator) | pinned ids asserted by the test suite; new step added 2026-11-17 |
| Pyodide (browser) runtime of the Lab | R2-equivalent | same ids as CPython (existing CI job `browser-runtime`) |
| Registered independent node | R3 | **none** — no node is designated (DKP8-Q-02) |

**INDEPENDENT_REPRODUCTION_VALIDATED: NO.** Determinism across platforms is shown; independence of operators is not.

## 3. How an independent node would take part

1. The node operator generates an Ed25519 key, publishes the public key and an identity statement.
2. The governance decision (DKP8-Q-02) registers it in `dkp8/trust-store.json` (`nodes`) by a reviewed commit.
3. The operator checks out the engine at the package's commit, runs `repro verify … --level R3 --node-key <file>` and
   returns the signed record; the gate counts it.
