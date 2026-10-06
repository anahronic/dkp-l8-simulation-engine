#!/usr/bin/env python3
"""
Identities of a fixed set of computations, for comparison with the browser runtime.

    python -m lab.tools.pyodide_check BUNDLE_DIR   (CPython; prints JSON)
    node lab/tools/pyodide_check.mjs BUNDLE_DIR    (Pyodide; runs this same function)

The two outputs must be equal: same code, same inputs, same input_id and result_id.
"""

from __future__ import annotations

import json
import sys


def identities() -> dict:
    from lab import api
    from simulation.core.config import deep_merge, load_config
    from simulation.run_prevention_simulation import run_simulation
    smoke = run_simulation(deep_merge(load_config("simulation/configs/prevention_childcare_fast_smoke.yaml"),
                                      {"output": {"directory": "unused"}}), write=False)
    out = {"bench_smoke": [smoke.manifest["input_id"], smoke.manifest["result_id"]]}
    for mod in ("time", "work_cycle", "failure_chain", "prevention"):
        req = api.example_request(mod)
        req["variants"] = req["variants"][:2]
        doc = api.run_payload(req)
        out[mod] = [doc["input_id"], doc["result_id"]]
    return out


if __name__ == "__main__":
    print(json.dumps(identities(), sort_keys=True))
