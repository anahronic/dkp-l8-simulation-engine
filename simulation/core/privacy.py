"""
Privacy / ZKP interface — §8 placeholder for DKP-1-PREVENTION-001 v1.0.

This is an L8 simulation placeholder, NOT a production cryptographic
implementation.  It exists so the repository structurally acknowledges
the protocol's ZKP(SIₖ, linkage) provability requirement.

Production L9+ implementations MUST replace PlaceholderZKPProvider
with a real zero-knowledge proof backend (e.g., zk-SNARKs, Bulletproofs).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ── ZKP data types ──────────────────────────────────────────────────────

@dataclass
class ZKPProof:
    """
    Zero-knowledge proof object — §8.

    In production, this carries a cryptographic proof that the subject
    linkage claim is valid without revealing raw behavioral data.
    """
    subject_id: str
    claim_hash: str          # hash of the claim being proved
    proof_data: bytes        # serialised proof (empty in L8 placeholder)
    verified: bool           # whether the proof has been verified
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── ZKP provider interface ──────────────────────────────────────────────

class ZKPProvider(ABC):
    """
    Abstract interface for zero-knowledge proof operations — §8.

    Any conforming DKP prevention implementation must wire a ZKPProvider
    into the recognition pipeline at the point where SI/linkage proof
    would be validated.
    """

    @abstractmethod
    def create_proof(
        self,
        subject_id: str,
        linkage_score: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> ZKPProof:
        """Create a ZKP proving the linkage claim without revealing data."""
        ...

    @abstractmethod
    def verify_proof(self, proof: ZKPProof) -> bool:
        """Verify a previously created proof."""
        ...


# ── L8 simulation placeholder ──────────────────────────────────────────

class PlaceholderZKPProvider(ZKPProvider):
    """
    L8 simulation stub — satisfies the interface contract without
    performing real cryptography.

    - create_proof: returns a stub ZKPProof (no raw data exposed)
    - verify_proof: raises NotImplementedError (not available at L8)
    """

    def create_proof(
        self,
        subject_id: str,
        linkage_score: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> ZKPProof:
        return ZKPProof(
            subject_id=subject_id,
            claim_hash=f"placeholder:{subject_id}:{linkage_score:.4f}",
            proof_data=b"",
            verified=False,
            metadata={"provider": "PlaceholderZKPProvider", "l8_stub": True},
        )

    def verify_proof(self, proof: ZKPProof) -> bool:
        raise NotImplementedError(
            "ZKP verification is not available in L8 simulation scope. "
            "Replace PlaceholderZKPProvider with a production ZKP backend."
        )
