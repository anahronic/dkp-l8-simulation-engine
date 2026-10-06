"""
Run a lab experiment: one module, one or more variants on the same world.

Request (schema dkp-lab-input/1):
    {"schema": "dkp-lab-input/1", "module": "<id>",
     "variants": [{"name": "A", "input": {...}}, ...]}

Result (schema dkp-lab-result/1) — reproducible content only:
    identity     lab/engine code digests, corpus and registry digests, module version
    variants     per variant: resolved input, input_id, outputs, checks, summary, result_id
    comparison   the module's comparison metrics side by side (no ranking, no "best")
    input_id     digest of identity + module + all resolved variant inputs
    result_id    digest of every variant's outputs, checks and summary
Machine, time and paths are provenance and are kept out of this document.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

from lab import LAB_VERSION
from lab.core.checks import summarize
from lab.core.registry import REGISTRY, catalog, requirement_ids
from lab.core.schema import LabInputError

LAB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_ROOT = os.path.dirname(LAB_ROOT)
INPUT_SCHEMA = "dkp-lab-input/1"
RESULT_SCHEMA = "dkp-lab-result/1"
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")
MAX_VARIANTS = 6


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _norm_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


def tree_digest(root: str, suffixes=(".py",), skip=("__pycache__", "outputs", "corpus", "web")) -> str:
    files = []
    for dirpath, dirnames, names in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip)
        files += [os.path.join(dirpath, n) for n in sorted(names) if n.endswith(suffixes)]
    h = hashlib.sha256()
    for p in sorted(files, key=lambda p: os.path.relpath(p, ENGINE_ROOT).replace(os.sep, "/")):
        rel = os.path.relpath(p, ENGINE_ROOT).replace(os.sep, "/")
        h.update(rel.encode() + b"\0" + hashlib.sha256(_norm_bytes(p)).digest())
    return h.hexdigest()


def identity() -> Dict[str, Any]:
    from simulation import __version__ as engine_version
    from simulation.core.manifest import engine_code_digest
    return {
        "lab_version": LAB_VERSION,
        "lab_code_digest": tree_digest(LAB_ROOT),
        "registry_digest": tree_digest(REGISTRY, suffixes=(".json",), skip=()),
        "corpus": catalog()["corpus"],
        "engine_version": engine_version,
        "engine_code_digest": engine_code_digest()["sha256"],
    }


def validate_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Check the request envelope and every variant input; return resolved variants."""
    from lab.modules import MODULES
    problems: List[str] = []
    if not isinstance(request, dict):
        raise LabInputError(["request: expected mapping"])
    for k in request:
        if k not in ("schema", "module", "variants"):
            problems.append(f"request.{k}: unknown key")
    if request.get("schema") != INPUT_SCHEMA:
        problems.append(f"request.schema: expected {INPUT_SCHEMA!r}")
    module = MODULES.get(request.get("module"))
    if module is None:
        problems.append(f"request.module: unknown module {request.get('module')!r}; installed: {sorted(MODULES)}")
    variants = request.get("variants")
    if not isinstance(variants, list) or not 1 <= len(variants) <= MAX_VARIANTS:
        problems.append(f"request.variants: 1..{MAX_VARIANTS} variants required")
        variants = []
    if problems:
        raise LabInputError(problems)
    resolved: Dict[str, Dict[str, Any]] = {}
    for i, v in enumerate(variants):
        if not isinstance(v, dict) or set(v) != {"name", "input"}:
            problems.append(f"variants[{i}]: expected {{name, input}}")
            continue
        name = v["name"]
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            problems.append(f"variants[{i}].name: letters, digits, '_' or '-', at most 40")
            continue
        if name in resolved:
            problems.append(f"variants[{i}].name: duplicate {name!r}")
            continue
        try:
            resolved[name] = module.validate(v["input"])
        except LabInputError as exc:
            problems += [f"variants.{name}: {p}" for p in exc.problems]
    if problems:
        raise LabInputError(problems)
    return {"module": module, "variants": resolved}


def run_request(request: Dict[str, Any],
                progress: Optional[Callable[[float, str], None]] = None,
                records_out: Optional[Dict[str, list]] = None) -> Dict[str, Any]:
    checked = validate_request(request)
    module = checked["module"]
    ident = identity()
    doc_reqs = requirement_ids(module.protocols)
    variants_out: Dict[str, Any] = {}
    names = list(checked["variants"])
    for i, name in enumerate(names):
        resolved = checked["variants"][name]

        def sub_progress(frac: float, msg: str, i=i, name=name) -> None:
            if progress:
                progress((i + frac) / len(names), f"{name}: {msg}")

        module.progress = sub_progress
        try:
            res = module.evaluate(resolved)
        finally:
            module.progress = None
        if records_out is not None and res.records is not None:
            records_out[name] = res.records
        checks = [c.as_dict() for c in res.checks]
        summary = summarize(res.checks, doc_reqs)
        body = {"outputs": res.outputs, "checks": checks, "summary": summary}
        variants_out[name] = {
            "resolved_input": resolved,
            "input_id": sha256_text(canonical_json({"identity": ident, "module": [module.id, module.version],
                                                    "input": resolved})),
            **body,
            "explain": res.explain,
            "result_id": sha256_text(canonical_json(body)),
        }
        if progress:
            progress((i + 1) / len(names), f"{name}: done")
    comparison = comparison_table(module, variants_out)
    doc = {
        "schema": RESULT_SCHEMA,
        "module": {"id": module.id, "version": module.version, "title": module.title,
                   "protocols": module.protocols},
        "identity": ident,
        "request": {"schema": INPUT_SCHEMA, "module": module.id,
                    "variants": [{"name": n, "input": checked["variants"][n]} for n in names]},
        "variants": variants_out,
        "comparison": comparison,
        "hypotheses": module.hypotheses,
        "causal_note": module.causal_note,
        "epistemic": {
            "operational_use": False,
            "scope_ref": f"lab:{module.id}",
            "note": "Research output on declared synthetic or user-given inputs. Passing checks is not "
                    "a model validation and not an admission under DKP-8-SIMULATION-001 §8–§9.",
        },
    }
    doc["input_id"] = sha256_text(canonical_json({"identity": ident, "request": doc["request"]}))
    doc["result_id"] = sha256_text(canonical_json({n: variants_out[n]["result_id"] for n in names}))
    return doc


def comparison_table(module, variants_out: Dict[str, Any]) -> Dict[str, Any]:
    metrics = getattr(module, "comparison_metrics", None)
    rows = []
    keys: List[str] = []
    for name, v in variants_out.items():
        vals = metrics(v["outputs"]) if metrics else {}
        for k in vals:
            if k not in keys:
                keys.append(k)
        counts = v["summary"]["counts"]
        rows.append({"variant": name, "metrics": vals,
                     "checks": {"PASS": counts["PASS"], "FAIL": counts["FAIL"], "UNKNOWN": counts["UNKNOWN"],
                                "NOT_APPLICABLE": counts["NOT_APPLICABLE"]}})
    return {"metrics": keys, "rows": rows,
            "note": {"en": "Values side by side. No ranking: the lab names no best variant.",
                     "ru": "Значения рядом. Без рейтинга: лаборатория не называет лучший вариант."}}
