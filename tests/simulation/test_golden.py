"""Pinned result identity of the smoke scenario.

The value was computed on Windows 10 (CPython 3.12.10, MSVC CRT) and Linux
(WSL2 Ubuntu 22.04, CPython 3.10.12, glibc 2.35) on 2026-10-05; CI checks it
on Linux, Windows and macOS.  A change of this value means the computation
changed: update it only together with a CHANGELOG entry.
"""

from simulation.core.config import deep_merge, load_config
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import SMOKE

SMOKE_RESULT_ID = "dc813ca13486a2a05863183a2621799b408bbef70328c29e15fb7370143666b3"


def test_smoke_result_id_is_platform_independent(tmp_path):
    cfg = deep_merge(load_config(SMOKE), {"output": {"directory": str(tmp_path / "smoke")}})
    res = run_simulation(cfg, write=True)
    assert res.manifest["result_id"] == SMOKE_RESULT_ID
