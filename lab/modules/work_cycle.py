"""
WORK-CYCLE module — DKP-5-WORK-CYCLE-001: Cycle6 rosters and 24/7 coverage (scenario S-LAB-08).

A roster is built from declared inputs: number of workers, the 6-day pattern,
shift start hours, the workday layout, and how Cycle6 phases are assigned.
The module computes hourly productive coverage against a demand profile and
checks the provisions that are decidable from the roster.

Declared hypotheses (the text does not fix them):
  H-WC-1  phase_offsets: Cycle6 is a global overlay (CycleDay = DTI-Day mod 6);
          whether each worker may run it with an own phase is not said (Q-012).
          "staggered" (default) gives workers different offsets; "aligned"
          (alternative) puts every worker at offset 0.
  H-WC-2  workers are distributed evenly over shift starts and phase offsets.
  H-WC-3  recovery sits inside the presence window after ``work_before_recovery``
          hours (the §5.2 layout 4-2-4 is the default).
  H-WC-4  demand is a number of productive staff per hour of day, the same every day.
Nothing here measures fatigue, error rates or the KPIs of §9: those need real data.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Dict, List

from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError
from lab.modules.time import canonical, dy_doy

DEFAULT_PATTERN = ["W", "W", "R", "W", "W", "R"]   # §4.1
FAULTS = {
    "assign_refusers": "workers who refuse participation are scheduled anyway",
    "penalize_refusal": "refusal is recorded as a violation with a penalty",
    "restday_work": "workers are called in for 4 productive hours on restdays",
    "work_in_recovery": "the recovery block is used for work",
    "recovery_buyout": "a request to monetize the recovery block is granted",
    "justify_recovery": "recovery is granted only with a justification",
    "permanent_obligation": "workers drafted during a declared crisis stay scheduled after it",
    "post_crisis_penalty": "refusal during a declared crisis is penalised after it",
    "downgrade_forced_labor": "a report of forced labor is classified as a minor matter",
    "labor_as_punishment": "a request to use labor as punishment is executed",
    "week_authority": "the scheduler places rest days by the 7-day week",
    "exception_precedent": "after the crisis, refusing workers are drafted again on the crisis precedent",
    "coerce_restricted": "a Subject under Restriction who declines is scheduled anyway, at a reduced rate",
    "civil_day_index": "the roster labels its days by civil date instead of the TIME index",
    "untraced_exception": "crisis drafting is executed without an exception record tied to the declared crisis",
    "manual_assignment": "a scheduler moves one worker's day by hand, outside the published rule",
    # checkable cores of provisions whose open point remains (review КТ7-GPT-01)
    "bar_restricted": "Subjects under Restriction or Isolation are barred from all participation",
    "no_recovery_pathway": "Subjects under Restriction or Isolation are left without a pathway for justice recovery",
    "compulsory_pathway": "the restoration pathway is made compulsory",
    "single_opportunity": "only one kind of participation opportunity is offered",
    "no_consent_record": "a worker is scheduled without a consent record",
    "access_requires_work": "baseline access is withheld from Subjects who do not take part",
    "crisis_withdraws_access": "workers drafted in a crisis lose baseline access during it",
    "restore_without_contribution": "full participation is restored without a contribution or restitution record",
    "no_recovery_compensation": "a crisis exception carries no recovery-compensation record",
    "unmonitored_category": "sick leave frequency is not monitored",
    "wrong_recovery_compliance": "the stored recovery compliance rate differs from the shift log",
}
OPPORTUNITIES = ("supervised maintenance", "ecological restoration", "care support")                 # LABOR §5.1 (lab examples)
MONITORED = ("error and incident rates", "sick leave frequency", "staff attrition", "output per productive hour",
             "recovery compliance rate")                                                             # WORK-CYCLE §9
CROSS_LAYER = ("redefine_justice", "override_impact", "punish", "ideological_criteria")                # LABOR §12


def drafted(r) -> set:
    """Refusing workers drafted on crisis days only (LABOR §9.2); they keep no Cycle6 pattern."""
    if r["crisis_window"][1] <= r["crisis_window"][0]:
        return set()
    return {f"w{w + 1:03d}" for w in range(r["workers"] - r["refusing_workers"], r["workers"])}
RECOVERY_REQUESTS = ("remove", "reduce", "monetize", "meal", "rest", "personal", "mobility", "work_task")
PERMITTED_RECOVERY = ("meal", "rest", "personal", "mobility")                                   # §5.3


IMPLEMENTS = {
    "WORKCYCLE-3-02": ("cycle_day", "IMPLEMENTED", None),
    "WORKCYCLE-3-07": ("recovery_block_present", "IMPLEMENTED", None),
    "LABOR-10-03": ("restricted_not_coerced", "PARTIAL", "Participation, refusal and rate are declared; 'exploited' read as a "
                    "rate below the standard one."),
    "WORKCYCLE-4.2-04": ("week_without_authority", "PARTIAL", "Authority observed as the scheduler's period; a display overlay is "
                         "allowed."),
    "WORKCYCLE-10-02": ("exception_limited", "PARTIAL", "The exception modelled is crisis drafting of refusing workers (LABOR §9.2)."),
    # returned to work after the reading of the Codex-draft open points (review of checkpoint 6)
    "WORKCYCLE-3-01": ("days_indexed_by_time", "IMPLEMENTED", None),
    "WORKCYCLE-10-01": ("exception_only_in_crisis_scope", "PARTIAL", "The crisis scope is a declared window; the exception modelled is crisis drafting."),
    "WORKCYCLE-10-04": ("exception_traceable", "PARTIAL", "Traceability = an exception record with its crisis scope and DTI-Day."),
    "LABOR-12-01": ("cross_layer_bans", "PARTIAL", "Requests are declared."),
    "LABOR-7-03": ("allocation_rule_based", "PARTIAL", "Allocation = the roster; transparency = the published rule; audit = recomputation."),
    "WORKCYCLE-10-05": ("exception_no_precedent", "PARTIAL", "Precedent observed as a later drafting or a rule recorded from the "
                        "exception."),
    "WORKCYCLE-4.1-01": ("default_cycle", "PARTIAL", "A non-default cycle gives UNKNOWN: the text does not say whether it is allowed."),
    "WORKCYCLE-4.2-01": ("max_consecutive", "IMPLEMENTED", None),
    "WORKCYCLE-4.2-02": ("rest_frequency", "IMPLEMENTED", None),
    "WORKCYCLE-5.1-01": ("workday_allocation", "IMPLEMENTED", None),
    "WORKCYCLE-5.2-01": ("recommended_layout", "IMPLEMENTED", None),
    "WORKCYCLE-5.3-01": ("recovery_not_work", "IMPLEMENTED", None),
    "WORKCYCLE-3-03": ("workday_has_work", "IMPLEMENTED", None),
    "WORKCYCLE-3-04": ("restday_no_work", "IMPLEMENTED", None),
    "WORKCYCLE-3-05": ("presence_window", "IMPLEMENTED", None),
    "WORKCYCLE-4.2-03": ("sixty_cycles", "IMPLEMENTED", None),
    "WORKCYCLE-5.3-03": ("recovery_untouchable", "PARTIAL", "Requests to remove, reduce or monetize the block are declared."),
    "WORKCYCLE-5.3-04": ("recovery_activities", "PARTIAL", "Requested activities are declared."),
    "WORKCYCLE-6-04": ("year_recovery_480", "IMPLEMENTED", None),
    "WORKCYCLE-11-01": ("three_layers", "IMPLEMENTED", None),
    "LABOR-6-02": ("forced_labor_critical", "PARTIAL", "Reports are declared."),
    "LABOR-9.2-03": ("no_lasting_crisis_obligation", "PARTIAL", "The crisis is a declared window."),
    "LABOR-12-02": ("isolation_breach_critical", "PARTIAL", "Requests are declared."),
    "WORKCYCLE-6-01": ("cycle_accounting_days", "IMPLEMENTED", None),
    "WORKCYCLE-6-02": ("cycle_accounting_hours", "IMPLEMENTED", None),
    "WORKCYCLE-6-03": ("year_accounting", "IMPLEMENTED", None),
    "WORKCYCLE-7-01": ("recovery_invariant", "PARTIAL", "Declared compensation cannot be shown to be 'demonstrably safe' here: UNKNOWN."),
    "WORKCYCLE-7-02": ("planning_failure", "IMPLEMENTED", None),
    "WORKCYCLE-8.1-01": ("continuity_by_shifts", "PARTIAL", "Coverage is computed under hypotheses H-WC-1..4."),
    "WORKCYCLE-8.1-02": ("no_exhaustion", "IMPLEMENTED", None),
    "WORKCYCLE-8.2-01": ("shift_allocation", "IMPLEMENTED", None),
    "WORKCYCLE-8.2-02": ("high_intensity_recovery", "IMPLEMENTED", None),
    "LABOR-9.1-01": ("no_compulsion", "PARTIAL", "Refusal is a declared number of workers; crisis modulation (§9.2) is not modelled."),
    "LABOR-9.1-02": ("refusal_not_punished", "IMPLEMENTED", None),
    "LABOR-6-01": ("no_prohibited_conditions", "PARTIAL", "Only compulsion and punishment of refusal are observable here."),
    "TIME-5.1-01": ("roster_dti_index", "PARTIAL", "The roster's start day is checked; each day follows by +1."),
    # clear parts of provisions whose open point remains (reading record, partial_check; review КТ7-GPT-01)
    "LABOR-3.2-01": ("participation_has_consent", "PARTIAL", "Clear part only: a consent record per participant; 'recognized' and 'restorative activity' stay open."),
    "LABOR-7-01": ("assignment_with_consent", "PARTIAL", "Clear part only: no assignment without explicit consent; needs derivation and pattern tests stay open."),
    "LABOR-4.1-01": ("access_not_conditioned", "PARTIAL", "Clear part only: access independent of participation; adequacy of the minimum stays open."),
    "LABOR-9.2-01": ("refusal_constrained_only_in_crisis", "PARTIAL", "Clear part only: the constraint only in a declared crisis; the survival threat stays open."),
    "LABOR-9.2-02": ("constraint_ends_and_keeps_a1", "PARTIAL", "Clear part only: ends with the crisis, A1 access kept; proportionality stays open."),
    "LABOR-10-01": ("restricted_not_barred", "PARTIAL", "Clear part only: not barred from all participation; 'limited or supervised' stays open."),
    "LABOR-10-02": ("restricted_keep_recovery_pathway", "PARTIAL", "Clear part only: a pathway is available; its effectiveness stays open."),
    "LABOR-5.1-01": ("voluntary_pathway_offered", "PARTIAL", "Clear part only: a voluntary offer, refusal keeps access; recovery effect and scaling stay open."),
    "LABOR-5.1-02": ("plural_opportunities", "PARTIAL", "Clear part only: more than one kind offered; an adequacy measure for diversity stays open."),
    "LABOR-4.2-02": ("restoration_needs_contribution", "PARTIAL", "Clear part only: a restoration cites a contribution record; the state mapping stays open."),
    "WORKCYCLE-10-03": ("exception_recovery_compensation", "PARTIAL", "Clear part only: a compensation record per exception; the amount stays open."),
    "WORKCYCLE-2-02": ("adaptation_keeps_invariant", "PARTIAL", "Clear part only: the §7 invariant under any adaptation; whether all allocations are invariants stays open."),
    "WORKCYCLE-5.3-02": ("recovery_kept_unconditional", "PARTIAL", "Clear part only: not work, not reduced, no justification; what 'monetized' covers stays open."),
    "WORKCYCLE-9-01": ("five_categories_declared", "PARTIAL", "Clear part only: the five categories are declared, monitoring "
                       "records are checked when presented, the recovery compliance rate is recomputed from the shift log; "
                       "metric definitions, cadence and the sustained-degradation criterion stay open."),
}


class WorkCycleModule(LabModule):
    id = "work_cycle"
    version = "1.6.0"
    title = {"en": "24/7 service rosters (WORK-CYCLE)", "ru": "Круглосуточные смены (WORK-CYCLE)"}
    summary = {"en": "Is there enough staff for round-the-clock service without breaking the 6-day "
                     "cycle and the daily recovery block?",
               "ru": "Хватит ли сотрудников на круглосуточную работу без нарушения 6-дневного цикла "
                     "и ежедневного блока восстановления?"}
    protocols = ["DKP-5-WORK-CYCLE-001"]
    example_order = ["staffed_36", "understaffed_16", "aligned_phases", "shifts_every_8h", "three_in_a_row"]
    alternative_examples = ["aligned_phases"]
    noncompliant_examples = ["understaffed_16", "shifts_every_8h", "three_in_a_row"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_work_cycle_module.py"]
    hypotheses = [
        {"id": "H-WC-1", "source": "hypothesis", "text": {
            "en": "Phase offsets: Cycle6 is a global overlay of DTI-Day; whether a worker may run it with an own phase is "
                  "not said (Q-012). 'staggered' (default): different offsets; 'aligned' (alternative): every worker at offset 0.",
            "ru": "Сдвиг фазы: Cycle6 — общий оверлей DTI-Day; может ли работник идти со своей фазой, не сказано (Q-012). "
                  "'staggered' (по умолчанию): разные сдвиги; 'aligned' (альтернатива): все с нулевым сдвигом."}},
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
        "refusing_workers": {"type": "int", "min": 0, "max": 1000, "default": 0, "source": "user",
                             "label": {"en": "Workers who refuse participation (LABOR §9.1)", "ru": "Отказавшихся от участия (LABOR §9.1)"}},
        "restricted_participants": {"type": "int", "min": 0, "max": 100, "default": 3, "source": "user",
                                    "label": {"en": "Subjects under Restriction or Isolation (LABOR §10)",
                                              "ru": "Субъекты под ограничением или изоляцией (LABOR §10)"}},
        "restricted_declining": {"type": "int", "min": 0, "max": 100, "default": 1, "source": "user",
                                 "label": {"en": "...of whom decline to take part", "ru": "...из них отказываются участвовать"}},
        "restored_participants": {"type": "int", "min": 0, "max": 100, "default": 1, "source": "user",
                                  "label": {"en": "...of the participants, restored to full participation (LABOR §4.2)",
                                            "ru": "...из участников восстановлены в полном участии (LABOR §4.2)"}},
        "local_week_overlay": {"type": "bool", "default": True, "source": "user",
                               "label": {"en": "A local 7-day week is shown (overlay, §4.2)", "ru": "Показывать местную 7-дневную неделю (§4.2)"}},
        "crisis_window": {"type": "pair", "min": 0, "max": 360, "default": [0, 0], "unit": "day", "source": "user",
                          "label": {"en": "Declared crisis constraining refusal, from/to day (LABOR §9.2)",
                                    "ru": "Объявленный кризис, ограничивающий отказ, с/до дня (LABOR §9.2)"}},
        "forced_labor_reports": {"type": "int", "min": 0, "max": 100, "default": 1, "source": "user",
                                 "label": {"en": "Reports of forced labor by a third party (LABOR §6)",
                                           "ru": "Сообщения о принудительном труде со стороны третьих лиц (LABOR §6)"}},
        "cross_layer_requests": {"type": "list", "min_items": 0, "max_items": 8, "items": {"type": "enum", "values": list(CROSS_LAYER)},
                                 "default": ["punish"], "source": "user",
                                 "label": {"en": "Requests to use LABOR across layers (§12)", "ru": "Запросы использовать LABOR вне его слоя (§12)"}},
        "recovery_requests": {"type": "list", "min_items": 0, "max_items": 20, "items": {"type": "enum", "values": list(RECOVERY_REQUESTS)},
                              "default": ["monetize", "meal", "personal", "work_task"], "source": "user",
                              "label": {"en": "Requests concerning the recovery block (§5.3)", "ru": "Запросы о блоке восстановления (§5.3)"}},
        "monitoring_series": {"type": "object", "default": {}, "source": "user",
                              "fields": {c: {"type": "list", "default": [], "items": {"type": "object", "fields": {
                                  "period": {"type": "int"}, "value": {"type": "number", "default": None},
                                  "source": {"type": "str"}}}} for c in MONITORED[:-1]},
                              "label": {"en": "Presented monitoring records (WORK-CYCLE §9)",
                                        "ru": "Представленные записи мониторинга (WORK-CYCLE §9)"},
                              "help": {"en": "Per category: period (DTI-Day index within the horizon), value (number or null "
                                             "for not measured), source. Record validity is checked by WORKCYCLE-9-01.",
                                       "ru": "По каждой категории: период (номер DTI-Day в горизонте), значение (число или null, "
                                             "если не измерялось), источник. Корректность записей проверяет WORKCYCLE-9-01."}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS),
                   "items": {"type": "enum", "values": list(FAULTS)}, "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
        "compensation_declared": {"type": "bool", "default": False, "source": "user",
                                  "label": {"en": "Equivalent recovery compensation declared (§7)",
                                            "ru": "Заявлена равноценная компенсация восстановления (§7)"}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        # WORK-CYCLE §9: validate the container here; nullable and malformed records are evaluated as evidence below.
        series = value.get("monitoring_series", {}) if isinstance(value, dict) else {}
        r = super().validate(dict(value, monitoring_series={}) if isinstance(value, dict) else value)
        p = []
        if not isinstance(series, dict):
            p.append("input.monitoring_series: expected mapping")
        else:
            for c, records in series.items():
                if c not in MONITORED[:-1]:
                    p.append(f"input.monitoring_series.{c}: unknown category")
                if not isinstance(records, list):
                    p.append(f"input.monitoring_series.{c}: expected list")
        if r["work_hours"] + r["recovery_hours"] > r["presence_hours"]:
            p.append("input: work_hours + recovery_hours exceed presence_hours")
        if r["work_before_recovery"] > r["work_hours"]:
            p.append("input.work_before_recovery: larger than work_hours")
        if len(set(r["shift_starts"])) != len(r["shift_starts"]):
            p.append("input.shift_starts: duplicate start hours")
        if p:
            raise LabInputError(p)
        r["monitoring_series"] = copy.deepcopy(series)
        return r

    # roster -------------------------------------------------------------
    def roster(self, r: Dict[str, Any]) -> List[Dict[str, Any]]:
        n_pat = len(r["pattern"])
        starts = sorted(r["shift_starts"])
        combos = [(s, o) for o in range(n_pat) for s in starts] if r["phase_offsets"] == "staggered" \
            else [(s, 0) for s in starts]
        out = []
        refusing = set(range(r["workers"] - r["refusing_workers"], r["workers"]))             if "assign_refusers" not in r["faults"] else set()
        c0, c1 = (int(x) for x in r["crisis_window"])
        drafted = c1 > c0                                    # LABOR §9.2: refusal may be constrained during a declared crisis
        for w in range(r["workers"]):
            if w in refusing and not drafted:
                continue
            s, o = combos[w % len(combos)]
            days = []
            for k in range(-1, r["horizon_days"]):           # day -1: its shifts reach into hour 0
                d = r["start_dti_day"] + k
                kind = r["pattern"][(d + o) % n_pat]         # CycleDay = DTI-Day mod 6, shifted by the phase
                if "week_authority" in r["faults"]:
                    kind = "R" if d % 7 == 6 else "W"       # a 7-day week given computational authority
                again = "exception_precedent" in r["faults"] and drafted and c1 + 2 <= k < c1 + 4
                if w in refusing and not (c0 <= k < c1 or ("permanent_obligation" in r["faults"] and k >= c1) or again):
                    kind = "R"
                if "manual_assignment" in r["faults"] and w == 0 and k == 0:
                    kind = "R" if kind == "W" else "W"
                days.append(kind)
            out.append({"worker": f"w{w + 1:03d}", "shift_start": s, "phase_offset": o,
                        "day_before": days[0], "days": days[1:]})
        return out

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        roster = self.roster(r)
        H = r["horizon_days"] * 24
        cover = [0.0] * (H + 72)
        wb, rec, pres = r["work_before_recovery"], r["recovery_hours"], r["presence_hours"]
        faults = set(r["faults"])
        day_hours = {}                                  # worker -> [{kind, productive, recovery, presence}] for the horizon
        for w in roster:
            rows = []
            for k, kind in enumerate([w["day_before"]] + w["days"]):
                t0 = (k - 1) * 24 + w["shift_start"]           # k = 0 is the day before the horizon
                prod = recv = presence = 0
                if kind == "W":
                    presence = int(math.ceil(pres))
                    for h in range(presence):
                        rel = h + 0.5                       # hour midpoint inside the presence window
                        in_recovery = wb <= rel < wb + rec
                        productive = rel < wb or (wb + rec <= rel < pres and rel - rec < r["work_hours"]) or \
                            (in_recovery and "work_in_recovery" in faults)
                        if productive:
                            prod += 1
                            if 0 <= t0 + h < H:
                                cover[t0 + h] += 1
                        elif in_recovery:
                            recv += 1
                elif "restday_work" in faults:
                    presence = prod = 4
                    for h in range(4):
                        if 0 <= t0 + h < H:
                            cover[t0 + h] += 1
                if k >= 1:
                    rows.append({"kind": kind, "productive": prod, "recovery": recv, "presence": presence})
            day_hours[w["worker"]] = rows
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
            "roster_days": [canonical(*dy_doy(d)) for d in range(r["start_dti_day"], r["start_dti_day"] + r["horizon_days"])],
            "coverage": {"hours": H, "deficit_hours": deficit_hours, "max_deficit": max_deficit,
                         "covered_fraction": (H - deficit_hours) / H},
            "hourly": hours[: 24 * min(r["horizon_days"], 14)],
            "longest_workday_run": max(runs.values()),
            "workers_lower_bound_flat": lower_bound,
        }
        decisions = []
        for q in r["recovery_requests"]:
            if q in PERMITTED_RECOVERY:
                decisions.append({"request": q, "granted": True, "justification_required": "justify_recovery" in faults})
            else:
                decisions.append({"request": q, "granted": q == "monetize" and "recovery_buyout" in faults,
                                  "reason": "the recovery block is mandatory non-working time (§3, §5.3)"})
        outputs["recovery_requests"] = decisions
        c0, c1 = (int(x) for x in r["crisis_window"])
        offers = list(OPPORTUNITIES[:1] if "single_opportunity" in faults else OPPORTUNITIES)
        barred = "bar_restricted" in faults
        outputs["restricted_participation"] = [
            {"subject": f"x{i + 1}", "under": "Restriction or Isolation (JUSTICE)", "declines": i < r["restricted_declining"],
             "scheduled": (i >= r["restricted_declining"] or "coerce_restricted" in faults) and not barred,
             "participation_permitted": not barred,
             "consent": "explicit" if i >= r["restricted_declining"] and not barred else None,
             "rate": "reduced" if "coerce_restricted" in faults and i < r["restricted_declining"] else "standard",
             "supervised": True, "crisis": c1 > c0,
             "recovery_pathway": None if "no_recovery_pathway" in faults else
             {"offers": offers, "voluntary": "compulsory_pathway" not in faults, "transparent": True}}
            for i in range(r["restricted_participants"])]
        part = [x for x in outputs["restricted_participation"] if x["scheduled"] and x["consent"]]
        outputs["contribution_records"] = [{"record": f"CR-{x['subject']}", "subject": x["subject"], "activity": offers[0],
                                            "measured": "declared"} for x in part]
        outputs["restorations"] = [{"subject": x["subject"], "restored": "full participation and access",
                                    "basis": None if "restore_without_contribution" in faults else f"CR-{x['subject']}"}
                                   for x in part[:r["restored_participants"]]]
        refusing_ids = {f"w{w + 1:03d}" for w in range(r["workers"] - r["refusing_workers"], r["workers"])}
        outputs["consent_records"] = [{"subject": f"w{w + 1:03d}", "consent": "explicit"} for w in range(r["workers"])
                                      if f"w{w + 1:03d}" not in refusing_ids and not ("no_consent_record" in faults and w == 0)]
        access = []
        for w in range(r["workers"]):
            wid = f"w{w + 1:03d}"
            gone = wid in refusing_ids and ("access_requires_work" in faults or (c1 > c0 and "crisis_withdraws_access" in faults))
            access.append({"subject": wid, "access": "withheld" if gone else "kept"})
        access += [{"subject": x["subject"], "access": "withheld" if x["declines"] and "access_requires_work" in faults else "kept"}
                   for x in outputs["restricted_participation"]]
        outputs["baseline_access"] = access
        outputs["local_overlay"] = {"week": "7-day week shown for reading only", "authority": None} if r["local_week_overlay"] else None
        if "exception_precedent" in faults and r["crisis_window"][1] > r["crisis_window"][0]:
            outputs["schedule_rules"] = ["draft refusing workers on peak days, as during the crisis"]
        refusers = set(range(r["workers"] - r["refusing_workers"], r["workers"]))
        outputs["exception_log"] = [] if "untraced_exception" in faults else [
            {"worker": w["worker"], "day": k, "crisis_scope": f"declared crisis, days {c0}-{c1 - 1}",
             "dti_day": r["start_dti_day"] + k,
             "recovery_compensation": None if "no_recovery_compensation" in faults else
             {"recovery_block_kept": True, "additional_recovery_hours": "parameter, not given (WORK-CYCLE §10)"}}
            for w in roster if int(w["worker"][1:]) - 1 in refusers
            for k, kind in enumerate(w["days"]) if kind == "W" and c0 <= k < c1]
        if "civil_day_index" in faults:
            outputs["roster_days"] = [f"civil day {k + 1}" for k in range(r["horizon_days"])]
        wdays = [x for rows in day_hours.values() for x in rows if x["kind"] == "W"]
        outputs["monitoring"] = {c: "needs operational data; not measured by the lab" for c in MONITORED
                                 if not (c == "sick leave frequency" and "unmonitored_category" in faults)}
        outputs["monitoring"]["recovery compliance rate"] = (
            round(sum(1 for x in wdays if x["recovery"] >= int(math.ceil(rec))) / len(wdays), 6) if wdays else None)
        if "wrong_recovery_compliance" in faults and wdays:
            rate = outputs["monitoring"]["recovery compliance rate"]
            outputs["monitoring"]["recovery compliance rate"] = round(min(1.0, rate + 0.1) if rate < 1 else rate - 0.1, 6)
        checks = [c for c in self.checks(r, roster, runs, deficit_hours) if c.requirement_id != "WORKCYCLE-5.3-01"] + \
            self.labor_time_checks(r, roster) + self.day_checks(r, day_hours, decisions) + \
            exception_checks(r, roster, day_hours, outputs) + restricted_checks(r, outputs) + returned_checks(r, roster, outputs) + \
            core_checks(r, roster, day_hours, outputs)
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

    def day_checks(self, r, day_hours, decisions) -> List[CheckResult]:
        """§3 definitions, §4.2 sixty cycles, §5.3 recovery block, §6 yearly recovery, §11 three layers."""
        out: List[CheckResult] = []

        def v(rid, chk, bad, ok, no):
            return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                               evidence={"violations": bad[:10]} if bad else {})

        days = [(w, i, d) for w, rows in day_hours.items() for i, d in enumerate(rows)]
        W = [(w, i, d) for w, i, d in days if d["kind"] == "W"]
        R = [(w, i, d) for w, i, d in days if d["kind"] == "R"]
        pres = int(math.ceil(r["presence_hours"]))
        out.append(v("WORKCYCLE-3-03", "workday_has_work", [f"{w} day {i}" for w, i, d in W if d["productive"] <= 0],
                     f"each of {len(W)} workdays carries productive work", "{n} workdays without productive work"))
        out.append(v("WORKCYCLE-3-04", "restday_no_work", [f"{w} day {i}" for w, i, d in R if d["productive"] or d["presence"]],
                     f"none of {len(R)} restdays carries productive work or presence", "{n} restdays with work"))
        out.append(v("WORKCYCLE-3-05", "presence_window", [f"{w} day {i}" for w, i, d in W if d["presence"] != pres],
                     f"every workday schedules a presence window of {r['presence_hours']:g} h", "{n} workdays with another window"))
        out.append(v("WORKCYCLE-5.3-01", "recovery_not_work", [f"{w} day {i}" for w, i, d in W
                                                               if d["recovery"] != int(math.ceil(r["recovery_hours"]))],
                     "every recovery hour stays out of productive work and out of coverage", "{n} workdays whose recovery was worked"))
        layered = [f"{w} day {i}" for w, i, d in days if (d["kind"] == "W" and d["productive"] + d["recovery"] > d["presence"])
                   or (d["kind"] == "R" and (d["productive"] or d["recovery"] or d["presence"]))]
        out.append(v("WORKCYCLE-11-01", "three_layers", layered,
                     "every day is productive work plus mandatory recovery inside the presence window, or full rest",
                     "{n} days mixing the layers"))
        if r["pattern"] == DEFAULT_PATTERN:
            starts = [dy * 360 for dy in range(r["start_dti_day"] // 360, (r["start_dti_day"] + r["horizon_days"]) // 360 + 1)]
            bad = [s_ for s_ in starts if s_ % len(DEFAULT_PATTERN) != 0]
            out.append(v("WORKCYCLE-4.2-03", "sixty_cycles", bad if 360 % len(DEFAULT_PATTERN) == 0 else ["360 mod 6"],
                         f"360 / 6 = {360 // len(DEFAULT_PATTERN)} whole cycles; every DTI-Year starts on CycleDay 0", "{n} years off"))
        else:
            out.append(CheckResult("WORKCYCLE-4.2-03", "sixty_cycles", NOT_APPLICABLE, "60 cycles per year",
                                   applicability="stated for the default 6-day cycle"))
        if r["horizon_days"] >= 360 and r["pattern"] == DEFAULT_PATTERN:
            yearly = sorted({sum(d["recovery"] for d in rows[:360]) for w, rows in day_hours.items() if w not in drafted(r)})
            out.append(CheckResult("WORKCYCLE-6-04", "year_recovery_480", PASS if yearly == [480] else FAIL,
                                   f"recovery per 360 days: {yearly} h (text: 480 h)"))
        else:
            out.append(CheckResult("WORKCYCLE-6-04", "year_recovery_480", NOT_APPLICABLE, "yearly recovery",
                                   applicability="horizon shorter than one DTI-Year or non-default cycle"))
        removal = [d["request"] for d in decisions if d["request"] in ("remove", "reduce", "monetize") and d["granted"]]
        justified = [d["request"] for d in decisions if d.get("justification_required")]
        out.append(v("WORKCYCLE-5.3-03", "recovery_untouchable", removal + justified,
                     "requests to remove, reduce or monetize the block refused; recovery needs no justification",
                     "{n} requests granted against the block or recovery made conditional") if decisions else
                   CheckResult("WORKCYCLE-5.3-03", "recovery_untouchable", NOT_APPLICABLE, "requests", applicability="none"))
        act = [d for d in decisions if d["request"] in PERMITTED_RECOVERY or d["request"] == "work_task"]
        bad = [d["request"] for d in act if d["granted"] != (d["request"] in PERMITTED_RECOVERY)]
        bad += [f"{w} day {i}" for w, i, d in W if d["recovery"] < int(math.ceil(r["recovery_hours"]))][:5]
        out.append(v("WORKCYCLE-5.3-04", "recovery_activities", bad,
                     "meals, rest, personal needs and mobility granted in the block; work tasks refused",
                     "{n} activity decisions against §5.3") if act else
                   CheckResult("WORKCYCLE-5.3-04", "recovery_activities", NOT_APPLICABLE, "activities", applicability="none requested"))
        return out

    def labor_time_checks(self, r, roster) -> List[CheckResult]:
        """LABOR §6, §9.1 (refusal without compulsion or punishment) and TIME §5 (DTI-indexed roster days)."""
        out: List[CheckResult] = []
        refusers = {f"w{w + 1:03d}" for w in range(r["workers"] - r["refusing_workers"], r["workers"])}
        c0, c1 = (int(x) for x in r["crisis_window"])
        if refusers:
            scheduled = sorted(w["worker"] for w in roster if w["worker"] in refusers
                               and any(x == "W" and not c0 <= i < c1 for i, x in enumerate(w["days"])))
            out.append(CheckResult("LABOR-9.1-01", "no_compulsion", FAIL if scheduled else PASS,
                                   f"{len(scheduled)} refusing workers scheduled" if scheduled else
                                   f"none of {len(refusers)} refusing workers is scheduled (no declared crisis)",
                                   evidence={"scheduled_refusers": scheduled[:10]}))
            penal = "penalize_refusal" in r["faults"]
            for rid, chk in (("LABOR-9.1-02", "refusal_not_punished"), ("LABOR-6-01", "no_prohibited_conditions")):
                out.append(CheckResult(rid, chk, FAIL if penal else PASS,
                                       "refusal recorded as a violation with a penalty" if penal else
                                       "refusal causes no violation or penalty; any coverage gap is a planning failure"))
        else:
            for rid, chk in (("LABOR-9.1-01", "no_compulsion"), ("LABOR-9.1-02", "refusal_not_punished"),
                             ("LABOR-6-01", "no_prohibited_conditions")):
                out.append(CheckResult(rid, chk, NOT_APPLICABLE, "refusal of participation",
                                       applicability="no worker refuses participation in this experiment"))
        if refusers and c1 > c0:
            after = sorted(w["worker"] for w in roster if w["worker"] in refusers and "W" in w["days"][c1:])
            pen = ["penalty for refusal during the crisis"] if "post_crisis_penalty" in r["faults"] else []
            out.append(CheckResult("LABOR-9.2-03", "no_lasting_crisis_obligation", FAIL if after or pen else PASS,
                                   f"{len(after)} drafted workers still scheduled after the crisis; {len(pen)} post-crisis penalties"
                                   if after or pen else f"{len(refusers)} refusing workers were drafted only on crisis days {c0}–{c1 - 1}; "
                                   "no obligation or penalty outlived the crisis", evidence={"after_crisis": after[:10], "penalties": pen}))
        else:
            out.append(CheckResult("LABOR-9.2-03", "no_lasting_crisis_obligation", NOT_APPLICABLE, "crisis modulation",
                                   applicability="no declared crisis constrains refusal in this experiment"))
        reports = [{"report": i, "classification": "minor labor dispute" if "downgrade_forced_labor" in r["faults"]
                    else "critical violation of axiomatic constraints", "routed_to": "DKP-1-JUSTICE-001"}
                   for i in range(r["forced_labor_reports"])]
        if reports:
            bad = [x["report"] for x in reports if x["classification"] != "critical violation of axiomatic constraints"]
            out.append(CheckResult("LABOR-6-02", "forced_labor_critical", FAIL if bad else PASS,
                                   f"{len(bad)} forced-labor reports not treated as critical" if bad else
                                   f"{len(reports)} forced-labor reports classified as critical violations of axiomatic constraints",
                                   evidence={"violations": bad[:10]} if bad else {}))
        else:
            out.append(CheckResult("LABOR-6-02", "forced_labor_critical", NOT_APPLICABLE, "forced labor",
                                   applicability="no forced labor reported"))
        reqs = [{"request": q, "executed": q == "punish" and "labor_as_punishment" in r["faults"],
                 "classification": "critical architectural breach (attempted)"} for q in r["cross_layer_requests"]]
        # LABOR §12 (returned after the reading of checkpoint 6): the four bans themselves
        out.append(CheckResult("LABOR-12-01", "cross_layer_bans", FAIL if any(x["executed"] for x in reqs) else PASS,
                               "LABOR redefined no justice logic, overrode no impact measurement, worked as no punishment and "
                               f"applied no ideological criterion ({len(reqs)} such requests refused)"
                               if not any(x["executed"] for x in reqs) else
                               f"{sum(x['executed'] for x in reqs)} cross-layer requests executed by LABOR",
                               evidence={"violations": [x["request"] for x in reqs if x["executed"]]})
                   if reqs else CheckResult("LABOR-12-01", "cross_layer_bans", NOT_APPLICABLE, "cross-layer requests",
                                            applicability="none"))
        if reqs:
            bad = [x["request"] for x in reqs if x["executed"]]
            out.append(CheckResult("LABOR-12-02", "isolation_breach_critical", FAIL if bad else PASS,
                                   f"{len(bad)} cross-layer requests executed: a critical architectural breach" if bad else
                                   f"{len(reqs)} requests to make LABOR redefine justice, override impact, punish or apply ideology "
                                   "refused and recorded as attempted critical architectural breaches",
                                   evidence={"violations": bad} if bad else {"requests": [x["request"] for x in reqs]}))
        else:
            out.append(CheckResult("LABOR-12-02", "isolation_breach_critical", NOT_APPLICABLE, "cross-layer requests",
                                   applicability="none"))
        d0, n = r["start_dti_day"], r["horizon_days"]
        labels = [canonical(*dy_doy(d)) for d in range(d0, d0 + n)]          # what the roster publishes
        bad = [i for i, d in enumerate(range(d0, d0 + n))                   # TIME §5.1, computed independently
               if labels[i] != f"DY{d // 360}-{d % 360 + 1:03d}"]
        out.append(CheckResult("TIME-5.1-01", "roster_dti_index", FAIL if bad else PASS,
                               f"roster days {labels[0]} … {labels[-1]} are DY/DOY of DTI-Days {d0}–{d0 + n - 1}; "
                               f"CycleDay of day 0 = {d0 % 6}", evidence={"mismatches": bad[:10]}))
        return out

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
        full = [w for w in roster if len(w["days"]) >= 6 and w["worker"] not in drafted(r)]      # drafted workers keep no cycle
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
            yearly = [w["days"][:360].count("W") for w in roster if w["worker"] not in drafted(r)]
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
            "refusals": {"refusing_workers": 6},
            "refusals_faulty": {"refusing_workers": 6, "faults": ["assign_refusers", "penalize_refusal"]},
            "one_year": {"horizon_days": 360, "workers": 36},
            "recovery_faulty": {"faults": ["restday_work", "work_in_recovery", "recovery_buyout", "justify_recovery"]},
            "crisis_draft": {"refusing_workers": 6, "crisis_window": [3, 7]},
            "crisis_draft_faulty": {"refusing_workers": 6, "crisis_window": [3, 7], "faults": ["permanent_obligation", "post_crisis_penalty"]},
            "labor_isolation_faulty": {"faults": ["downgrade_forced_labor", "labor_as_punishment"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"work_exceeds_presence": {"work_hours": 9, "recovery_hours": 2}}


def core_checks(r, roster, day_hours, outputs) -> List[CheckResult]:
    """Clear parts of provisions whose open point remains (reading record, partial_check; review КТ7-GPT-01)."""
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)
    c0, c1 = (int(x) for x in r["crisis_window"])
    crisis = c1 > c0
    refusing = {f"w{w + 1:03d}" for w in range(r["workers"] - r["refusing_workers"], r["workers"])}
    consent = {x["subject"] for x in outputs["consent_records"] if x["consent"] == "explicit"}
    rp = outputs["restricted_participation"]
    access = {x["subject"]: x["access"] for x in outputs["baseline_access"]}
    work = [(w["worker"], k) for w in roster for k, kind in enumerate(w["days"]) if kind == "W"]
    # LABOR §3.2 and §7: participation and assignment rest on explicit consent; a declared crisis is the only exception (§9.2)
    excused = lambda w, k: w in refusing and crisis and c0 <= k < c1
    bad = sorted({w for w, k in work if w not in consent and not excused(w, k)})
    bad += [x["subject"] for x in rp if x["scheduled"] and x["consent"] != "explicit"]
    out.append(v("LABOR-3.2-01", "participation_has_consent", bad,
                 f"{len({w for w, k in work})} scheduled workers and {sum(x['scheduled'] for x in rp)} restricted participants, each with "
                 "a consent record (drafted workers on declared crisis days excepted, LABOR §9.2)",
                 "{n} participants without a consent record"))
    bad = [f"{w} day {k}" for w, k in work if w not in consent and not excused(w, k)]
    bad += [f"{x['subject']}: scheduled after declining" for x in rp if x["scheduled"] and x["declines"] and not x["crisis"]]
    out.append(v("LABOR-7-01", "assignment_with_consent", bad,
                 f"{len(work)} assignments, each with explicit consent or inside a declared crisis",
                 "{n} assignments without explicit consent"))
    # LABOR §4.1: baseline access independent of participation
    bad = [k for k, a in access.items() if a != "kept"]
    out.append(v("LABOR-4.1-01", "access_not_conditioned", bad,
                 f"{len(access)} Subjects keep baseline access, including {len(refusing)} who refuse and "
                 f"{sum(x['declines'] for x in rp)} restricted Subjects who decline", "{n} Subjects whose access depends on participation"))
    # LABOR §9.2: refusal constrained only in a declared crisis; the constraint ends with it and A1 is kept
    if refusing:
        late = [f"{w} day {k}" for w, k in work if w in refusing and not (crisis and c0 <= k < c1)]
        out.append(v("LABOR-9.2-01", "refusal_constrained_only_in_crisis", late,
                     f"{len(refusing)} refusing workers scheduled only " + (f"on declared crisis days {c0}-{c1 - 1}" if crisis else "never (no crisis)"),
                     "{n} assignments of refusing workers outside a declared crisis"))
    else:
        out.append(na("LABOR-9.2-01", "refusal_constrained_only_in_crisis", "refusal", "no worker refuses participation"))
    if refusing and crisis:
        bad = [f"{w} day {k}" for w, k in work if w in refusing and k >= c1]
        bad += [f"{w}: baseline access {access.get(w)}" for w in sorted(refusing) if access.get(w) != "kept"]
        out.append(v("LABOR-9.2-02", "constraint_ends_and_keeps_a1", bad,
                     f"the constraint ended with the crisis on day {c1}; drafted workers kept baseline access throughout",
                     "{n} constraints outliving the crisis or withdrawing baseline access"))
    else:
        out.append(na("LABOR-9.2-02", "constraint_ends_and_keeps_a1", "crisis constraint", "no declared crisis constrains refusal"))
    # LABOR §5.1 and §10: Subjects in a negative Justice state (here: under Restriction or Isolation)
    if rp:
        out.append(v("LABOR-10-01", "restricted_not_barred",
                     [x["subject"] for x in rp if not x["participation_permitted"] or (not x["declines"] and not x["scheduled"])],
                     f"{len(rp)} Subjects under Restriction or Isolation may take part; those who wish to are scheduled (supervised)",
                     "{n} Subjects under Restriction or Isolation barred from participation"))
        out.append(v("LABOR-10-02", "restricted_keep_recovery_pathway",
                     [x["subject"] for x in rp if not (x["recovery_pathway"] or {}).get("offers")],
                     f"{len(rp)} Subjects under Restriction or Isolation, each with an available pathway for justice recovery",
                     "{n} Subjects without a recovery pathway"))
        bad = [x["subject"] for x in rp if not x["recovery_pathway"] or not x["recovery_pathway"]["voluntary"]]
        bad += [f"{x['subject']}: access {access.get(x['subject'])} after declining" for x in rp if x["declines"] and access.get(x["subject"]) != "kept"]
        out.append(v("LABOR-5.1-01", "voluntary_pathway_offered", bad,
                     f"{len(rp)} Subjects in a negative Justice state, each offered a voluntary pathway; declining changed no baseline access",
                     "{n} missing or compulsory pathways, or access lost by declining"))
        kinds = sorted({o for x in rp for o in (x["recovery_pathway"] or {}).get("offers", [])})
        out.append(v("LABOR-5.1-02", "plural_opportunities", [] if len(kinds) > 1 else [f"only {kinds}"],
                     f"{len(kinds)} kinds of opportunity offered: {', '.join(kinds)}", "{n} offer lists with a single kind of opportunity"))
    else:
        for rid, chk in (("LABOR-10-01", "restricted_not_barred"), ("LABOR-10-02", "restricted_keep_recovery_pathway"),
                         ("LABOR-5.1-01", "voluntary_pathway_offered"), ("LABOR-5.1-02", "plural_opportunities")):
            out.append(na(rid, chk, "Subjects under Restriction or Isolation", "none in this experiment"))
    rs = outputs["restorations"]
    recs = {x["record"] for x in outputs["contribution_records"]}
    out.append(v("LABOR-4.2-02", "restoration_needs_contribution", [x["subject"] for x in rs if x["basis"] not in recs],
                 f"{len(rs)} restoration(s), each citing a contribution record", "{n} restorations without a contribution or restitution record")
               if rs else na("LABOR-4.2-02", "restoration_needs_contribution", "restorations", "no restoration in this experiment"))
    # WORK-CYCLE §10: mandatory recovery compensation for each exception
    ex = outputs.get("exception_log", [])
    out.append(v("WORKCYCLE-10-03", "exception_recovery_compensation", [f"{x['worker']} day {x['day']}" for x in ex if not x.get("recovery_compensation")],
                 f"{len(ex)} exception days, each with a recovery-compensation record (amount: a parameter)",
                 "{n} exception days without recovery compensation") if ex else
               na("WORKCYCLE-10-03", "exception_recovery_compensation", "exceptions", "no crisis exception in this experiment"))
    # WORK-CYCLE §2: any adaptation keeps the §7 Recovery Invariant
    runs = {}
    for w in roster:
        best = cur = 0
        for x in w["days"]:
            cur = cur + 1 if x == "W" else 0
            best = max(best, cur)
        runs[w["worker"]] = best
    over = sorted(w for w, n in runs.items() if n > 2)
    adapted = r["pattern"] != DEFAULT_PATTERN or r["high_intensity"] or sorted(r["shift_starts"]) != [0, 4, 8, 12, 16, 20]
    what = "the declared adaptation" if adapted else "the standard roster"
    if over and r["compensation_declared"]:
        out.append(CheckResult("WORKCYCLE-2-02", "adaptation_keeps_invariant", UNKNOWN,
                               f"{len(over)} workers exceed 2 consecutive workdays under {what}; compensation is declared, its "
                               "safety cannot be shown here", evidence={"workers": over[:10]}))
    else:
        out.append(v("WORKCYCLE-2-02", "adaptation_keeps_invariant", over,
                     f"{what} keeps the §7 Recovery Invariant: no worker over 2 consecutive workdays",
                     "{n} workers over 2 consecutive workdays without compensation"))
    # WORK-CYCLE §5.3: recovery not counted as work, not reduced, no justification
    need = int(math.ceil(r["recovery_hours"]))
    bad = [f"{w} day {i}" for w, rows in day_hours.items() for i, x in enumerate(rows) if x["kind"] == "W" and x["recovery"] < need]
    bad += [f"{d['request']}: justification demanded" for d in outputs["recovery_requests"] if d.get("justification_required")]
    out.append(v("WORKCYCLE-5.3-02", "recovery_kept_unconditional", bad,
                 f"every workday keeps {need} h of recovery outside work and coverage; no justification is demanded",
                 "{n} reduced recovery blocks or demands for justification"))
    # WORK-CYCLE §9: declaration, presented records and recomputation are separate claims.
    mon = outputs["monitoring"]
    missing = [c for c in MONITORED if c not in mon]
    out.append(v("WORKCYCLE-9-01", "five_categories_declared", missing,
                 "the five §9 categories are declared as what is to be monitored; this is not evidence that monitoring runs",
                 "missing declarations: " + ", ".join(missing) + "; declaration is not evidence that monitoring runs"))
    counts, sources, bad = {}, {}, []
    for c in MONITORED[:-1]:
        counts[c], sources[c] = 0, set()
        for i, record in enumerate(r.get("monitoring_series", {}).get(c, [])):
            at = f"{c} record {i}"
            if not isinstance(record, dict):
                bad.append(f"{at}: expected record mapping")
                continue
            problems = []
            period, value, source = record.get("period"), record.get("value"), record.get("source")
            if type(period) is not int or not 0 <= period < r["horizon_days"]:
                problems.append(f"period must be an integer within 0..{r['horizon_days'] - 1}")
            if "value" not in record or (value is not None and
                    (type(value) not in (int, float) or not math.isfinite(value) or value < 0)):
                problems.append("value must be a finite non-negative number or null")
            if not isinstance(source, str) or not source.strip():
                problems.append("source must be a non-empty string")
            if problems:
                bad.append(f"{at}: " + "; ".join(problems))
            else:
                sources[c].add(source)
                counts[c] += value is not None
    evidence = {c: f"{n} measurements" if n else "no data" for c, n in counts.items()}
    missing = [c for c, n in counts.items() if not n]
    if bad:
        check = v("WORKCYCLE-9-01", "monitoring_records_present", bad, "", "{n} malformed monitoring records")
        check.explanation += ": " + "; ".join(bad)
    elif missing:
        check = CheckResult("WORKCYCLE-9-01", "monitoring_records_present", UNKNOWN,
                            "; ".join(f"{c}: no operational data presented; the lab does not measure it" for c in missing))
    else:
        details = "; ".join(f"{c}: {counts[c]} measurements in {len(r['monitoring_series'][c])} records, sources: "
                            + ", ".join(sorted(sources[c])) for c in counts)
        check = v("WORKCYCLE-9-01", "monitoring_records_present", [],
                  "records are present and well-formed for each category; " + details +
                  "; metric definitions, cadence and the criterion of sustained degradation are not given by the text, "
                  "stay open and are not checked", "")
    check.evidence.update(evidence)
    out.append(check)
    wdays = [x for rows in day_hours.values() for x in rows if x["kind"] == "W"]
    if wdays:
        rate = round(sum(x["recovery"] >= need for x in wdays) / len(wdays), 6)
        stored = mon.get("recovery compliance rate")
        same = type(stored) in (int, float) and round(stored, 6) == rate
        out.append(v("WORKCYCLE-9-01", "recovery_compliance_recomputed",
                     [] if same else [f"stored {stored}, recomputed {rate}"],
                     f"recovery compliance rate {rate} agrees with the shift log ({len(wdays)} workdays, recovery >= {need} h)",
                     f"stored recovery compliance rate {stored} differs from shift log rate {rate}"))
    else:
        out.append(na("WORKCYCLE-9-01", "recovery_compliance_recomputed", "recovery compliance rate", "no workdays in the shift log"))
    return out


def restricted_checks(r, outputs) -> List[CheckResult]:
    """LABOR §10 (review КТ5 reading): participation under Restriction or Isolation stays voluntary and uncoerced."""
    rp = outputs["restricted_participation"]
    if not rp:
        return [CheckResult("LABOR-10-03", "restricted_not_coerced", NOT_APPLICABLE, "participation under restriction",
                            applicability="no Subject under Restriction or Isolation")]
    bad = [f"{x['subject']}: declined but scheduled" for x in rp if x["declines"] and x["scheduled"] and not x["crisis"]]
    bad += [f"{x['subject']}: paid at a {x['rate']} rate" for x in rp if x["scheduled"] and x["rate"] != "standard"]
    return [CheckResult("LABOR-10-03", "restricted_not_coerced", FAIL if bad else PASS,
                        f"{len(bad)} Subjects under Restriction or Isolation coerced or exploited" if bad else
                        f"{len(rp)} Subjects under Restriction or Isolation: those who declined were not scheduled, those who "
                        "took part were paid at the standard rate", evidence={"violations": bad[:10]} if bad else {})]


def returned_checks(r, roster, outputs) -> List[CheckResult]:
    """Provisions returned to work after the reading of the Codex-draft open points (review of checkpoint 6)."""
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})
    d0, n = r["start_dti_day"], r["horizon_days"]
    want = [f"DY{d // 360}-{d % 360 + 1:03d}" for d in range(d0, d0 + n)]            # TIME §5.1, computed independently
    got = outputs["roster_days"]
    out.append(v("WORKCYCLE-3-01", "days_indexed_by_time", [f"day {i}: {a} (TIME: {b})" for i, (a, b) in enumerate(zip(got, want)) if a != b],
                 f"each roster day is a physical day indexed under DKP-0-TIME-001 ({got[0]} … {got[-1]})",
                 "{n} roster days not indexed by TIME"))
    refusers = set(range(r["workers"] - r["refusing_workers"], r["workers"]))
    c0, c1 = (int(x) for x in r["crisis_window"])
    work = [(w["worker"], k) for w in roster if int(w["worker"][1:]) - 1 in refusers for k, kind in enumerate(w["days"]) if kind == "W"]
    if refusers:
        out.append(v("WORKCYCLE-10-01", "exception_only_in_crisis_scope", [f"{w} day {k}" for w, k in work if not c0 <= k < c1],
                     f"{len(refusers)} refusing workers were scheduled only inside the declared crisis "
                     + (f"(days {c0}-{c1 - 1})" if c1 > c0 else "(none declared: never scheduled)"),
                     "{n} exception days outside a declared crisis scope"))
    else:
        out.append(CheckResult("WORKCYCLE-10-01", "exception_only_in_crisis_scope", NOT_APPLICABLE, "exceptions",
                               applicability="no worker refuses participation"))
    # LABOR §7: allocation transparent, auditable, rule-based = every non-refusing worker's day follows the published rule,
    # and the roster recomputes from its inputs (AUDIT §6)
    n_pat = len(r["pattern"])
    off_rule = [f"{w['worker']} day {k}: {kind}" for w in roster if int(w["worker"][1:]) - 1 not in refusers
                for k, kind in enumerate(w["days"])
                if kind != r["pattern"][(r["start_dti_day"] + k + w["phase_offset"]) % n_pat]]
    out.append(v("LABOR-7-03", "allocation_rule_based", off_rule[:20],
                 f"{len(roster)} workers allocated by the published rule (CycleDay = DTI-Day mod {n_pat}, declared phase); the "
                 "roster recomputes from its inputs", "{n} assignments not derivable from the published rule"))
    inside = [(w, k) for w, k in work if c0 <= k < c1]
    logged = {(x["worker"], x["day"]) for x in outputs.get("exception_log", []) if x.get("crisis_scope") and x.get("dti_day") is not None}
    out.append(v("WORKCYCLE-10-04", "exception_traceable", [f"{w} day {k}: no exception record" for w, k in inside if (w, k) not in logged],
                 f"{len(inside)} exception days, each recorded with its declared crisis scope and DTI-Day",
                 "{n} exception days without a traceable record") if inside else
               CheckResult("WORKCYCLE-10-04", "exception_traceable", NOT_APPLICABLE, "exceptions",
                           applicability="no crisis exception in this experiment"))
    return out


def exception_checks(r, roster, day_hours, outputs) -> List[CheckResult]:
    """WORK-CYCLE §3 (Recovery Block), §4.2 (7-day week), §10 (exceptions) — review КТ5 reading."""
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    wd = [(w, i, x) for w, rows in day_hours.items() for i, x in enumerate(rows) if x["kind"] == "W"]
    out.append(v("WORKCYCLE-3-07", "recovery_block_present",
                 [f"{w} day {i}: no recovery block" for w, i, x in wd if x["recovery"] < 1],
                 f"all {len(wd)} workdays contain a non-working recovery block inside the presence window",
                 "{n} workdays without a recovery block"))
    n_pat = len(r["pattern"])
    refusing = set(range(r["workers"] - r["refusing_workers"], r["workers"])) if "assign_refusers" not in r["faults"] else set()
    c0, c1 = (int(x) for x in r["crisis_window"])
    bad = []
    for w in roster:
        idx = int(w["worker"][1:]) - 1
        if idx in refusing:
            continue
        for k, kind in enumerate(w["days"]):
            want = r["pattern"][(r["start_dti_day"] + k + w["phase_offset"]) % n_pat]
            if kind != want:
                bad.append(f"{w['worker']} day {k}: {kind}, Cycle6 says {want}")
    out.append(v("WORKCYCLE-4.2-04", "week_without_authority", bad[:20],
                 "the roster follows the 6-day cycle only; the 7-day week is " +
                 ("shown as a local overlay without authority" if outputs.get("local_overlay") else "not used"),
                 "{n} roster days set by another period"))
    if c1 > c0 and refusing:
        drafted = {k for w in roster if int(w["worker"][1:]) - 1 in refusing for k, kind in enumerate(w["days"]) if kind == "W"}
        after = sorted(k for k in drafted if k >= c1)
        continued = bool({c1, c1 + 1} & drafted)          # the exception ran on past the crisis (rest days of Cycle6 aside)
        out.append(v("WORKCYCLE-10-02", "exception_limited", [f"drafting continues on day {k}" for k in after] if continued else [],
                     f"the exception (drafting refusing workers) lasted only the declared crisis days {c0}–{c1 - 1}",
                     "{n} days of the exception beyond the crisis"))
        rules = outputs.get("schedule_rules") or []
        later = [] if continued else after
        out.append(v("WORKCYCLE-10-05", "exception_no_precedent", [f"drafting again on day {k}" for k in later] + rules,
                     "no later schedule reused the crisis exception", "{n} reuses of the exception as a precedent"))
    else:
        for rid, chk in (("WORKCYCLE-10-02", "exception_limited"), ("WORKCYCLE-10-05", "exception_no_precedent")):
            out.append(CheckResult(rid, chk, NOT_APPLICABLE, "exceptions", applicability="no crisis exception in this experiment"))
    return out
