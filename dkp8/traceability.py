"""Traceability of the 48 provisions of DKP-8-SIMULATION-001 (lab registry ids) to code, tests and status.

Statuses (one per provision, for the provision as a whole - not only for its software part):
IMPLEMENTED_AND_TESTED, IMPLEMENTED_UNVERIFIED, PARTIAL, MISSING, BLOCKED_BY_NORMATIVE_DECISION,
BLOCKED_BY_EMPIRICAL_DATA, NOT_COMPUTABLE.  ``software`` says whether the software part is complete; ``remaining``
says what keeps the provision from operational compliance.  ``python -m dkp8 trace --md FILE`` writes the matrix;
``tests/dkp8/test_traceability.py`` checks that every registry id is mapped and every reference resolves.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
STATUSES = ("IMPLEMENTED_AND_TESTED", "IMPLEMENTED_UNVERIFIED", "PARTIAL", "MISSING", "BLOCKED_BY_NORMATIVE_DECISION",
            "BLOCKED_BY_EMPIRICAL_DATA", "NOT_COMPUTABLE")
G, BU, INV, REP, ENF, SC = ("dkp8.gate", "dkp8.bundle", "dkp8.invariants", "dkp8.reproduction", "dkp8.enforcement",
                            "dkp8.scenarios")
TG, TB, TC = "tests/dkp8/test_gate.py", "tests/dkp8/test_bundle.py", "tests/dkp8/test_crypto_and_canonical.py"
TE, TR, TL = "tests/dkp8/test_enforcement.py", "tests/dkp8/test_reproduction.py", "tests/lab/test_simulation_gate_module.py"
TCE, TEF = "tests/lab/test_calibration_expiry_module.py", "tests/lab/test_edition_finality_module.py"


def _r(status, software, impl, tests, remaining=""):
    return {"status": status, "software": software, "implementation": impl, "tests": tests, "remaining": remaining}


MATRIX: Dict[str, Dict[str, Any]] = {
    "SIMULATION-0-01": _r("PARTIAL", "complete", [G + ":evaluate", "lab.modules.simulation_gate"], [TG, TL],
                          "No activation system exists to make the gate the exclusive path; who accepts a norm after a "
                          "successful check is open (Q-001)."),
    "SIMULATION-1-01": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":evaluate"], [TG, TL],
                          "Gate decisions are binding outputs; there is no advisory mode and no override."),
    "SIMULATION-2-01": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":evaluate", G + ":OVERRIDE_KEYS"], [TG],
                          "No exception path inside L8; binding it to a real activation process is operational work."),
    "SIMULATION-3-01": _r("PARTIAL", "complete", ["simulation.run_prevention_simulation:run_simulation",
                          G + ":evaluate"], [TG, TR],
                          "Isolation: bench and Lab worker write only to their output stores; a trace reporting live "
                          "effects is blocked. Protocol logic is mirrored for PREVENTION (bench) and 35 lab modules only."),
    "SIMULATION-3-02": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":admissibility", SC + ":catalog"], [TG]),
    "SIMULATION-3-03": _r("PARTIAL", "partial", [INV + ":REGISTRY"], [TG],
                          "Axioms A1-A7 have no machine model (declared evaluations only); the SCOPE map needs author "
                          "confirmation."),
    "SIMULATION-3-04": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":envelope_breaches", INV + ":evaluate"], [TG],
                          "Detection is limited by the invariants that are not computable (see 6-01)."),
    "SIMULATION-3-05": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":evaluate"], [TG]),
    "SIMULATION-3-06": _r("BLOCKED_BY_NORMATIVE_DECISION", "complete", [BU + ":validate", BU + ":sign",
                          "dkp8.trust:verify_signature"], [TB, TC],
                          "Format, signing and verification exist; no L8 signing authority is designated (DKP8-Q-01), "
                          "so no authoritative bundle can exist."),
    "SIMULATION-4-01": _r("IMPLEMENTED_AND_TESTED", "complete", [BU + ":KINDS", G + ":evaluate"], [TB, TG]),
    "SIMULATION-4-02": _r("IMPLEMENTED_AND_TESTED", "complete", [ENF + ":enforceability", BU + ":status"], [TE, TB],
                          "Today every listed protocol/provision is NON-ENFORCEABLE or UNCALIBRATED (no bundle). Which "
                          "texts bind now is Q-035."),
    "SIMULATION-5-01": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":SCENARIO_KINDS", SC + ":catalog"], [TG],
                          "Historical PTL scenarios are accepted by the software; no PTL dataset exists yet."),
    "SIMULATION-5-02": _r("PARTIAL", "partial", [G + ":admissibility"], [TG],
                          "Unphysical or PTL-bypassing inputs are refused when declared; detecting them from the data "
                          "needs physical bounds per quantity (calibration)."),
    "SIMULATION-5-03": _r("PARTIAL", "partial", [G + ":admissibility"], [TG],
                          "Smoothing/normalisation/cherry-picking/selective sampling must be declared false; detection "
                          "from data alone is not computable in general."),
    "SIMULATION-5-04": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":admissibility", REP + ":make_package"], [TG, TR]),
    "SIMULATION-6-01": _r("PARTIAL", "partial", [INV + ":evaluate"], [TG],
                          "Authority and reversibility computable; scope partial; life-preservation metric undefined "
                          "(normative); biosphere needs B(t) model and PTL data (empirical); axioms not computable."),
    "SIMULATION-6-02": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":evaluate"], [TG]),
    "SIMULATION-7-01": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":evaluate", INV + ":check_axioms",
                          INV + ":check_scope"], [TG], "Classification is implemented; axiom detection relies on declared "
                          "evaluations (6-01)."),
    "SIMULATION-7-02": _r("IMPLEMENTED_UNVERIFIED", "complete", [G + ":instability", G + ":OPERATIONAL"], [TG],
                          "Runaway, cascade, deadlock and collapse detectors use operational definitions the corpus "
                          "does not give; author review needed."),
    "SIMULATION-7-03": _r("IMPLEMENTED_AND_TESTED", "complete", [INV + ":check_reversibility"], [TG],
                          "'Declared constraints' = a step budget declared in the dossier."),
    "SIMULATION-7-04": _r("IMPLEMENTED_UNVERIFIED", "complete", [G + ":externality"], [TG],
                          "Detects harm reported as unmeasured or displaced across declared boundaries; a model that does "
                          "not report a flow cannot be checked."),
    "SIMULATION-7-05": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":evaluate"], [TG]),
    "SIMULATION-7-06": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":evaluate"], [TG]),
    "SIMULATION-8-01": _r("BLOCKED_BY_NORMATIVE_DECISION", "complete", [G + ":evaluate", REP + ":assess"], [TG, TR],
                          "All five conditions are checked and the positive path is tested with test identities; the "
                          "number of independent nodes and the nodes themselves are not defined (DKP8-Q-02)."),
    "SIMULATION-8-02": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":evaluate"], [TG]),
    "SIMULATION-9-01": _r("BLOCKED_BY_NORMATIVE_DECISION", "complete", [BU + ":validate", BU + ":sign", BU + ":template"],
                          [TB], "No signing authority (DKP8-Q-01) and no calibration values with provenance exist."),
    "SIMULATION-CompositeIndices-01": _r("BLOCKED_BY_NORMATIVE_DECISION", "complete", [BU + ":composite_problems",
                                         "dkp8.composite:inventory"], [TB, TE],
                                         "Validation exists; no index (B(t), SPDI, PPDI/RED, credit risk, fatigue) has a "
                                         "model, inputs, weights or uncertainty method in the corpus (Q-017)."),
    "SIMULATION-CompositeIndices-02": _r("IMPLEMENTED_AND_TESTED", "complete", [BU + ":composite_problems"], [TB]),
    "SIMULATION-CompositeIndices-03": _r("BLOCKED_BY_EMPIRICAL_DATA", "complete", [BU + ":composite_problems"], [TB],
                                         "Index inputs must name raw PTL outputs; no PTL deployment emits data yet."),
    "SIMULATION-10-01": _r("IMPLEMENTED_AND_TESTED", "complete", [BU + ":status", BU + ":TRIGGERS"], [TB],
                           "A recorded trigger makes the bundle INDETERMINATE and not enforceable; whether it suspends "
                           "the bundle is Q-034 (not decided by software). Detecting drift needs data."),
    "SIMULATION-10-02": _r("IMPLEMENTED_AND_TESTED", "complete", [BU + ":status"], [TB, TCE]),
    "SIMULATION-CalibrationExpirationEpistemicHandling-01": _r("IMPLEMENTED_AND_TESTED", "complete",
                                                               [BU + ":EXPIRED", BU + ":apply_to_output"], [TB, TCE]),
    "SIMULATION-CalibrationExpirationEpistemicHandling-02": _r("IMPLEMENTED_AND_TESTED", "complete", [BU + ":status"],
                                                               [TB, TCE]),
    "SIMULATION-CalibrationExpirationEpistemicHandling-03": _r("IMPLEMENTED_AND_TESTED", "complete",
                                                               [BU + ":apply_to_output"], [TB, TCE]),
    "SIMULATION-11-01": _r("IMPLEMENTED_AND_TESTED", "complete", [REP + ":verify_package", G + ":evaluate"], [TR, TG],
                           "Bench result_id reproduced on the CI matrix (Linux/Windows/macOS) and by package verification."),
    "SIMULATION-11-02": _r("PARTIAL", "complete", [REP + ":make_package", REP + ":verify_package"], [TR],
                           "Configuration, assumptions and parameters are exposed and re-executable; there is no "
                           "operational channel that publishes summary outcomes for audit."),
    "SIMULATION-11-03": _r("IMPLEMENTED_AND_TESTED", "complete", [REP + ":make_package"], [TR]),
    "SIMULATION-12-01": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":OVERRIDE_KEYS", G + ":evaluate"], [TG, TL]),
    "SIMULATION-12-02": _r("IMPLEMENTED_AND_TESTED", "complete", [G + ":evaluate"], [TG, TL]),
    "SIMULATION-13-01": _r("BLOCKED_BY_EMPIRICAL_DATA", "complete", [ENF + ":audit_divergence"], [TE],
                           "No deployed system produces behaviour to compare."),
    "SIMULATION-13-02": _r("BLOCKED_BY_NORMATIVE_DECISION", "complete", [ENF + ":audit_divergence"], [TE],
                           "Tolerances are calibration values; none is defined (DKP8-Q-03)."),
    "SIMULATION-13-03": _r("IMPLEMENTED_AND_TESTED", "complete", [ENF + ":audit_divergence"], [TE]),
    "SIMULATION-14-01": _r("PARTIAL", "partial", ["lab.modules.edition_finality", "lab.modules.simulation_gate"],
                           [TEF, TL], "UPGRADE procedure stages are declared inputs in the lab; no operational upgrade "
                           "process exists."),
    "SIMULATION-14-02": _r("IMPLEMENTED_AND_TESTED", "complete", ["lab.modules.edition_finality"], [TEF]),
    "SIMULATION-14-03": _r("IMPLEMENTED_AND_TESTED", "complete", ["lab.modules.edition_finality"], [TEF]),
    "SIMULATION-14-04": _r("IMPLEMENTED_AND_TESTED", "complete", [ENF + ":dependents", "lab.modules.edition_finality"],
                           [TE, TEF]),
    "SIMULATION-14-05": _r("IMPLEMENTED_AND_TESTED", "complete", ["lab.modules.edition_finality"], [TEF],
                           "Scope of the date record is author question Q-062."),
    "SIMULATION-14-06": _r("PARTIAL", "partial", ["lab.modules.edition_finality"], [TEF],
                           "Checked on the pinned World commit and simulated releases, not on the published site."),
}


def registry_ids() -> List[str]:
    data = json.loads((ROOT / "lab/registry/requirements/DKP-8-SIMULATION-001.json").read_text(encoding="utf-8"))
    return [r["id"] for r in data["requirements"]]


def resolve(ref: str) -> bool:
    module, _, attr = ref.partition(":")
    mod = importlib.import_module(module)
    return not attr or hasattr(mod, attr)


def summary() -> Dict[str, int]:
    counts = {s: 0 for s in STATUSES}
    for row in MATRIX.values():
        counts[row["status"]] += 1
    return counts


def markdown() -> str:
    reqs = {r["id"]: r for r in json.loads((ROOT / "lab/registry/requirements/DKP-8-SIMULATION-001.json")
                                            .read_text(encoding="utf-8"))["requirements"]}
    counts = summary()
    lines = ["# DKP-8-SIMULATION-001 — requirements traceability", "",
             "Generated by `python -m dkp8 trace --md <file>` from `dkp8/traceability.py` and the lab registry "
             "(`lab/registry/requirements/DKP-8-SIMULATION-001.json`, exact quotes of World `aad3e86`). Status is for "
             "the provision as a whole; *software* says whether its software part is complete.", "",
             "| Status | Count |", "|---|---|"] + [f"| {s} | {n} |" for s, n in counts.items()] + ["",
             "| Provision | § | Quote (start) | Status | Software | Implementation | Tests | Remaining |",
             "|---|---|---|---|---|---|---|---|"]
    for rid in registry_ids():
        row, req = MATRIX[rid], reqs[rid]
        quote = " ".join(req["quote"].split())[:90].replace("|", "\\|")
        impl = "<br>".join(f"`{x}`" for x in row["implementation"])
        tests = "<br>".join(f"`{Path(t).name}`" for t in row["tests"])
        lines.append(f"| {rid} | {req['section']} | {quote}… | **{row['status']}** | {row['software']} | {impl} | {tests} | "
                     f"{row['remaining'].replace('|', '/')} |")
    lines += ["", "Open questions referenced: Q-001, Q-017, Q-034, Q-035, Q-062 (lab registry) and DKP8-Q-01…03 "
              "(`SIMULATION_CALIBRATION_GAPS.md`)."]
    return "\n".join(lines) + "\n"
