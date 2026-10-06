"""
Access to the protocol catalog, the requirement registry and installed modules.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List

LAB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(LAB_ROOT, "registry")


@lru_cache(maxsize=1)
def catalog() -> Dict[str, Any]:
    with open(os.path.join(REGISTRY, "protocol_catalog.json"), encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def requirements(doc_id: str) -> List[Dict[str, Any]]:
    path = os.path.join(REGISTRY, "requirements", f"{doc_id}.json")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)["requirements"]


def requirement_ids(doc_ids: List[str]) -> List[str]:
    return [r["id"] for d in doc_ids for r in requirements(d)]


def coverage_table() -> List[Dict[str, Any]]:
    """Per document: counts of requirements by coverage status (computed, never typed in)."""
    out = []
    for d in catalog()["documents"]:
        reqs = requirements(d["id"])
        counts: Dict[str, int] = {}
        for r in reqs:
            counts[r["coverage"]] = counts.get(r["coverage"], 0) + 1
        out.append({"id": d["id"], "kind": d["kind"], "layer": d["layer"], "title": d["title"],
                    "site_url": d["site_url"], "requirements": len(reqs), "coverage": counts,
                    "registered": bool(reqs)})
    return out


def modules() -> Dict[str, Any]:
    from lab.modules import MODULES
    return MODULES
