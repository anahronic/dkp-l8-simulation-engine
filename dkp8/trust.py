"""Who may sign L8 artifacts: the trust store (keys, roles, revocations, reproduction nodes).

DKP-8-SIMULATION-001 §3/§9 require a *signed* Calibration Bundle produced by L8, and §8 requires reproduction by
*independent nodes*.  The corpus names neither the signing authority nor the nodes (open author question), so the
canonical trust store ships with **no authority and no node**.  Consequently no bundle can be authoritative and no
reproduction can count as independent: every gate that needs them is NOT_ESTABLISHED, never PASS.

For development and tests there is one public development key derived from a published phrase.  Its private seed
is not a secret — anyone can sign with it — so a signature by it proves only integrity, never authority, and the
verifier reports VALID_DEVELOPMENT_ONLY.  It is never accepted where an authority is required.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from dkp8 import ed25519
from dkp8.canonical import canonical

TRUST_SCHEMA = "dkp-l8-trust/1"
DEV_PHRASE = b"DKP-8 development signing key - public, NOT an L8 authority - 2026-11-17"
DEV_SEED = hashlib.sha256(DEV_PHRASE).digest()
STORE_PATH = Path(__file__).with_name("trust-store.json")

# Signature verdicts
VALID_AUTHORITY = "VALID_AUTHORITY"
VALID_DEVELOPMENT_ONLY = "VALID_DEVELOPMENT_ONLY"
VALID_TEST_ONLY = "VALID_TEST_ONLY"
UNKNOWN_KEY = "UNKNOWN_KEY"
REVOKED_KEY = "REVOKED_KEY"
INVALID_SIGNATURE = "INVALID_SIGNATURE"
UNSIGNED = "UNSIGNED"


def key_id(public: bytes) -> str:
    return "ed25519:" + hashlib.sha256(public).hexdigest()[:16]


def dev_key() -> Dict[str, Any]:
    public = ed25519.public_key(DEV_SEED)
    return {"key_id": key_id(public), "public_key": public.hex(), "role": "development",
            "label": "DEVELOPMENT ONLY - public seed, not an L8 authority"}


def canonical_store() -> Dict[str, Any]:
    """The trust store as the corpus supports it today: no authority, no independent node."""
    return {
        "schema": TRUST_SCHEMA,
        "authorities": [],
        "authority_note": "No L8 signing authority is designated in the corpus (DKP-8-SIMULATION-001 §3, §9 say "
                          "'signed' but not by whom). Adding one is an author/governance decision.",
        "development_keys": [dev_key()],
        "test_keys": [],
        "nodes": [],
        "nodes_note": "No independent simulation node is designated (DKP-8-SIMULATION-001 §8). Adding nodes is an "
                      "author/governance decision.",
        "revoked_keys": [],
        "revoked_bundles": [],
    }


def load(path: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(path or STORE_PATH)
    store = json.loads(path.read_text(encoding="utf-8"))
    if store.get("schema") != TRUST_SCHEMA:
        raise ValueError("Unknown trust store schema")
    return store


def with_test_identities(store: Dict[str, Any], authority_seed: bytes, node_seeds=()) -> Dict[str, Any]:
    """A copy of ``store`` with test-only identities (used by tests and the labelled demonstration).

    Test identities are reported as VALID_TEST_ONLY and as test nodes: outcomes that rely on them are marked
    ``test_identity: true`` and can never become authoritative.
    """
    out = copy.deepcopy(store)
    out["allow_test_identities"] = True
    pub = ed25519.public_key(authority_seed)
    out["test_keys"].append({"key_id": key_id(pub), "public_key": pub.hex(), "role": "test-authority",
                             "label": "TEST ONLY"})
    for seed in node_seeds:
        npub = ed25519.public_key(seed)
        out["nodes"].append({"node_id": key_id(npub), "public_key": npub.hex(), "operator": "test-operator-" +
                             key_id(npub)[-4:], "test_only": True})
    return out


def _find(store, kid):
    for group, verdict in (("authorities", VALID_AUTHORITY), ("development_keys", VALID_DEVELOPMENT_ONLY),
                           ("test_keys", VALID_TEST_ONLY)):
        for entry in store.get(group, []):
            if entry["key_id"] == kid:
                return entry, verdict
    for entry in store.get("nodes", []):
        if entry["node_id"] == kid:
            return {"key_id": kid, "public_key": entry["public_key"]}, VALID_TEST_ONLY if entry.get("test_only") else VALID_AUTHORITY
    return None, UNKNOWN_KEY


def sign_document(body: Dict[str, Any], secret: bytes) -> Dict[str, str]:
    public = ed25519.public_key(secret)
    return {"key_id": key_id(public), "alg": "ed25519", "sig": ed25519.sign(secret, canonical(body)).hex()}


def verify_signature(body: Dict[str, Any], signature: Optional[Dict[str, Any]], store: Dict[str, Any]) -> str:
    """Verdict for one signature over the canonical bytes of ``body``."""
    if not signature:
        return UNSIGNED
    kid = signature.get("key_id")
    if kid in store.get("revoked_keys", []):
        return REVOKED_KEY
    entry, verdict = _find(store, kid)
    if entry is None:
        return UNKNOWN_KEY
    try:
        ok = signature.get("alg") == "ed25519" and ed25519.verify(bytes.fromhex(entry["public_key"]), canonical(body),
                                                                  bytes.fromhex(signature.get("sig", "")))
    except ValueError:
        ok = False
    return verdict if ok else INVALID_SIGNATURE
