"""Command line of the DKP-8 infrastructure.  ``python -m dkp8 <command> --help``.

  status                         overall L8 status (trust store, enforceability, indices, invariants, traceability)
  trace [--md FILE]              requirements traceability matrix
  catalog                        run the synthetic scenario catalogue through the gate
  gate DOSSIER.json              acceptance-gate decision for a change dossier (JSON to stdout)
  bundle template|validate|sign|status ...
  repro pack OUT.zip [--config C] | repro verify ZIP --operator NAME [--level R1|R2] [--node-key FILE]
  enforceability | dependents DOC | invariants | composite
  workbench [--out DIR]          calibration workbench: every missing L8 value, per protocol, with bundle templates
  redteam [--json FILE]          synthetic red-team models of the v3 remediation proposals T1-T7
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dkp8 import bundle, composite, enforcement, gate, invariants, redteam, reproduction, scenarios, traceability, trust


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _print(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")


def cmd_status(_):
    store = trust.load()
    rows = enforcement.enforceability()
    _print({
        "trust_store": {"authorities": len(store["authorities"]), "nodes": len(store["nodes"]),
                        "development_keys": len(store["development_keys"])},
        "calibration_bundles": 0,
        "enforceability": {s: sum(1 for r in rows if r["state"] == s) for s in sorted({r["state"] for r in rows})},
        "composite_indices": {i["index"]: i["status"] for i in composite.inventory()},
        "invariants": {i["id"]: i["computability"] for i in invariants.REGISTRY},
        "traceability": traceability.summary(),
        "operational": "NOT OPERATIONAL: no L8 signing authority, no independent node, no calibration value with "
                       "provenance, no PTL data (see SIMULATION_CALIBRATION_GAPS.md)",
    })


def cmd_trace(a):
    text = traceability.markdown()
    if a.md:
        Path(a.md).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {a.md}")
    else:
        sys.stdout.write(text)


def cmd_catalog(_):
    store = trust.load()
    ok = True
    for case in scenarios.catalog():
        try:
            got = gate.evaluate(case["dossier"], store)["decision"]
        except gate.DossierError:
            got = "REFUSED"
        ok &= got == case["expect"]
        print(f"{'ok ' if got == case['expect'] else 'BAD'} {case['id']:26} {got:18} {case['purpose']}")
    return 0 if ok else 1


def cmd_gate(a):
    try:
        _print(gate.evaluate(_load(a.dossier), trust.load(a.trust)))
    except gate.DossierError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


def cmd_bundle(a):
    if a.action == "template":
        _print(bundle.template({"kind": a.kind, "protocol_id": a.protocol, "source_sha256": a.source_sha256}))
    elif a.action == "validate":
        problems = bundle.validate(_load(a.file))
        _print({"well_formed": not problems, "problems": problems})
        return 0 if not problems else 1
    elif a.action == "sign":
        if a.dev:
            secret = trust.DEV_SEED
        elif a.key_file:
            secret = bytes.fromhex(Path(a.key_file).read_text().strip())
        else:
            print("choose --dev (public development key, never an authority) or --key-file", file=sys.stderr)
            return 2
        problems = bundle.validate(_load(a.file))
        if problems:
            _print({"refused": "bundle is not well-formed", "problems": problems})
            return 1
        _print(bundle.sign(_load(a.file), secret))
    elif a.action == "status":
        events = _load(a.events) if a.events else []
        _print(bundle.status(_load(a.file), a.at, trust.load(a.trust), events))


def cmd_repro(a):
    if a.action == "pack":
        _print(reproduction.make_package(a.config, a.out))
    else:
        secret = bytes.fromhex(Path(a.node_key).read_text().strip()) if a.node_key else None
        record = reproduction.verify_package(a.package, a.operator, a.level, secret, a.at)
        _print(record)
        return 0 if record["body"]["match"] else 1


def cmd_enforceability(_):
    for r in enforcement.enforceability():
        print(f"{r['state']:16} {r['doc']:28} {r['at']:6} {r['scope'][:70]}")


def cmd_dependents(a):
    _print({"changed": a.doc, "must_be_resimulated": enforcement.dependents(a.doc)})


def cmd_invariants(_):
    _print(invariants.REGISTRY)


def cmd_composite(_):
    _print(composite.inventory())


def cmd_workbench(a):
    cmap = json.loads((enforcement.REGISTRY / "calibration_map.json").read_text(encoding="utf-8"))
    out = Path(a.out)
    (out / "templates").mkdir(parents=True, exist_ok=True)
    by_doc = {}
    for e in cmap["deferred_to_l8"]:
        by_doc.setdefault(e["doc"], []).append(("L8 calibration", e["parameter"], e["at"], e["text"]))
    for e in cmap["missing_values"]:
        by_doc.setdefault(e["doc"], []).append((e.get("gap_type") or e.get("origin") or "missing", e["value"], e["at"], e["text"]))
    lines = ["# L8 calibration workbench", "", "Every value the corpus leaves to L8 calibration or does not give, by "
             "protocol. A value enters a Calibration Bundle only with provenance (`ptl_dataset`, `author_decision`, "
             "`simulation_output`; `synthetic_fixture` makes the bundle SYNTHETIC and never enforceable). Fill a "
             "template in `templates/`, then `python -m dkp8 bundle validate <file>`. Nothing here is a value.", ""]
    for doc in sorted(by_doc):
        lines += [f"## {doc}", "", "| Kind | Quantity | § | Text |", "|---|---|---|---|"]
        for kind, name, at, text in by_doc[doc]:
            lines.append(f"| {kind} | {name} | {at} | {' '.join(str(text).split())[:140].replace('|', '/')} |")
        lines.append("")
        tpl = bundle.template({"kind": "parameter", "protocol_id": doc, "source_sha256": None})
        (out / "templates" / f"{doc}.bundle-template.json").write_text(json.dumps(tpl, indent=1), encoding="utf-8")
    lines += ["## Composite indices", ""] + [f"- **{i['index']}** — {i['status']}; questions: " + " / ".join(i["questions"])
                                            for i in composite.inventory()]
    (out / "WORKBENCH.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out / 'WORKBENCH.md'} and {len(by_doc)} templates")


def cmd_redteam(a):
    import json as _json
    from fractions import Fraction
    runs = redteam.run_all()
    text = _json.dumps(runs, default=lambda o: str(o) if isinstance(o, Fraction) else repr(o), indent=1, ensure_ascii=False)
    if a.json:
        Path(a.json).write_text(text + chr(10), encoding="utf-8", newline=chr(10))
        print(f"wrote {a.json} ({len(runs)} scenarios)")
    else:
        for r in runs:
            print(f"{r['package']} {r['id']:34} {r['kind'][:38]:38} {r['outcome'][:90]}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m dkp8", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    t = sub.add_parser("trace"); t.add_argument("--md"); t.set_defaults(fn=cmd_trace)
    sub.add_parser("catalog").set_defaults(fn=cmd_catalog)
    g = sub.add_parser("gate"); g.add_argument("dossier"); g.add_argument("--trust"); g.set_defaults(fn=cmd_gate)
    b = sub.add_parser("bundle"); b.add_argument("action", choices=("template", "validate", "sign", "status"))
    b.add_argument("file", nargs="?"); b.add_argument("--protocol"); b.add_argument("--kind", default="parameter")
    b.add_argument("--source-sha256"); b.add_argument("--dev", action="store_true"); b.add_argument("--key-file")
    b.add_argument("--at"); b.add_argument("--events"); b.add_argument("--trust"); b.set_defaults(fn=cmd_bundle)
    r = sub.add_parser("repro"); r.add_argument("action", choices=("pack", "verify"))
    r.add_argument("out_or_package"); r.add_argument("--config"); r.add_argument("--operator", default="anonymous")
    r.add_argument("--level", default="R1"); r.add_argument("--node-key"); r.add_argument("--at", default="1970-01-01T00:00:00Z")
    r.set_defaults(fn=cmd_repro)
    sub.add_parser("enforceability").set_defaults(fn=cmd_enforceability)
    d = sub.add_parser("dependents"); d.add_argument("doc"); d.set_defaults(fn=cmd_dependents)
    sub.add_parser("invariants").set_defaults(fn=cmd_invariants)
    sub.add_parser("composite").set_defaults(fn=cmd_composite)
    rt = sub.add_parser("redteam"); rt.add_argument("--json"); rt.set_defaults(fn=cmd_redteam)
    w = sub.add_parser("workbench"); w.add_argument("--out", default="dkp8-workbench"); w.set_defaults(fn=cmd_workbench)
    a = p.parse_args(argv)
    if a.cmd == "repro":
        a.out = a.package = a.out_or_package
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
