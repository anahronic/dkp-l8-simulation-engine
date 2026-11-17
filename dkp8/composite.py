"""Composite indices named in the corpus and what DKP-8-SIMULATION-001 §9 still needs for each.

§9: any composite index (including B(t)) MUST have its model fully specified in L8, MUST declare all inputs and
weights, MUST include uncertainty propagation, SHALL NOT be modified outside L8; PTL emits only raw, model-declared
outputs.  None of the indices below has a model in the corpus, so none is computed here (no formula, weight or bound
is invented).  Each entry lists what the corpus *does* say, with its source, and the exact questions whose answers a
Calibration Bundle needs.  :func:`dkp8.bundle.composite_problems` checks a proposed specification.
"""
from __future__ import annotations

from typing import Any, Dict, List

INDICES: List[Dict[str, Any]] = [
    {"index": "B(t) - Biosphere Health / Integrity Index",
     "sources": ["CODE-OF-PLANETARY-SYNERGY A.1 (dW/dt >= k*E(t)*T(t)*B(t)^2.83; B(t) in 0...1, measured by PTL; "
                 "B_min = 0.68 hard threshold: if B(t) < B_min all Kill Switches activate)",
                 "DKP-0-ORACLE-001 §12 (composite physical index from PTL-admissible measurements; model, "
                 "aggregation, weighting and calibration not defined in PTL, MUST be specified in SIMULATION; "
                 "informational only until a valid bundle exists)",
                 "DKP-1-AXIOMS-001 A2 (sustained degradation of biospheric integrity incl. B(t) is a violation)"],
     "given": {"range": "[0, 1]", "B_min": "0.68 (Code A.1)", "exponent_in_main_equation": "2.83 (Code A.1)"},
     "status": "BLOCKED_BY_NORMATIVE_DECISION",
     "questions": ["Which PTL measurements are the inputs of B(t), in which units and at which spatial/temporal "
                   "resolution?", "What is the aggregation model (functional form) and what are the weights?",
                   "How is measurement uncertainty propagated to B(t), and which confidence level applies to the "
                   "comparison with B_min = 0.68?", "Does B_min = 0.68 in the Code bind before an L8 bundle exists "
                   "(author question Q-055), and what do the Kill Switches disconnect (Q-048)?",
                   "May Level-2 human validators contribute to B(t) (Q-047)?"],
     "open_questions": ["Q-017", "Q-047", "Q-048", "Q-055"]},
    {"index": "SPDI - Spatial Physical Dignity Index",
     "sources": ["DKP-5-HABITAT-001 §3-§5 (normalized in [0,1], exclusively from PTL-verified physical measurements; "
                 "activation needs SPDI >= SPDI_min and no component below its critical survivability threshold; "
                 "model, SPDI_min and component thresholds calibrated exclusively under SIMULATION)",
                 "DKP-5-HABITAT-001 §6 (NON-ENFORCEABLE without a valid bundle covering SPDI)"],
     "given": {"range": "[0, 1]", "components": "living space, quiet, light, air ... (non-exhaustive list, §4)"},
     "status": "BLOCKED_BY_NORMATIVE_DECISION",
     "questions": ["Complete list of SPDI components and their PTL measurements?", "Aggregation model and weights?",
                   "Value of SPDI_min and each component's critical survivability threshold (with confidence "
                   "bounds)?", "Uncertainty propagation method?"],
     "open_questions": ["Q-017"]},
    {"index": "PPDI - Passenger Physical Dignity Index (and RED)",
     "sources": ["DKP-5-TRANSPORT-001 §4 (PPDI quantifies physical conditions during transport; minimum components "
                 "§4.1; modes below the minimum PPDI threshold are classified ...; system quality metric)"],
     "given": {"components": "§4.1 minimum list"},
     "status": "BLOCKED_BY_NORMATIVE_DECISION",
     "questions": ["Aggregation model, weights and the minimum PPDI threshold?", "Is 'forced bodily contact between "
                   "non-consenting passengers' PTL-measurable (Q-037)?", "Definition and model of RED?",
                   "Where is DKP-2-ECONOMIC-001 referenced by TRANSPORT (missing document, Q-014)?"],
     "open_questions": ["Q-017", "Q-037", "Q-014"]},
    {"index": "Credit risk (FINANCE)", "sources": ["DKP-2-FINANCE-001, as recorded in lab/MODEL_GAPS.md §7 (no formula, weights or bounds given)"],
     "given": {}, "status": "BLOCKED_BY_NORMATIVE_DECISION",
     "questions": ["Inputs, model, weights and thresholds of the credit-risk assessment?"], "open_questions": ["Q-017"]},
    {"index": "Fatigue (WORK-CYCLE)", "sources": ["DKP-5-WORK-CYCLE-001 §9, as recorded in lab/MODEL_GAPS.md §7 (no formula, weights or bounds given)"],
     "given": {}, "status": "BLOCKED_BY_NORMATIVE_DECISION",
     "questions": ["Fatigue model, measured inputs, weights and the limits it is compared with?"],
     "open_questions": ["Q-017"]},
]


def inventory() -> List[Dict[str, Any]]:
    return [dict(x) for x in INDICES]
