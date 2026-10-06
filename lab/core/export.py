"""
Replay package (TZ §9 minimum package) and its verification.

Contents of the zip:
    request.json        the request exactly as resolved (all defaults visible)
    result.json         reproducible result document (input_id, result_id, outputs, checks)
    report.en.md / report.ru.md / report.html
    provenance.json     machine, Python, git commit, time — not part of any id
    records/<variant>.jsonl   detailed rows when the module produces them
    REPLAY.md           how to obtain the pinned code and repeat the computation
    SHA256SUMS          digests of every other file
"""

from __future__ import annotations

import datetime
import hashlib
import io
import json
import platform
import sys
import zipfile
from typing import Any, Dict, Optional

from lab.core.report import html_page, markdown
from lab.core.run import canonical_json, run_request


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def provenance() -> Dict[str, Any]:
    try:
        from simulation.core.manifest import git_provenance
        git = git_provenance()
    except Exception:  # pragma: no cover - e.g. in a browser runtime
        git = {"git_commit": None, "git_dirty": None}
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "platform": platform.platform(), **git,
            "packaged_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}


REPLAY = """# Replay

1. Get the code: `git clone https://github.com/anahronic/dkp-l8-simulation-engine`
   and check out the commit named in provenance.json (or the release tag).
2. `pip install -r requirements.txt`
3. `python -m lab replay <this zip>` — recomputes request.json and compares
   input_id and result_id with result.json.

input_id names what was computed (code digests, corpus, module version, inputs);
result_id names what came out. Provenance (machine, time) is not part of either.
"""


def build_package(doc: Dict[str, Any], records: Optional[Dict[str, list]] = None,
                  prov: Optional[Dict[str, Any]] = None) -> bytes:
    files: Dict[str, bytes] = {
        "request.json": _dumps(doc["request"]),
        "result.json": _dumps(doc),
        "report.en.md": markdown(doc, "en").encode("utf-8"),
        "report.ru.md": markdown(doc, "ru").encode("utf-8"),
        "report.html": html_page(doc, "en").encode("utf-8"),
        "provenance.json": _dumps(prov or provenance()),
        "REPLAY.md": REPLAY.encode("utf-8"),
    }
    for name, rows in (records or {}).items():
        files[f"records/{name}.jsonl"] = "".join(
            json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n" for r in rows).encode()
    sums = "".join(f"{hashlib.sha256(files[n]).hexdigest()}  {n}\n" for n in sorted(files))
    files["SHA256SUMS"] = sums.encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in sorted(files):
            info = zipfile.ZipInfo(n, date_time=(1980, 1, 1, 0, 0, 0))   # fixed time: identical zips
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, files[n])
    return buf.getvalue()


class ReplayMismatch(RuntimeError):
    pass


def replay(package: bytes) -> Dict[str, Any]:
    """Verify the package digests, recompute, compare ids.  Returns a report dict."""
    with zipfile.ZipFile(io.BytesIO(package)) as z:
        names = set(z.namelist())
        sums = z.read("SHA256SUMS").decode()
        for line in sums.splitlines():
            digest, name = line.split("  ", 1)
            if hashlib.sha256(z.read(name)).hexdigest() != digest:
                raise ReplayMismatch(f"package file changed: {name}")
        listed = {line.split("  ", 1)[1] for line in sums.splitlines()}
        if names - listed - {"SHA256SUMS"}:
            raise ReplayMismatch(f"unlisted files: {sorted(names - listed - {'SHA256SUMS'})}")
        request = json.loads(z.read("request.json"))
        stored = json.loads(z.read("result.json"))
    fresh = run_request(request)
    report = {"stored_input_id": stored["input_id"], "fresh_input_id": fresh["input_id"],
              "stored_result_id": stored["result_id"], "fresh_result_id": fresh["result_id"],
              "same_input": stored["input_id"] == fresh["input_id"],
              "same_result": stored["result_id"] == fresh["result_id"]}
    if not report["same_input"]:
        report["note"] = ("different input_id: code, corpus, registry or module version differ from the "
                          "package; check out the commit in provenance.json")
    return report
