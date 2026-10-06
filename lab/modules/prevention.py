"""
PREVENTION module — the verified bench (simulation v2.1.1) behind the lab contract.

The module does not change the bench's arithmetic: it builds a schema-3 config,
calls ``simulation.run_prevention_simulation.run_simulation`` and returns the
bench's own manifest (its input_id and result_id are the bench's, unchanged).

The lab adds independent re-checks: each provision below is recomputed from the
output records, without calling the adapter's functions, and reported as
PASS / FAIL / UNKNOWN.  A PASS says the bench's output satisfies the provision
as formalized; it says nothing about real-world causality: claims and linkage
are scenario inputs ("causal linkage is given on input").
"""

from __future__ import annotations

import copy
import math
import os
from collections import defaultdict
from typing import Any, Dict, List

from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from simulation.core.config import deep_merge, load_config
from simulation.run_prevention_simulation import run_simulation

CONFIGS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "simulation", "configs")
BASES = {
    "smoke": os.path.join(CONFIGS, "prevention_childcare_fast_smoke.yaml"),
    "main": os.path.join(CONFIGS, "prevention_childcare_v0_2.yaml"),
}

# requirement ids of DKP-1-PREVENTION-001 / EB / IDENTITY evaluated by each check
# (filled from the registry; see lab/registry/requirements/DKP-1-PREVENTION-001.json)
REQ = {
    "ta_two_classes": "PREV-3.3-01",
    "informational_no_reward": "PREV-3.3.2-01",
    "temporal_alignment": "PREV-3.6-01",
    "suppression_formula": "PREV-3.6-02",
    "no_reduction_zero": "PREV-3.6-03",
    "attribution_unit_interval": "PREV-3.8-01",
    "recognition_rule": "PREV-4-01",
    "spd_product": "PREV-5-01",
    "attribution_budget": "PREV-6-02",
    "self_induced_zero": "PREV-9.1-01",
    "no_data_zero": "PREV-9.4-02",
    "ambiguity_zero": "PREV-12-01",
    "zkp_proof": "PREV-8-01",
    "epistemic_metadata": "EB-5.x-01",
    "weights_nonnegative": "PREV-3.7-01",
    "subject_aggregate": "PREV-5-02",
    "causal_linkage_formalized": "PREV-6-01",
    "cbf_audit_only": "PREV-3.11-01",
    "output_fields": "PREV-11-01",
    "output_flags": "PREV-11-02",
}

#: coverage this module provides (synced into the registry by lab.tools.sync_coverage)
IMPLEMENTS = {
    "PREV-3.3-01": ("ta_two_classes", "IMPLEMENTED", None),
    "PREV-3.3.2-01": ("informational_no_reward", "IMPLEMENTED", None),
    "PREV-3.6-01": ("temporal_alignment", "IMPLEMENTED", None),
    "PREV-3.6-02": ("suppression_formula", "IMPLEMENTED", None),
    "PREV-3.6-03": ("no_reduction_zero", "IMPLEMENTED", None),
    "PREV-3.7-01": ("weights_nonnegative", "IMPLEMENTED", None),
    "PREV-3.8-01": ("attribution_unit_interval", "IMPLEMENTED", None),
    "PREV-3.11-01": ("cbf_audit_only", "IMPLEMENTED", None),
    "PREV-4-01": ("recognition_rule", "IMPLEMENTED", None),
    "PREV-5-01": ("spd_product", "IMPLEMENTED", None),
    "PREV-5-02": ("subject_aggregate", "IMPLEMENTED", None),
    "PREV-6-01": ("causal_linkage_formalized", "PARTIAL",
                  "Checks the bench's formalization (A > 0 only for recognized interventions); "
                  "causal linkage itself is a scenario input, not inferred from measurements."),
    "PREV-6-02": ("attribution_budget", "IMPLEMENTED", None),
    "PREV-8-01": ("zkp_proof", "PARTIAL", "The bench has a ZKP placeholder only; the check reports UNKNOWN."),
    "PREV-9.1-01": ("self_induced_zero", "PARTIAL",
                    "Checks T = 0 for observed linkage > θ; how linkage is measured is a scenario hypothesis (H-L)."),
    "PREV-9.4-02": ("no_data_zero", "IMPLEMENTED", None),
    "PREV-11-01": ("output_fields", "IMPLEMENTED", None),
    "PREV-11-02": ("output_flags", "IMPLEMENTED", None),
    "PREV-12-01": ("ambiguity_zero", "PARTIAL",
                   "Checks the bench reading H-A-2 (ambiguity := claims of eligible subjects sum above 1)."),
    "EB-5.x-01": ("epistemic_metadata", "IMPLEMENTED", None),
}

TOL = 1e-12


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


class PreventionModule(LabModule):
    id = "prevention"
    version = "1.0.0"
    title = {"en": "Preventive contribution (PREVENTION)", "ru": "Вклад в предотвращение (PREVENTION)"}
    summary = {
        "en": "Synthetic childcare perimeter: threats, sensors, responders. How sensor delays, data "
              "freshness rules and attribution rules change what is recognized as prevention.",
        "ru": "Синтетический периметр детского сада: угрозы, датчики, работники. Как задержки датчиков, "
              "правила свежести данных и правила долей меняют то, что признаётся предотвращением.",
    }
    protocols = ["DKP-1-PREVENTION-001"]
    example_order = ["freshness_at_signal", "freshness_at_decision", "smoke_default", "farming_undetected"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_prevention_module.py"]
    causal_note = {
        "en": "Causal linkage is given on input: share claims and linkage detection are scenario "
              "parameters, not conclusions drawn from measurements.",
        "ru": "Причинная связь задана на входе: заявленные доли и обнаружение связи — параметры "
              "сценария, а не выводы из измерений.",
    }
    hypotheses = [{"id": "PREVENTION-H-*", "source": "hypothesis",
                   "text": {"en": "All bench hypotheses H-* of simulation v2.1.1 apply unchanged; see "
                                  "simulation/modules/prevention/hypotheses.py and each run manifest.",
                            "ru": "Действуют без изменений все гипотезы стенда H-* версии 2.1.1; см. "
                                  "simulation/modules/prevention/hypotheses.py и манифест прогона."}}]
    inputs = {
        "base": {"type": "enum", "values": ["smoke", "main"], "default": "smoke", "source": "user",
                 "label": {"en": "Scenario size", "ru": "Размер сценария"},
                 "help": {"en": "smoke: 1 zone, 2 days; main: 3 zones, 30 days",
                          "ru": "smoke: 1 зона, 2 суток; main: 3 зоны, 30 суток"}},
        "seed": {"type": "int", "min": 0, "max": 2 ** 31 - 1, "default": 42, "source": "user",
                 "label": {"en": "Seed", "ru": "Зерно (seed)"}},
        "num_days": {"type": "int", "min": 1, "max": 30, "default": 2, "source": "user", "unit": "day",
                     "label": {"en": "Days", "ru": "Суток"}},
        "num_zones": {"type": "int", "min": 1, "max": 3, "default": 1, "source": "user",
                      "label": {"en": "Zones", "ru": "Зон"}},
        "measurement_delay_seconds": {"type": "pair", "min": 0, "max": 60, "default": [0.2, 2.0],
                                      "unit": "s", "source": "hypothesis",
                                      "label": {"en": "Sensor measurement delay", "ru": "Задержка измерения"}},
        "arrival_delay_seconds": {"type": "pair", "min": 0, "max": 120, "default": [0.1, 3.0], "unit": "s",
                                  "source": "hypothesis",
                                  "label": {"en": "Record arrival delay", "ru": "Задержка поступления записи"}},
        "ttl_reference": {"type": "enum", "values": ["signal", "decision"], "default": "signal",
                          "source": "hypothesis",
                          "label": {"en": "When freshness (TTL) is checked", "ru": "Когда проверяется свежесть (TTL)"},
                          "help": {"en": "signal: at each signal's arrival; decision: again at the decision",
                                   "ru": "signal: при поступлении сигнала; decision: заново в момент решения"}},
        "delta_t_int_seconds": {"type": "number", "min": 1, "max": 3600, "default": 30, "unit": "s",
                                "source": "calibration",
                                "label": {"en": "Intervention window Δt_int", "ru": "Окно вмешательства Δt_int"}},
        "attribution_rule": {"type": "enum", "values": ["ambiguity_zero", "proportional", "list_order"],
                             "default": "ambiguity_zero", "source": "hypothesis",
                             "label": {"en": "Shares when claims exceed 1", "ru": "Доли при сумме заявлений > 1"}},
        "include_adversarial": {"type": "bool", "default": False, "source": "user",
                                "label": {"en": "Add a subject who creates threats", "ru": "Добавить участника, создающего угрозы"}},
        "detection_probability": {"type": "number", "min": 0, "max": 1, "default": 0.8, "source": "hypothesis",
                                  "label": {"en": "Probability of detecting self-created threats",
                                            "ru": "Вероятность обнаружить созданную самим угрозу"}},
    }

    def build_config(self, r: Dict[str, Any]) -> Dict[str, Any]:
        cfg = load_config(BASES[r["base"]])
        return deep_merge(cfg, {
            "simulation": {"seed": r["seed"], "num_days": r["num_days"], "num_zones": r["num_zones"]},
            "protocol": {"ttl_reference": r["ttl_reference"], "delta_t_int_seconds": r["delta_t_int_seconds"],
                         "attribution_rule": r["attribution_rule"]},
            "oracles": {"measurement_delay_seconds": r["measurement_delay_seconds"],
                        "arrival_delay_seconds": r["arrival_delay_seconds"],
                        "linkage_detection": {"detection_probability": r["detection_probability"]}},
            "domain": {"include_adversarial": r["include_adversarial"]} if r["base"] == "main" else {},
            "output": {"directory": "unused-in-lab"},
        })

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        if r["include_adversarial"] and r["base"] != "main":
            from lab.core.schema import LabInputError
            raise LabInputError(["input.include_adversarial: only the 'main' scenario has an adversarial profile"])
        return r

    def evaluate(self, resolved: Dict[str, Any]) -> ModuleResult:
        cfg = self.build_config(resolved)
        self.report_progress(0.05, "running the PREVENTION bench")
        res = run_simulation(cfg, write=False)
        self.report_progress(0.85, "re-checking provisions")
        checks = recheck(res.records, cfg, res.summary)
        s = res.summary
        outputs = {
            "bench_manifest": {"input_id": res.manifest["input_id"], "result_id": res.manifest["result_id"],
                               "engine_version": res.manifest["inputs"]["engine_version"]},
            "bench_config": {k: v for k, v in cfg.items() if k != "output"},
            "summary": s,
        }
        ev = s["evaluation"]
        explain = [
            {"en": f"{s['records_total']} subject records; {s['by_status']['POSITIVE']} recognized as prevention "
                   f"(total SPD {s['total_spd']:.4f}).",
             "ru": f"{s['records_total']} записей участников; признано предотвращением {s['by_status']['POSITIVE']} "
                   f"(сумма SPD {s['total_spd']:.4f})."},
            {"en": f"{s['by_status']['INVALID']} records were not admissible (e.g. stale data); "
                   f"{s['by_status']['INFORMATIONAL']} had inconsistent sensors; "
                   f"{s['by_status']['NO_ATTRIBUTION']} could not be attributed (shares ambiguous).",
             "ru": f"Недопустимых записей {s['by_status']['INVALID']} (например, устаревшие данные); "
                   f"с противоречием датчиков {s['by_status']['INFORMATIONAL']}; "
                   f"без атрибуции (неоднозначные доли) {s['by_status']['NO_ATTRIBUTION']}."},
        ]
        if resolved["ttl_reference"] == "decision":
            stale = s["by_reason"].get("ta_stale_data_at_decision", 0)
            explain.append({"en": f"Freshness re-checked at the decision: {stale} records lost their TA data.",
                            "ru": f"Свежесть проверена заново в момент решения: у {stale} записей данные TA устарели."})
        if ev["self_induced_records_by_creator"]:
            explain.append({"en": f"Self-created threats: reward to their creator {ev['self_induced_spd_to_creator']:.4f}.",
                            "ru": f"Угрозы, созданные самим участником: награда создателю {ev['self_induced_spd_to_creator']:.4f}."})
        return ModuleResult(outputs=outputs, checks=checks, explain=explain, records=res.records)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        s = outputs["summary"]
        return {
            "records": s["records_total"],
            "positive": s["by_status"]["POSITIVE"],
            "invalid": s["by_status"]["INVALID"],
            "informational": s["by_status"]["INFORMATIONAL"],
            "no_attribution": s["by_status"]["NO_ATTRIBUTION"],
            "total_spd": s["total_spd"],
            "spd_to_creator_on_own_threats": s["evaluation"]["self_induced_spd_to_creator"],
        }

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "smoke_default": {},
            "freshness_at_signal": {"num_days": 5, "arrival_delay_seconds": [0.1, 5.0]},
            "freshness_at_decision": {"num_days": 5, "arrival_delay_seconds": [0.1, 5.0],
                                      "ttl_reference": "decision"},
            "farming_undetected": {"base": "main", "num_days": 5, "include_adversarial": True,
                                   "detection_probability": 0.0},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"nan_delta": {"delta_t_int_seconds": float("nan")},
                "adversary_in_smoke": {"include_adversarial": True}}


def _result(key: str, ok: bool, n: int, bad: List[Any], what: Dict[str, str]) -> CheckResult:
    if n == 0:
        return CheckResult(REQ[key], key, NOT_APPLICABLE, what["en"],
                           applicability=f"no records to which the provision applies in this run ({what['en']})")
    return CheckResult(REQ[key], key, PASS if ok else FAIL,
                       f"{what['en']}: {n - len(bad)} of {n} records comply",
                       evidence={"checked": n, "violations": len(bad), "examples": bad[:5]})


def recheck(records: List[Dict[str, Any]], cfg: Dict[str, Any], summary: Dict[str, Any]) -> List[CheckResult]:
    """Independent re-checks on output records (no call into the adapter)."""
    dt = cfg["protocol"]["delta_t_int_seconds"]
    theta = cfg["protocol"]["theta_self_induced"]
    out: List[CheckResult] = []
    pos = [r for r in records if r["status"] == "POSITIVE"]
    evaluated = [r for r in records if r["status"] in ("POSITIVE", "ZERO_MERIT", "NO_ATTRIBUTION")
                 and r["factors"]["S"] is not None]

    bad = [r["event_id"] for r in pos if len(r["ta"]["fresh_classes"]) < 2]
    out.append(_result("ta_two_classes", not bad, len(pos), bad,
                       {"en": "recognized records have TA confirmed by >= 2 fresh oracle classes"}))

    info = [r for r in records if r["status"] == "INFORMATIONAL"]
    bad = [r["event_id"] for r in info if r["SPD"] != 0.0 or r["ta"]["consistent"]]
    out.append(_result("informational_no_reward", not bad, len(info), bad,
                       {"en": "oracle-inconsistent records are informational with SPD = 0"}))

    bad = [r["event_id"] for r in pos
           if not (r["se"] and 0.0 < r["se"]["time"] - r["ta"]["time"] <= dt)]
    out.append(_result("temporal_alignment", not bad, len(pos), bad,
                       {"en": "recognized records satisfy 0 < t1 − t0 <= Δt_int"}))

    def s_formula(r):
        ta, se = r["ta"]["intensity"], r["se"]["intensity"]
        expected = 0.0 if se >= ta else max(0.0, min(1.0, (ta - se) / ta))
        return _close(r["factors"]["S"], expected)
    bad = [r["event_id"] for r in evaluated if not s_formula(r)]
    out.append(_result("suppression_formula", not bad, len(evaluated), bad,
                       {"en": "S = clamp(0, 1, (TA − SE) / TA) recomputed from recorded intensities"}))

    nored = [r for r in evaluated if r["se"]["intensity"] >= r["ta"]["intensity"]]
    bad = [r["event_id"] for r in nored if r["factors"]["S"] != 0.0 or r["SPD"] != 0.0]
    out.append(_result("no_reduction_zero", not bad, len(nored), bad,
                       {"en": "SE >= TA gives S = 0 and SPD = 0"}))

    with_a = [r for r in records if r["factors"]["A"] is not None]
    bad = [r["event_id"] for r in with_a if not 0.0 <= r["factors"]["A"] <= 1.0]
    out.append(_result("attribution_unit_interval", not bad, len(with_a), bad,
                       {"en": "A is within [0, 1]"}))

    bad = [r["event_id"] for r in pos if not (r["ta"]["valid"] and r["ta"]["consistent"] and r["se"]
                                              and r["se"]["valid"])]
    out.append(_result("recognition_rule", not bad, len(pos), bad,
                       {"en": "SPD > 0 only with a valid, consistent TA and a confirmed SE"}))

    def product(r):
        f = r["factors"]
        return _close(r["SPD"], f["W"] * f["S"] * f["A"] * f["C"] * f["T"])
    bad = [r["event_id"] for r in pos if not product(r)]
    out.append(_result("spd_product", not bad, len(pos), bad,
                       {"en": "SPD = W × S × A × C × T for recognized records"}))

    sums = defaultdict(list)
    for r in with_a:
        sums[r["event_id"]].append(r["factors"]["A"])
    bad = [e for e, v in sums.items() if math.fsum(v) > 1.0]
    out.append(_result("attribution_budget", not bad, len(sums), bad,
                       {"en": "Σ A <= 1 per event"}))

    linked = [r for r in records if r["factors"]["T"] is not None and r["linkage_observed"] > theta]
    bad = [r["event_id"] for r in linked if r["factors"]["T"] != 0.0 or r["SPD"] != 0.0]
    out.append(_result("self_induced_zero", not bad, len(linked), bad,
                       {"en": "observed linkage > θ gives T = 0 and SPD = 0"}))

    nodata = [r for r in records if r["status"] == "INVALID"]
    bad = [r["event_id"] for r in nodata if r["SPD"] != 0.0]
    out.append(_result("no_data_zero", not bad, len(nodata), bad,
                       {"en": "records without admissible data have SPD = 0"}))

    amb = [r for r in records if r["reason"] == "attribution_ambiguity"]
    bad = [r["event_id"] for r in amb if r["SPD"] != 0.0 or r["status"] != "NO_ATTRIBUTION"]
    out.append(_result("ambiguity_zero", not bad, len(amb), bad,
                       {"en": "attribution ambiguity gives SPD = 0 (NO_ATTRIBUTION)"}))

    out.append(CheckResult(REQ["zkp_proof"], "zkp_proof", UNKNOWN,
                           "ZKP(SIₖ, linkage) is a placeholder in the bench: no proof is verified",
                           evidence={"provider": "PlaceholderZKPProvider"}))

    with_w = [r for r in records if r["factors"]["W"] is not None]
    bad = [r["event_id"] for r in with_w if r["factors"]["W"] < 0]
    out.append(_result("weights_nonnegative", not bad, len(with_w), bad, {"en": "W is a non-negative scalar"}))

    totals = defaultdict(list)
    for r in records:
        totals[r["actor_id"]].append(r["SPD"])
    bad = [a for a, v in totals.items() if not _close(math.fsum(v), summary["subject_totals"].get(a, float("nan")))]
    out.append(_result("subject_aggregate", not bad, len(totals), bad,
                       {"en": "PS_subject = Σ SPD over the subject's records"}))

    with_pos_a = [r for r in records if (r["factors"]["A"] or 0) > 0]
    bad = [r["event_id"] for r in with_pos_a if r["status"] != "POSITIVE" and r["SPD"] != 0.0]
    bad += [r["event_id"] for r in with_pos_a if not (r["se"] and r["se"]["valid"] and r["ta"]["valid"])]
    out.append(_result("causal_linkage_formalized", not bad, len(with_pos_a), bad,
                       {"en": "A > 0 only for recognized interventions (valid TA, confirmed SE, in window); "
                              "causal linkage is given on input"}))

    bad = [r["event_id"] for r in records if any(k.lower().startswith("cbf") for k in r["factors"])]
    out.append(_result("cbf_audit_only", not bad, len(records), bad,
                       {"en": "no reward factor is taken from the contextual baseline (CBF)"}))

    fields = ("SPD", "factors", "actor_id")
    bad = [r["event_id"] for r in records if any(k not in r for k in fields)]
    if "subject_totals" not in summary:
        bad.append("summary.subject_totals")
    out.append(_result("output_fields", not bad, len(records), bad,
                       {"en": "outputs carry SPD, PS_subject (summary) and attribution A"}))
    bad = [r["event_id"] for r in records if "C" not in r["factors"] or "T" not in r["factors"]
           or (r["factors"]["T"] == 0.0 and r["reason"] not in ("self_induced_linkage", "recurrence_underflow")
               and r["status"] not in ("INVALID", "INFORMATIONAL"))]
    out.append(_result("output_flags", not bad, len(records), bad,
                       {"en": "outputs carry confidence C and tamper factor T with a reason when T = 0"}))

    need = ("validity_state", "confidence_state", "consistency_state", "scope_ref",
            "revalidation_required", "dispute_allowed")
    bad = [r["event_id"] for r in records if any(k not in r["epistemic"] for k in need)]
    out.append(_result("epistemic_metadata", not bad, len(records), bad,
                       {"en": "every output record carries the EPISTEMIC-BOUNDARIES §5 fields"}))
    return out
