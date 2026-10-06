"""
API functions shared by the browser runtime (Pyodide worker) and the HTTP server.

All inputs are JSON text produced by the client; all outputs are JSON-safe.
Nothing here executes user-provided code, reads user-provided paths or fetches
URLs: the client chooses an installed module and supplies values that the
module validates strictly.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from lab import LAB_VERSION
from lab.core.export import build_package
from lab.core.registry import catalog, coverage_table, requirements
from lab.core.run import identity, run_request, validate_request
from lab.core.schema import LabInputError

_last_package: Optional[bytes] = None


def catalog_payload() -> Dict[str, Any]:
    from lab.modules import MODULES
    cat = catalog()
    return {
        "lab_version": LAB_VERSION,
        "corpus": cat["corpus"],
        "counts": cat["counts"],
        "documents": coverage_table(),
        "unresolved_dependencies": cat["unresolved_dependencies"],
        "ambiguous_references": cat["ambiguous_references"],
        "broken_section_references": cat["section_references"]["broken"],
        "modules": [m.manifest() for m in MODULES.values()],
        "prefixes": _prefixes(),
    }


def _prefixes() -> Dict[str, str]:
    """Requirement id prefix -> document id (inverse of lab/registry/prefixes.json)."""
    import os
    from lab.core.registry import REGISTRY
    with open(os.path.join(REGISTRY, "prefixes.json"), encoding="utf-8") as f:
        return {v: k for k, v in json.load(f).items()}


def requirements_payload(doc_id: str) -> Dict[str, Any]:
    return {"doc_id": doc_id, "requirements": requirements(doc_id)}


def example_request(module_id: str, example_names: Optional[list] = None) -> Dict[str, Any]:
    from lab.modules import MODULES
    m = MODULES[module_id]
    ex = m.examples()
    names = example_names or m.ordered_examples()
    return {"schema": "dkp-lab-input/1", "module": m.id,
            "variants": [{"name": n, "input": ex[n]} for n in names]}


def validate_payload(request: Dict[str, Any]) -> Dict[str, Any]:
    try:
        checked = validate_request(request)
    except LabInputError as exc:
        return {"ok": False, "problems": exc.problems}
    return {"ok": True, "problems": [], "resolved": checked["variants"]}


def run_payload(request: Dict[str, Any], progress: Optional[Callable[[float, str], None]] = None,
                provenance: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run and package.  Raises LabInputError for invalid requests (checked before any work)."""
    global _last_package
    records: Dict[str, list] = {}
    doc = run_request(request, progress=progress, records_out=records)
    _last_package = build_package(doc, records, provenance)
    return doc


def last_package() -> Optional[bytes]:
    return _last_package


# JSON-text wrappers (convenient for the Pyodide bridge)

def catalog_json() -> str:
    return json.dumps(catalog_payload(), ensure_ascii=False)


def requirements_json(doc_id: str) -> str:
    return json.dumps(requirements_payload(doc_id), ensure_ascii=False)


def example_json(module_id: str) -> str:
    return json.dumps(example_request(module_id), ensure_ascii=False)


def validate_json(request_text: str) -> str:
    try:
        req = json.loads(request_text)
    except ValueError as exc:
        return json.dumps({"ok": False, "problems": [f"request is not JSON: {exc}"]})
    return json.dumps(validate_payload(req), ensure_ascii=False)


def run_json(request_text: str, progress: Optional[Callable[[float, str], None]] = None,
             provenance_text: Optional[str] = None) -> str:
    try:
        req = json.loads(request_text)
        prov = json.loads(provenance_text) if provenance_text else None
        doc = run_payload(req, progress, prov)
    except LabInputError as exc:
        return json.dumps({"ok": False, "problems": exc.problems}, ensure_ascii=False)
    return json.dumps({"ok": True, "result": doc}, ensure_ascii=False)


def identity_json() -> str:
    return json.dumps(identity())
