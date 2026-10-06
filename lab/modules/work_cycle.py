"""
WORK-CYCLE module — DKP-5-WORK-CYCLE-001: Cycle6 rosters and 24/7 coverage (scenario S-LAB-08).

A roster is built from declared inputs: number of workers, the 6-day pattern,
shift start hours, the workday layout, and how Cycle6 phases are assigned.
The module computes hourly productive coverage against a demand profile and
checks the provisions that are decidable from the roster.

Declared hypotheses (the text does not fix them):
  H-WC-1  phase_offsets: "staggered" lets workers run the Cycle6 pattern with
          different phase offsets; "aligned" is the literal reading (every
          worker follows CycleDay = DTI-Day mod 6 with offset 0).
  H-WC-2  workers are distributed evenly over shift starts and phase offsets.
  H-WC-3  recovery sits inside the presence window after ``work_before_recovery``
          hours (the §5.2 layout 4-2-4 is the default).
  H-WC-4  demand is a number of productive staff per hour of day, the same every day.
Nothing here measures fatigue, error rates or the KPIs of §9: those need real data.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError

DEFAULT_PATTERN = ["W", "W", "R", "W", "W", "R"]   # §4.1


IMPLEMENTS = {
    "WORKCYCLE-3-02": ("cycle_day", "IMPLEMENTED", None),
    "WORKCYCLE-4.1-01": ("default_cycle", "PARTIAL", "A non-default cycle gives UNKNOWN: the text does not say whether it is allowed."),
    "WORKCYCLE-4.2-01": ("max_consecutive", "IMPLEMENTED", None),
    "WORKCYCLE-4.2-02": ("rest_frequency", "IMPLEMENTED", None),
    "WORKCYCLE-5.1-01": ("workday_allocation", "IMPLEMENTED", None),
    "WORKCYCLE-5.2-01": ("recommended_layout", "IMPLEMENTED", None),
    "WORKCYCLE-5.3-01": ("recovery_not_work", "PARTIAL", "Holds by construction of the coverage model."),
    "WORKCYCLE-6-01": ("cycle_accounting_days", "IMPLEMENTED", None),
    "WORKCYCLE-6-02": ("cycle_accounting_hours", "IMPLEMENTED", None),
    "WORKCYCLE-6-03": ("year_accounting", "IMPLEMENTED", None),
    "WORKCYCLE-7-01": ("recovery_invariant", "PARTIAL", "Declared compensation cannot be shown to be 'demonstrably safe' here: UNKNOWN."),
    "WORKCYCLE-7-02": ("planning_failure", "IMPLEMENTED", None),
    "WORKCYCLE-8.1-01": ("continuity_by_shifts", "PARTIAL", "Coverage is computed under hypotheses H-WC-1..4."),
    "WORKCYCLE-8.1-02": ("no_exhaustion", "IMPLEMENTED", None),
    "WORKCYCLE-8.2-01": ("shift_allocation", "IMPLEMENTED", None),
    "WORKCYCLE-8.2-02": ("high_intensity_recovery", "IMPLEMENTED", None),
}


class WorkCycleModule(LabModule):
    id = "work_cycle"
    version = "1.0.0"
    title = {"en": "24/7 service rosters (WORK-CYCLE)", "ru": "Круглосуточные смены (WORK-CYCLE)"}
    summary = {"en": "Is there enough staff for round-the-clock service without breaking the 6-day "
                     "cycle and the daily recovery block?",
               "ru": "Хватит ли сотрудников на круглосуточную работу без нарушения 6-дневного цикла "
                     "и ежедневного блока восстановления?"}
    protocols = ["DKP-5-WORK-CYCLE-001"]
    example_order = ["staffed_36", "understaffed_16", "aligned_phases", "shifts_every_8h", "three_in_a_row"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_work_cycle_module.py"]
    hypotheses = [
        {"id": "H-WC-1", "source": "hypothesis", "text": {
            "en": "Phase offsets: 'staggered' lets workers run Cycle6 with different offsets; 'aligned' is the literal reading.",
            "ru": "Сдвиг фазы: 'staggered' — работники идут по Cycle6 с разными сдвигами; 'aligned' — буквальное прочтение."}},
        {"id": "H-WC-2", "source": "hypothesis", "text": {
            "en": "Workers are spread evenly over shift starts and phase offsets.",
            "ru": "Работники распределены поровну по началам смен и сдвигам фазы."}},
        {"id": "H-WC-3", "source": "hypothesis", "text": {
            "en": "Recovery sits inside the presence window after the first work block (§5.2 layout 4-2-4 by default).",
            "ru": "Восстановление внутри окна присутствия после первого рабочего блока (по умолчанию схема §5.2: 4-2-4)."}},
        {"id": "H-WC-4", "source": "hypothesis", "text": {
            "en": "Demand is productive staff per hour of day, the same every day.",
            "ru": "Спрос — число работающих по часам суток, одинаковое каждый день."}},
    ]
    inputs = {
        "start_dti_day": {"type": "int", "min": 0, "max": 10 ** 8, "default": 2461042, "source": "user",
                          "label": {"en": "First DTI-Day", "ru": "Первый DTI-Day"}},
        "horizon_days": {"type": "int", "min": 6, "max": 360, "default": 12, "unit": "day", "source": "user",
                         "label": {"en": "Horizon", "ru": "Горизонт"}},
        "workers": {"type": "int", "min": 1, "max": 1000, "default": 36, "source": "user",
                    "label": {"en": "Workers", "ru": "Сотрудников"}},
        "pattern": {"type": "list", "min_items": 1, "max_items": 14,
                    "items": {"type": "enum", "values": ["W", "R"]}, "default": DEFAULT_PATTERN,
                    "source": "text", "label": {"en": "Cycle pattern", "ru": "Шаблон цикла"}},
        "phase_offsets": {"type": "enum", "values": ["staggered", "aligned"], "default": "staggered",
                          "source": "hypothesis", "label": {"en": "Cycle phases (H-WC-1)", "ru": "Фазы цикла (H-WC-1)"}},
        "shift_starts": {"type": "list", "min_items": 1, "max_items": 24, "items": {"type": "int", "min": 0, "max": 23},
                         "default": [0, 4, 8, 12, 16, 20], "unit": "hour", "source": "user",
                         "label": {"en": "Shift start hours", "ru": "Начала смен (час)"}},
        "presence_hours": {"type": "number", "min": 1, "max": 24, "default": 10, "unit": "h", "source": "text",
                           "label": {"en": "Presence window", "ru": "Окно присутствия"}},
        "work_hours": {"type": "number", "min": 0, "max": 24, "default": 8, "unit": "h", "source": "text",
                       "label": {"en": "Productive work", "ru": "Производительная работа"}},
        "recovery_hours": {"type": "number", "min": 0, "max": 24, "default": 2, "unit": "h", "source": "text",
                           "label": {"en": "Recovery block", "ru": "Блок восстановления"}},
        "work_before_recovery": {"type": "number", "min": 0, "max": 24, "default": 4, "unit": "h",
                                 "source": "text", "label": {"en": "Work before recovery (§5.2)",
                                                             "ru": "Работа до восстановления (§5.2)"}},
        "demand": {"type": "list", "min_items": 24, "max_items": 24, "items": {"type": "number", "min": 0, "max": 10000},
                   "default": [4] * 24, "unit": "staff", "source": "user",
                   "label": {"en": "Required productive staff per hour of day", "ru": "Нужно работающих по часам суток"}},
        "high_intensity": {"type": "bool", "default": False, "source": "user",
                           "label": {"en": "High-intensity environment (§8.2)", "ru": "Высокая нагрузка (§8.2)"}},
        "compensation_declared": {"type": "bool", "default": False, "source": "user",
                                  "label": {"en": "Equivalent recovery compensation declared (§7)",
                                            "ru": "Заявлена равноценная компенсация восстановления (§7)"}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        if r["work_hours"] + r["recovery_hours"] > r["presence_hours"]:
            p.append("input: work_hours + recovery_hours exceed presence_hours")
        if r["work_before_recovery"] > r["work_hours"]:
            p.append("input.work_before_recovery: larger than work_hours")
        if len(set(r["shift_starts"])) != len(r["shift_starts"]):
            p.append("input.shift_starts: duplicate start hours")
        if p:
            raise LabInputError(p)
        return r

    # roster -------------------------------------------------------------
    def roster(self, r: Dict[str, Any]) -> List[Dict[str, Any]]:
        n_pat = len(r["pattern"])
        starts = sorted(r["shift_starts"])
        combos = [(s, o) for o in range(n_pat) for s in starts] if r["phase_offsets"] == "staggered" \
            else [(s, 0) for s in starts]
        out = []
        for w in range(r["workers"]):
            s, o = combos[w % len(combos)]
            days = []
            for k in range(-1, r["horizon_days"]):           # day -1: its shifts reach into hour 0
                d = r["start_dti_day"] + k
                days.append(r["pattern"][(d + o) % n_pat])   # CycleDay = DTI-Day mod 6, shifted by the phase
            out.append({"worker": f"w{w + 1:03d}", "shift_start": s, "phase_offset": o,
                        "day_before": days[0], "days": days[1:]})
        return out

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        roster = self.roster(r)
        H = r["horizon_days"] * 24
        cover = [0.0] * (H + 72)
        wb, rec, pres = r["work_before_recovery"], r["recovery_hours"], r["presence_hours"]
        for w in roster:
            for k, kind in enumerate([w["day_before"]] + w["days"]):
                if kind != "W":
                    continue
                t0 = (k - 1) * 24 + w["shift_start"]           # k = 0 is the day before the horizon
                for h in range(int(math.ceil(pres))):
                    rel = h + 0.5                       # hour midpoint inside the presence window
                    productive = rel < wb or (wb + rec <= rel < pres and rel - rec < r["work_hours"])
                    if productive and 0 <= t0 + h < H:
                        cover[t0 + h] += 1
        demand = r["demand"]
        hours = []
        deficit_hours = 0
        max_deficit = 0.0
        for t in range(H):
            need = demand[t % 24]
            have = cover[t]
            gap = max(0.0, need - have)
            if gap > 0:
                deficit_hours += 1
                max_deficit = max(max_deficit, gap)
            hours.append({"hour": t, "need": need, "productive_staff": have, "deficit": gap})

        def longest_run(days):
            best = cur = 0
            for x in days:
                cur = cur + 1 if x == "W" else 0
                best = max(best, cur)
            return best

        runs = {w["worker"]: longest_run(w["days"]) for w in roster}
        avg_need = sum(demand) / 24
        work_frac = r["pattern"].count("W") / len(r["pattern"])
        lower_bound = math.ceil(avg_need * 24 / max(r["work_hours"], 1e-9) / work_frac) if avg_need and work_frac else 0
        outputs = {
            "roster": [{k: v for k, v in w.items()} for w in roster],
            "coverage": {"hours": H, "deficit_hours": deficit_hours, "max_deficit": max_deficit,
                         "covered_fraction": (H - deficit_hours) / H},
            "hourly": hours[: 24 * min(r["horizon_days"], 14)],
            "longest_workday_run": max(runs.values()),
            "workers_lower_bound_flat": lower_bound,
        }
        checks = self.checks(r, roster, runs, deficit_hours)
        explain = [
            {"en": f"{r['workers']} workers, shifts at {sorted(r['shift_starts'])} h: demand is fully covered in "
                   f"{H - deficit_hours} of {H} hours; largest shortfall {max_deficit:g} staff.",
             "ru": f"{r['workers']} сотрудников, смены с {sorted(r['shift_starts'])} ч: спрос полностью покрыт в "
                   f"{H - deficit_hours} из {H} часов; наибольшая нехватка {max_deficit:g} чел."},
            {"en": f"Lower bound for a flat demand of {avg_need:g}: at least {lower_bound} workers "
                   f"(each gives {r['work_hours']:g} productive hours on {work_frac:.0%} of days).",
             "ru": f"Нижняя оценка при ровном спросе {avg_need:g}: не меньше {lower_bound} сотрудников "
                   f"(каждый даёт {r['work_hours']:g} рабочих часов в {work_frac:.0%} дней)."},
        ]
        if r["phase_offsets"] == "aligned":
            explain.append({"en": "Aligned phases: everybody rests on the same Cycle6 days, so those days have no staff.",
                            "ru": "Совпадающие фазы: все отдыхают в одни и те же дни Cycle6, в эти дни работать некому."})
        return ModuleResult(outputs=outputs, checks=checks, explain=explain)

    def checks(self, r, roster, runs, deficit_hours) -> List[CheckResult]:
        out: List[CheckResult] = []
        worst = max(runs.values())
        out.append(CheckResult("WORKCYCLE-3-02", "cycle_day", PASS,
                               "each day's role is taken from CycleDay = DTI-Day mod 6 (shifted by the declared phase)",
                               evidence={"start_dti_day": r["start_dti_day"],
                                         "cycle_day_of_start": r["start_dti_day"] % 6}))
        if r["pattern"] == DEFAULT_PATTERN:
            out.append(CheckResult("WORKCYCLE-4.1-01", "default_cycle", PASS, "the roster uses the default [W, W, R, W, W, R]"))
        else:
            out.append(CheckResult("WORKCYCLE-4.1-01", "default_cycle", UNKNOWN,
                                   "the roster uses another cycle; §4.1 names the default but does not say whether "
                                   "others are allowed (the hard limit is §7)", evidence={"pattern": r["pattern"]}))
        viol = sorted(w for w, n in runs.items() if n > 2)
        out.append(CheckResult("WORKCYCLE-4.2-01", "max_consecutive", PASS if not viol else FAIL,
                               f"longest run of consecutive workdays: {worst} (limit 2)",
                               evidence={"workers_over_limit": viol[:20]}))

        def rest_gap_ok(days):
            return all("R" in days[i:i + 3] for i in range(0, max(0, len(days) - 2)))
        bad = [w["worker"] for w in roster if not rest_gap_ok(w["days"])]
        out.append(CheckResult("WORKCYCLE-4.2-02", "rest_frequency", PASS if not bad else FAIL,
                               f"every 3 consecutive days contain a restday for {len(roster) - len(bad)} of {len(roster)} workers",
                               evidence={"workers": bad[:20]}))
        exact = (r["presence_hours"], r["work_hours"], r["recovery_hours"]) == (10, 8, 2)
        out.append(CheckResult("WORKCYCLE-5.1-01", "workday_allocation", PASS if exact else FAIL,
                               f"workday: presence {r['presence_hours']:g} h, work {r['work_hours']:g} h, "
                               f"recovery {r['recovery_hours']:g} h (text: 10 / 8 / 2)"))
        if r["work_before_recovery"] == 4 and r["recovery_hours"] == 2 and r["work_hours"] == 8:
            out.append(CheckResult("WORKCYCLE-5.2-01", "recommended_layout", PASS, "layout 4 h work, 2 h recovery, 4 h work"))
        else:
            out.append(CheckResult("WORKCYCLE-5.2-01", "recommended_layout", NOT_APPLICABLE,
                                   "the recommended 4-2-4 layout is not used", applicability=
                                   "§5.2 is a recommendation, not mandatory; this variant declares another layout"))
        out.append(CheckResult("WORKCYCLE-5.3-01", "recovery_not_work", PASS,
                               "coverage counts productive hours only; recovery hours are never counted as work"))
        full = [w for w in roster if len(w["days"]) >= 6]
        if r["pattern"] == DEFAULT_PATTERN and full:
            cyc_ok = all(w["days"][i:i + 6].count("W") == 4 for w in full for i in range(0, len(w["days"]) - 5, 6))
            out.append(CheckResult("WORKCYCLE-6-01", "cycle_accounting_days", PASS if cyc_ok else FAIL,
                                   "each complete 6-day window: 4 workdays, 2 restdays, 32 h work"))
            out.append(CheckResult("WORKCYCLE-6-02", "cycle_accounting_hours", PASS if exact else FAIL,
                                   f"per cycle: presence {4 * r['presence_hours']:g} h, recovery {4 * r['recovery_hours']:g} h "
                                   "(text: 40 h, 8 h)"))
        else:
            for rid in ("WORKCYCLE-6-01", "WORKCYCLE-6-02"):
                out.append(CheckResult(rid, "cycle_accounting", NOT_APPLICABLE, "cycle accounting is stated for the default cycle",
                                       applicability="the variant does not use the default cycle"))
        if r["horizon_days"] >= 360 and r["pattern"] == DEFAULT_PATTERN:
            yearly = [w["days"][:360].count("W") for w in roster]
            ok = all(n == 240 for n in yearly)
            out.append(CheckResult("WORKCYCLE-6-03", "year_accounting", PASS if ok and exact else FAIL,
                                   f"per 360 days: {sorted(set(yearly))} workdays (text: 240; 1,920 h work, 2,400 h presence)"))
        else:
            out.append(CheckResult("WORKCYCLE-6-03", "year_accounting", NOT_APPLICABLE, "yearly totals",
                                   applicability="horizon shorter than one DTI-Year or non-default cycle"))
        if viol:
            st = UNKNOWN if r["compensation_declared"] else FAIL
            out.append(CheckResult("WORKCYCLE-7-01", "recovery_invariant", st,
                                   f"{len(viol)} workers exceed 2 consecutive workdays; "
                                   + ("compensation is declared but its safety cannot be demonstrated here"
                                      if r["compensation_declared"] else "no compensation declared"),
                                   evidence={"workers": viol[:20]}))
        else:
            out.append(CheckResult("WORKCYCLE-7-01", "recovery_invariant", PASS, "no worker exceeds 2 consecutive workdays"))
        out.append(CheckResult("WORKCYCLE-7-02", "planning_failure", PASS,
                               "violations are reported against the roster (planning), never against a worker"))
        covered = deficit_hours == 0
        out.append(CheckResult("WORKCYCLE-8.1-01", "continuity_by_shifts", PASS if covered else FAIL,
                               "demand covered in every hour by shifts and staffing" if covered else
                               f"demand not covered in {deficit_hours} hours", evidence={"deficit_hours": deficit_hours}))
        out.append(CheckResult("WORKCYCLE-8.1-02", "no_exhaustion", PASS if not viol else FAIL,
                               "coverage does not rely on extra consecutive workdays" if not viol else
                               "coverage relies on workers exceeding the consecutive-workday limit"))
        out.append(CheckResult("WORKCYCLE-8.2-01", "shift_allocation", PASS if (r["presence_hours"] == 10 and r["work_hours"] == 8
                                                                         and r["recovery_hours"] >= 2) else FAIL,
                               f"shift: presence {r['presence_hours']:g} h, work {r['work_hours']:g} h, "
                               f"recovery {r['recovery_hours']:g} h (text: 10 h, 8 h, at least 2 h)"))
        if r["high_intensity"]:
            ok = 3 <= r["recovery_hours"] <= 4
            out.append(CheckResult("WORKCYCLE-8.2-02", "high_intensity_recovery", PASS if ok else NOT_APPLICABLE,
                                   "high intensity: recommended 3–4 h recovery per shift"
                                   + ("" if ok else " not adopted"),
                                   applicability=None if ok else
                                   "a recommendation; with presence 10 h and work 8 h only 2 h remain (§8.2 vs §5.1)"))
        else:
            out.append(CheckResult("WORKCYCLE-8.2-02", "high_intensity_recovery", NOT_APPLICABLE,
                                   "high-intensity recommendation (3–4 h recovery)",
                                   applicability="the variant does not declare a high-intensity environment"))
        return out

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        c = outputs["coverage"]
        return {"deficit_hours": c["deficit_hours"], "max_deficit": c["max_deficit"],
                "covered_fraction": c["covered_fraction"], "longest_workday_run": outputs["longest_workday_run"],
                "workers_lower_bound_flat": outputs["workers_lower_bound_flat"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "staffed_36": {},
            "understaffed_16": {"workers": 16},
            "aligned_phases": {"phase_offsets": "aligned"},
            "shifts_every_8h": {"shift_starts": [0, 8, 16]},
            "three_in_a_row": {"pattern": ["W", "W", "W", "R", "W", "R"]},
            "high_intensity": {"high_intensity": True},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"work_exceeds_presence": {"work_hours": 9, "recovery_hours": 2}}
