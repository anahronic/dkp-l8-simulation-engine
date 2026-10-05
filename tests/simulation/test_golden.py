"""Pinned result identity of the smoke scenario.

The value was computed on Windows 10 (CPython 3.12.10, MSVC CRT) and Linux
(WSL2 Ubuntu 22.04, CPython 3.10.12, glibc 2.35) on 2026-10-05 for engine 2.1.0; CI checks it
on Linux, Windows and macOS.  A change of this value means the computation
changed: update it only together with a CHANGELOG entry.
"""

from simulation.core.config import deep_merge, load_config
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import SMOKE

SMOKE_RESULT_ID = "77d06a9bcae3916123d1c5b61fb8cda4d83c682c99f6153edf006b2ec9912186"   # engine 2.1.0


def test_smoke_result_id_is_platform_independent(tmp_path):
    cfg = deep_merge(load_config(SMOKE), {"output": {"directory": str(tmp_path / "smoke")}})
    res = run_simulation(cfg, write=True)
    assert res.manifest["result_id"] == SMOKE_RESULT_ID
