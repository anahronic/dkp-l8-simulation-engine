"""
Lab CLI.

    python -m lab catalog                         coverage of every document (from the registry)
    python -m lab modules                         installed modules and their examples
    python -m lab example MODULE [EXAMPLE ...] --out PACKAGE.zip
                                                  run module examples as variants of one experiment
    python -m lab run REQUEST.json --out PACKAGE.zip
    python -m lab replay PACKAGE.zip              recompute and compare ids
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from lab.core.export import build_package, replay
from lab.core.registry import coverage_table
from lab.core.run import INPUT_SCHEMA, run_request


def _safe_stdout() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def _run_and_package(request, out: str) -> int:
    records: dict = {}
    doc = run_request(request, progress=lambda f, m: print(f"  {f:4.0%} {m}", file=sys.stderr),
                      records_out=records)
    data = build_package(doc, records)
    with open(out, "wb") as f:
        f.write(data)
    for name, v in doc["variants"].items():
        print(f"{name}: {v['summary']['sentence']['en']}")
    print(f"input_id  {doc['input_id']}\nresult_id {doc['result_id']}\npackage   {out}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    _safe_stdout()
    ap = argparse.ArgumentParser(prog="python -m lab")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("catalog")
    sub.add_parser("modules")
    ex = sub.add_parser("example")
    ex.add_argument("module")
    ex.add_argument("examples", nargs="*")
    ex.add_argument("--out", required=True)
    rn = sub.add_parser("run")
    rn.add_argument("request")
    rn.add_argument("--out", required=True)
    rp = sub.add_parser("replay")
    rp.add_argument("package")
    args = ap.parse_args(argv)

    if args.cmd == "catalog":
        rows = coverage_table()
        for r in rows:
            cov = ", ".join(f"{k} {v}" for k, v in sorted(r["coverage"].items())) or "not registered"
            print(f"{r['id']:34s} {r['kind']:9s} {r['requirements']:3d}  {cov}")
        print(f"documents {len(rows)}, protocols {sum(1 for r in rows if r['kind'] == 'protocol')}")
        return 0
    if args.cmd == "modules":
        from lab.modules import MODULES
        for m in MODULES.values():
            print(f"{m.id:12s} {m.version}  {', '.join(m.protocols)}  examples: {', '.join(sorted(m.examples()))}")
        return 0
    if args.cmd == "example":
        from lab.modules import MODULES
        m = MODULES[args.module]
        names = args.examples or m.ordered_examples()
        req = {"schema": INPUT_SCHEMA, "module": m.id,
               "variants": [{"name": n, "input": m.examples()[n]} for n in names]}
        return _run_and_package(req, args.out)
    if args.cmd == "run":
        with open(args.request, encoding="utf-8") as f:
            return _run_and_package(json.load(f), args.out)
    if args.cmd == "replay":
        with open(args.package, "rb") as f:
            rep = replay(f.read())
        print(json.dumps(rep, indent=1))
        return 0 if rep["same_input"] and rep["same_result"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
