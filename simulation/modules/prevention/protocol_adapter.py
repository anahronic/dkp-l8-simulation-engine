"""
Protocol adapter — EXACT implementation of DKP-1-PREVENTION-001 v1.0.

This module maps protocol definitions §3–§9 onto the core engine
primitives.  Every calculation cites the relevant spec section.

Protocol math:
    SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ
    PS_subject = Σ SPDₖ

Invariants:
    - TAₖ valid ⇔ ≥ 2 independent oracle classes (§3.3, §9.5)
    - Δ_oracle = max(intensity) − min(intensity)
    - Consistent regime:  Δ_oracle ≤ ε_consistency  → TAₖ_intensity = min(intensities) (§3.3.1)
    - Inconsistent regime: Δ_oracle > ε_consistency → SPDₖ = informational (§3.3.2)
    - Sₖ = clamp(0, 1, (TAₖ_intensity − SEₖ_intensity) / TAₖ_intensity) (§3.6)
    - If SEₖ_intensity ≥ TAₖ_intensity → Sₖ = 0, SPDₖ = 0 (§3.6)
    - Self-induced risk: linkage > θ → Tₖ = 0 (§9.1)
    - Pattern recurrence → Tₖ ↓ (§9.3)
    - Low coverage → Cₖ ↓; no data → SPDₖ = 0 (§9.4)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from simulation.core.oracles import OracleReading
from simulation.core.privacy import ZKPProvider, PlaceholderZKPProvider


# ── Protocol result types ───────────────────────────────────────────────

@dataclass
class ThreatActivation:
    """Validated threat activation — §3.3."""
    event_id: int
    risk_channel: str
    timestamp: float
    intensity: float          # TAₖ_intensity (min of consistent readings)
    oracle_readings: List[OracleReading]
    oracle_classes_used: set
    is_valid: bool            # ≥ 2 independent classes
    is_consistent: bool       # Δ_oracle ≤ ε_consistency
    delta_oracle: float
    informational: bool = False


@dataclass
class SuppressionResult:
    """Suppression completeness — §3.6."""
    ta_intensity: float
    se_intensity: float
    S_k: float
    temporal_valid: bool
    fully_suppressed: bool    # SE ≥ TA → Sₖ=0


@dataclass
class SPDResult:
    """Final SPDₖ for one event — §5."""
    event_id: int
    zone_id: str
    risk_channel: str
    timestamp: float
    W_k: float
    S_k: float
    A_k: float
    C_k: float
    T_k: float
    SPD_k: float
    informational: bool
    actor_id: str
    details: Dict[str, Any]


# ── Protocol adapter ───────────────────────────────────────────────────

class PreventionProtocolAdapter:
    """
    Implements the complete DKP-1-PREVENTION-001 v1.0 recognition pipeline.

    Pipeline: oracle readings → TAₖ validation → SIₖ → SEₖ → SPDₖ
    """

    def __init__(
        self,
        epsilon_consistency: float,
        delta_t_int: float,
        theta_self_induced: float,
        recurrence_decay: float,
        coverage_floor: float,
        recurrence_threshold: int,
        threat_weights: Optional[Dict[str, float]] = None,
        zkp_provider: Optional[ZKPProvider] = None,
    ) -> None:
        self.epsilon_consistency = epsilon_consistency    # §3.3, §14
        self.delta_t_int = delta_t_int                   # §3.6, §14
        self.theta_self_induced = theta_self_induced     # §9.1, §14
        self.recurrence_decay = recurrence_decay         # §9.3
        self.coverage_floor = coverage_floor             # §9.4
        self.recurrence_threshold = recurrence_threshold # §9.3 — configurable onset
        self.threat_weights = threat_weights or {}       # §3.7, §14

        # §8 — ZKP provider (placeholder at L8)
        self._zkp_provider = zkp_provider or PlaceholderZKPProvider()

        # Recurrence tracking for §9.3
        self._pattern_counts: Dict[str, int] = {}

    # ── §3.3  Threat Activation validation ──────────────────────────────

    def validate_threat_activation(
        self,
        event_id: int,
        risk_channel: str,
        timestamp: float,
        readings: List[OracleReading],
    ) -> ThreatActivation:
        """
        Validate TAₖ per §3.3 + §9.5.

        Requires ≥ 2 independent oracle classes.
        """
        classes = {r.oracle_class for r in readings}
        is_valid = len(classes) >= 2  # §3.3 + §9.5

        if not is_valid or not readings:
            return ThreatActivation(
                event_id=event_id,
                risk_channel=risk_channel,
                timestamp=timestamp,
                intensity=0.0,
                oracle_readings=readings,
                oracle_classes_used=classes,
                is_valid=False,
                is_consistent=False,
                delta_oracle=float("inf"),
                informational=False,
            )

        intensities = [r.intensity for r in readings]
        delta_oracle = max(intensities) - min(intensities)  # §3.3
        is_consistent = delta_oracle <= self.epsilon_consistency  # §3.3.1 vs §3.3.2

        if is_consistent:
            ta_intensity = min(intensities)  # §3.3.1 — conservative
        else:
            ta_intensity = min(intensities)  # still record, but mark informational

        return ThreatActivation(
            event_id=event_id,
            risk_channel=risk_channel,
            timestamp=timestamp,
            intensity=ta_intensity,
            oracle_readings=readings,
            oracle_classes_used=classes,
            is_valid=True,
            is_consistent=is_consistent,
            delta_oracle=delta_oracle,
            informational=not is_consistent,  # §3.3.2
        )

    # ── §3.6  Suppression completeness ──────────────────────────────────

    def compute_suppression(
        self,
        ta_intensity: float,
        se_intensity: float,
        ta_time: float,
        se_time: float,
    ) -> SuppressionResult:
        """
        Compute Sₖ per §3.6.

        Sₖ = clamp(0, 1, (TAₖ_intensity − SEₖ_intensity) / TAₖ_intensity)
        If SE ≥ TA → Sₖ = 0, SPDₖ = 0
        """
        dt = se_time - ta_time
        temporal_valid = 0 < dt <= self.delta_t_int  # §3.6

        if ta_intensity <= 0:
            return SuppressionResult(
                ta_intensity=ta_intensity,
                se_intensity=se_intensity,
                S_k=0.0,
                temporal_valid=temporal_valid,
                fully_suppressed=True,
            )

        # §3.6: If SE ≥ TA → Sₖ=0, SPDₖ=0
        if se_intensity >= ta_intensity:
            return SuppressionResult(
                ta_intensity=ta_intensity,
                se_intensity=se_intensity,
                S_k=0.0,
                temporal_valid=temporal_valid,
                fully_suppressed=True,
            )

        # §3.6: Sₖ = clamp(0, 1, (TA − SE) / TA)
        raw = (ta_intensity - se_intensity) / ta_intensity
        S_k = max(0.0, min(1.0, raw))

        return SuppressionResult(
            ta_intensity=ta_intensity,
            se_intensity=se_intensity,
            S_k=S_k,
            temporal_valid=temporal_valid,
            fully_suppressed=False,
        )

    # ── §3.9  Confidence from coverage ──────────────────────────────────

    def compute_confidence(self, readings: List[OracleReading]) -> float:
        """
        Derive Cₖ from oracle coverage quality — §3.9, §9.4.

        Low coverage → Cₖ ↓.  No data → SPDₖ = 0 (handled by caller).
        """
        if not readings:
            return 0.0  # §9.4: no data
        avg_confidence = sum(r.confidence for r in readings) / len(readings)
        return max(self.coverage_floor, min(1.0, avg_confidence))

    # ── §3.10 / §9.1 / §9.3  Tamper resistance ─────────────────────────

    def compute_tamper_factor(
        self,
        linkage_score: float,
        risk_channel: str,
        actor_id: str,
    ) -> float:
        """
        Derive Tₖ — §3.10, §9.1, §9.3.

        - linkage_score > θ_self_induced: Tₖ = 0  (§9.1)
        - Pattern recurrence: Tₖ decays  (§9.3)
        """
        if linkage_score > self.theta_self_induced:
            return 0.0  # §9.1: linkage > θ → Tₖ = 0

        # §9.3: pattern recurrence tracking
        pattern_key = f"{actor_id}:{risk_channel}"
        count = self._pattern_counts.get(pattern_key, 0) + 1
        self._pattern_counts[pattern_key] = count

        T_k = self.recurrence_decay ** max(0, count - self.recurrence_threshold)
        return max(0.0, min(1.0, T_k))

    # ── §5  Full SPDₖ calculation ───────────────────────────────────────

    def compute_spd(
        self,
        event_id: int,
        zone_id: str,
        ta: ThreatActivation,
        se_intensity: float,
        se_time: float,
        actor_id: str,
        attribution_share: float,
        linkage_score: float = 0.0,
    ) -> SPDResult:
        """
        Full SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ — §5.

        Enforces all invariants from §4, §6, §9.
        """
        # §4: TAₖ(valid, consistent) ∧ SIₖ ∧ SEₖ required
        if not ta.is_valid:
            return self._zero_spd(event_id, zone_id, ta, actor_id, "invalid_ta")

        if ta.informational:
            return self._informational_spd(event_id, zone_id, ta, actor_id)

        # §3.6: Suppression
        suppression = self.compute_suppression(
            ta.intensity, se_intensity, ta.timestamp, se_time,
        )

        if not suppression.temporal_valid:
            return self._zero_spd(event_id, zone_id, ta, actor_id, "temporal_invalid")

        if suppression.fully_suppressed:
            return self._zero_spd(event_id, zone_id, ta, actor_id, "fully_suppressed")

        S_k = suppression.S_k

        # §3.7: Threat severity weight
        W_k = self.threat_weights.get(ta.risk_channel, 1.0)

        # §3.8 / §6: Attribution — causal linkage
        A_k = max(0.0, min(1.0, attribution_share))

        # §3.9 / §9.4: Confidence
        C_k = self.compute_confidence(ta.oracle_readings)
        if C_k == 0.0:
            return self._zero_spd(event_id, zone_id, ta, actor_id, "no_coverage")

        # §8: ZKP linkage proof (placeholder at L8)
        self._zkp_provider.create_proof(actor_id, linkage_score)

        # §3.10 / §9.1 / §9.3: Tamper resistance (continuous linkage threshold)
        T_k = self.compute_tamper_factor(linkage_score, ta.risk_channel, actor_id)

        # §5: SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ
        SPD_k = W_k * S_k * A_k * C_k * T_k

        return SPDResult(
            event_id=event_id,
            zone_id=zone_id,
            risk_channel=ta.risk_channel,
            timestamp=ta.timestamp,
            W_k=round(W_k, 6),
            S_k=round(S_k, 6),
            A_k=round(A_k, 6),
            C_k=round(C_k, 6),
            T_k=round(T_k, 6),
            SPD_k=round(SPD_k, 6),
            informational=False,
            actor_id=actor_id,
            details={
                "ta_intensity": round(ta.intensity, 6),
                "se_intensity": round(se_intensity, 6),
                "delta_oracle": round(ta.delta_oracle, 6),
                "oracle_classes": sorted(ta.oracle_classes_used),
            },
        )

    # ── internal helpers ────────────────────────────────────────────────

    def _zero_spd(
        self, event_id: int, zone_id: str, ta: ThreatActivation,
        actor_id: str, reason: str,
    ) -> SPDResult:
        return SPDResult(
            event_id=event_id,
            zone_id=zone_id,
            risk_channel=ta.risk_channel,
            timestamp=ta.timestamp,
            W_k=0.0, S_k=0.0, A_k=0.0, C_k=0.0, T_k=0.0, SPD_k=0.0,
            informational=False,
            actor_id=actor_id,
            details={"reason": reason},
        )

    def _informational_spd(
        self, event_id: int, zone_id: str, ta: ThreatActivation,
        actor_id: str,
    ) -> SPDResult:
        """§3.3.2 — inconsistent oracle regime → informational, no reward."""
        return SPDResult(
            event_id=event_id,
            zone_id=zone_id,
            risk_channel=ta.risk_channel,
            timestamp=ta.timestamp,
            W_k=0.0, S_k=0.0, A_k=0.0, C_k=0.0, T_k=0.0, SPD_k=0.0,
            informational=True,
            actor_id=actor_id,
            details={
                "reason": "oracle_inconsistency",
                "delta_oracle": round(ta.delta_oracle, 6),
                "epsilon": self.epsilon_consistency,
            },
        )
