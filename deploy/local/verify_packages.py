"""Replay checkpoint packages, compare actual results, and verify new packages.

Run from the desired engine root:
python /path/to/verify_packages.py PACKAGES_DIR OUT.json [--regenerate OUT_DIR]
An identity change is reported, never hidden by rewriting historical identifiers.
"""
import argparse
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path.cwd()))
from lab.core.export import build_package, replay
from lab.core.run import run_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--regenerate", type=Path)
    args = parser.parse_args()
    rows = []
    if args.regenerate:
        args.regenerate.mkdir(parents=True, exist_ok=True)
    for path in sorted(args.packages.glob("*.zip")):
        original = replay(path.read_bytes())
        row = {"package": path.name, "historical_replay": original}
        if args.regenerate:
            with zipfile.ZipFile(path) as archive:
                request = json.loads(archive.read("request.json"))
                old = json.loads(archive.read("result.json"))
            records = {}
            fresh = run_request(request, records_out=records)
            row["same_outputs_and_checks"] = all(
                old["variants"][name]["outputs"] == variant["outputs"] and
                old["variants"][name]["checks"] == variant["checks"]
                for name, variant in fresh["variants"].items())
            package = build_package(fresh, records)
            (args.regenerate / path.name).write_bytes(package)
            row["new_package_replay"] = replay(package)
        rows.append(row)
    result = {"packages": len(rows), "historical_verified": sum(r["historical_replay"]["verified"] for r in rows),
              "rows": rows}
    if args.regenerate:
        result.update(unchanged_outputs_and_checks=sum(r["same_outputs_and_checks"] for r in rows),
                      regenerated_verified=sum(r["new_package_replay"]["verified"] for r in rows))
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}))
    assert rows
    if args.regenerate:
        assert result["unchanged_outputs_and_checks"] == result["regenerated_verified"] == len(rows)
    else:
        assert result["historical_verified"] == len(rows)


if __name__ == "__main__":
    main()
