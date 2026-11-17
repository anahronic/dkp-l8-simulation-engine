"""Portable offline check entry point; no author-specific paths, installs or network.

python deploy/local/run_checks.py OUT [--skip-pytest]
Browser checks of the Lab page: deploy/local/offline_browser_check.mjs (needs a local Playwright).
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "TEMP": str(out), "TMP": str(out)}
    commands = [] if args.skip_pytest else [
        ("targeted", ["-m", "pytest", "tests/server", "-q", "--basetemp=" + str(out / "targeted-tmp")]),
        ("full", ["-m", "pytest", "-q", "-x", "--basetemp=" + str(out / "full-tmp")])]
    commands += [(name, ["-m", "lab.tools." + name, *(["--check"] if name != "check_registry" else [])])
                 for name in ("check_registry", "sync_coverage", "reconcile", "trace", "calibration_map")]
    for name, command in commands:
        with (out / (name + ".log")).open("w", encoding="utf-8", newline="\n") as file:
            result = subprocess.run([sys.executable, *command], cwd=root, env=env, stdout=file,
                                    stderr=subprocess.STDOUT)
        print(name, result.returncode, flush=True)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
