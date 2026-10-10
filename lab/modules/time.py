"""
TIME module — DKP-0-TIME-001 date index (DTI-Day = JDN, DY/DOY, canonical string).

Independent implementation of §3, §5 and §6 (Fliegel–Van Flandern for
Gregorian ↔ JDN), compared with
  - the normative vectors of §9 (one check per row), and
  - the canonical reference implementation of §10, executed from the pinned,
    hash-verified corpus text (never from user input).

The §9 row for 2000-01-01 (DY6815-026) contradicts §5 and the §10 code
(DTI-Day 2451545 → DY6809-306).  The lab reports that row as FAIL with the tag
``corpus_inconsistency`` (erratum pending) and does not present either value
as the agreed normative vector.

Besides the conversion, the module keeps a small record store (§7, §8): records
arrive with a DTI-Day, a (DY, DOY) pair or only a Gregorian date; the store keeps
DTI-Day as the authority, derives DY/DOY from it, shows the Gregorian date for
reading only and makes audits and disputes reference DTI-Day.  A year table
checks §3 and §4.2 (360 days, no leap rule, arithmetic boundaries).
"""

from __future__ import annotations

import dataclasses
import inspect
import os
import re
from datetime import date as _date
from typing import Any, Dict, List, Tuple

from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve

YEAR = 360
LAB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIME_TEXT = os.path.join(LAB_ROOT, "corpus", "world-aad3e86", "Dikenocracy", "Protocols",
                         "L0_Physical_Truth", "DKP-0-TIME-001.md")

# §9 table, as printed in the pinned text (requirement ids TIME-9-01 .. TIME-9-04)
VECTORS = [
    ("TIME-9-01", "2026-01-01", 2461042, 6836, 83, "DY6836-083"),
    ("TIME-9-02", "2026-01-02", 2461043, 6836, 84, "DY6836-084"),
    ("TIME-9-03", "1970-01-01", 2440588, 6779, 149, "DY6779-149"),
    ("TIME-9-04", "2000-01-01", 2451545, 6815, 26, "DY6815-026"),
]


def gregorian_to_jdn(year: int, month: int, day: int) -> int:
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def jdn_to_gregorian(jdn: int) -> Tuple[int, int, int]:
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    return 100 * b + d - 4800 + m // 10, m + 3 - 12 * (m // 10), e - (153 * m + 2) // 5 + 1


def dy_doy(dti_day: int) -> Tuple[int, int]:
    return dti_day // YEAR, dti_day % YEAR + 1          # §5.1


def from_dy_doy(dy: int, doy: int) -> int:
    if not 1 <= doy <= YEAR:                            # §6.3: invalid DOY must be rejected
        raise ValueError("DOY must be in 1..360")
    return dy * YEAR + (doy - 1)                        # §6.2


def canonical(dy: int, doy: int) -> str:
    return f"DY{dy}-{doy:03d}"                          # §5.2


def parse_canonical(s: str) -> Tuple[int, int]:
    """Only the form canonical() writes: no sign but '-', no leading zeros in DY, DOY 001..360."""
    m = re.fullmatch(r"DY(0|-?[1-9]\d*)-(\d{3})", s)
    if not m or not 1 <= int(m.group(2)) <= YEAR:
        raise ValueError(f"not a canonical DTI date: {s!r}")
    return int(m.group(1)), int(m.group(2))


def year_bounds(dy: int, faults=()) -> Tuple[int, int]:
    """First and last DTI-Day of a DTI-Year (§3, §4.2)."""
    first, last = dy * YEAR, dy * YEAR + YEAR - 1
    if "gregorian_new_year" in faults:
        y = jdn_to_gregorian(first)[0] + 1
        first, last = gregorian_to_jdn(y, 1, 1), gregorian_to_jdn(y + 1, 1, 1) - 1
    if "leap_day" in faults and any(jdn_to_gregorian(j)[1:] == (2, 29) for j in range(first, last + 1)):
        last += 1
    return first, last


def store(records: List[Dict[str, Any]], faults=()) -> List[Dict[str, Any]]:
    """§7, §8: DTI-Day is the authority; DY/DOY are derived; a Gregorian date is shown for reading only."""
    out = []
    for rec in records:
        g = set(rec["given"])
        row = {"id": rec["id"], "purpose": rec["purpose"], "given": sorted(g), "signed": rec["signed"], "conflicts": []}
        greg = gregorian_to_jdn(*parse_gregorian(rec["gregorian"])) if "gregorian" in g else None
        if "dti_day" in g:
            day = rec["dti_day"]
            if "dy_doy" in g and from_dy_doy(rec["dy"], rec["doy"]) != day:
                row["conflicts"].append("dy_doy")
                if "derived_overrides" in faults:
                    day = from_dy_doy(rec["dy"], rec["doy"])
            if greg is not None and greg != rec["dti_day"]:
                row["conflicts"].append("gregorian")
        elif "dy_doy" in g:
            day = from_dy_doy(rec["dy"], rec["doy"])
            if greg is not None and greg != day:
                row["conflicts"].append("gregorian")
        elif "gregorian_as_authority" in faults:
            day = greg
        else:
            row.update(accepted=False, reason="neither DTI-Day nor (DY, DOY): a Gregorian date is shown for reading only (§7)")
            out.append(row)
            continue
        dy, doy = dy_doy(day)
        row.update(accepted=True, dti_day=day, dy=dy, doy=doy, derived=["dy", "doy"],
                   gregorian_display="%04d-%02d-%02d" % jdn_to_gregorian(day))
        if "unrecomputable_index" in faults and len(out) == 0:
            row.update(dy=None, doy=None, gregorian_display=None, derived=[])
        if rec["purpose"] != "record":
            row["reference"] = canonical(dy, doy) if "audit_by_canonical" in faults else f"DTI-Day {day}"
        out.append(row)
    return out


def parse_gregorian(s: str) -> Tuple[int, int, int]:
    parts = s.split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts) or len(parts[0]) != 4:
        raise LabInputError([f"input.dates: {s!r} is not YYYY-MM-DD (years 0001-9999)"])
    y, m, d = (int(p) for p in parts)
    if y < 1 or not (1 <= m <= 12 and 1 <= d <= 31) or jdn_to_gregorian(gregorian_to_jdn(y, m, d)) != (y, m, d):
        raise LabInputError([f"input.dates: {s!r} is not a valid Gregorian date"])
    return y, m, d


def reference_namespace() -> Dict[str, Any]:
    """Execute the §10 code block of the pinned TIME text (verified against CORPUS.json)."""
    from lab.tools.build_catalog import verify
    verify()
    with open(TIME_TEXT, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"### 10\..*?```python\n(.*?)```", text, re.S)
    if not m:
        raise RuntimeError("TIME §10 reference implementation not found in the pinned text")
    import sys
    import types
    mod = types.ModuleType("dkp_time_reference")
    sys.modules[mod.__name__] = mod          # dataclasses look the module up while building the class
    try:
        exec(compile(m.group(1), "DKP-0-TIME-001 §10", "exec"), mod.__dict__)   # pinned canonical text only
    finally:
        sys.modules.pop(mod.__name__, None)
    return mod.__dict__


FAULTS = {
    "derived_overrides": "a stored (DY, DOY) that disagrees with DTI-Day replaces it",
    "gregorian_as_authority": "a record with only a Gregorian date is accepted as authoritative",
    "audit_by_canonical": "an audit or dispute references the DY/DOY string instead of DTI-Day",
    "leap_day": "a DTI-Year containing 29 February gets 361 days",
    "gregorian_new_year": "DTI-Year boundaries are placed on 1 January",
    "event_epoch": "DTI-Day is counted from the Genesis launch (2025-12-10) instead of JDN 0",
    "julian_before_1582": "dates before 1582-10-15 are converted with the Julian calendar",
    "unrecomputable_index": "a stored record keeps DTI-Day but drops its derived DY/DOY and Gregorian display",
    "no_inverse_rule": "the conversion offered has no rule back to the civil calendar",
}
EVENT_EPOCH = (2025, 12, 10)                       # the Code's launch date: an event (fault event_epoch)
PROBES = [(1000, 3, 1), (1582, 10, 4), (1582, 10, 15), (1970, 1, 1), (2026, 1, 1)]   # proleptic Gregorian probes (§3)


def to_dti(y: int, m: int, d: int, faults=()) -> int:
    """The lab's conversion Gregorian -> DTI-Day, with the faults that change it."""
    if "julian_before_1582" in faults and (y, m, d) < (1582, 10, 15):
        a = (14 - m) // 12
        yy, mm = y + 4800 - a, m + 12 * a - 3
        jdn = d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - 32083          # Julian calendar day number
    else:
        jdn = gregorian_to_jdn(y, m, d)
    return jdn - gregorian_to_jdn(*EVENT_EPOCH) if "event_epoch" in faults else jdn
RECORD = {"type": "object", "fields": {
    "id": {"type": "str"},
    "given": {"type": "list", "min_items": 1, "max_items": 3, "items": {"type": "enum", "values": ["dti_day", "dy_doy", "gregorian"]}},
    "dti_day": {"type": "int", "min": 0, "max": 10 ** 8, "default": 0},
    "dy": {"type": "int", "min": -10 ** 6, "max": 10 ** 6, "default": 0},
    "doy": {"type": "int", "min": 1, "max": YEAR, "default": 1},
    "gregorian": {"type": "str", "default": "none"},                    # read only when "gregorian" is in given
    "purpose": {"type": "enum", "values": ["record", "audit", "dispute"], "default": "record"},
    "signed": {"type": "bool", "default": True}}}
RECORDS = [
    {"id": "by_day", "given": ["dti_day"], "dti_day": 2461042},
    {"id": "by_dy_doy", "given": ["dy_doy"], "dy": 6836, "doy": 84},
    {"id": "conflicting", "given": ["dti_day", "dy_doy", "gregorian"], "dti_day": 2461042, "dy": 6836, "doy": 90,
     "gregorian": "2026-01-09"},
    {"id": "gregorian_only", "given": ["gregorian"], "gregorian": "2026-01-01", "signed": False},
    {"id": "audit_of_conflict", "given": ["dy_doy"], "dy": 6836, "doy": 83, "purpose": "audit"},
    {"id": "dispute", "given": ["dti_day"], "dti_day": 2461043, "purpose": "dispute"},
]
NO_SUB_DAY = {"hour", "hours", "minute", "minutes", "second", "seconds", "time", "tz", "timezone", "utc_offset"}

IMPLEMENTS = {
    "TIME-2-02": ("unique_from_canonical", "IMPLEMENTED", None),
    "TIME-2-01": ("neutral_anchor", "PARTIAL", "Neutrality read as an arithmetic origin (DTI-Day = JDN by §3); whether JDN's own "
                  "origin is neutral is fixed by §3, not judged."),
    "TIME-2-03": ("recomputable_index", "IMPLEMENTED", None),
    "TIME-2-05": ("conversion_rules_provided", "PARTIAL", "Civil calendars = the Gregorian calendar the text names."),
    "TIME-3-01": ("jdn_proleptic_count", "IMPLEMENTED", None),
    "TIME-3-03": ("year_360_days", "IMPLEMENTED", None),
    "TIME-3-04": ("doy_1_to_360", "IMPLEMENTED", None),
    "TIME-4.1-01": ("civil_day_unit", "IMPLEMENTED", None),
    "TIME-4.1-02": ("no_sub_day_units", "IMPLEMENTED", None),
    "TIME-4.2-01": ("no_leap_rule", "IMPLEMENTED", None),
    "TIME-4.2-02": ("arithmetic_boundaries", "IMPLEMENTED", None),
    "TIME-5.2-02": ("string_fields", "IMPLEMENTED", None),
    "TIME-6.1-01": ("standard_jdn", "IMPLEMENTED", None),
    "TIME-6.3-02": ("negative_dy", "IMPLEMENTED", None),
    "TIME-6.3-03": ("derived_never_override", "IMPLEMENTED", None),
    "TIME-7-01": ("gregorian_for_reading", "IMPLEMENTED", None),
    "TIME-7-02": ("authoritative_has_index", "IMPLEMENTED", None),
    "TIME-7-03": ("dti_day_wins", "IMPLEMENTED", None),
    "TIME-8-01": ("signed_store_dti_day", "PARTIAL", "A SHOULD: a deviation is reported UNKNOWN, not FAIL."),
    "TIME-8-02": ("audits_reference_dti_day", "IMPLEMENTED", None),
    "TIME-10-03": ("reference_frozen", "IMPLEMENTED", None),
    "TIME-10-04": ("reference_rejects_doy", "IMPLEMENTED", None),
    "TIME-3-02": ("dti_day_is_jdn", "IMPLEMENTED", None),
    "TIME-5.1-01": ("dy_formula", "IMPLEMENTED", None),
    "TIME-5.1-02": ("doy_formula", "IMPLEMENTED", None),
    "TIME-5.2-01": ("string_form", "IMPLEMENTED", None),
    "TIME-6.2-01": ("roundtrip", "IMPLEMENTED", None),
    "TIME-6.3-01": ("invalid_doy_rejected", "IMPLEMENTED", None),
    "TIME-9-01": ("normative_vector", "IMPLEMENTED", None),
    "TIME-9-02": ("normative_vector", "IMPLEMENTED", None),
    "TIME-9-03": ("normative_vector", "IMPLEMENTED", None),
    "TIME-9-04": ("normative_vector", "IMPLEMENTED",
                  "The table row contradicts §5/§10; the check reports FAIL with tag corpus_inconsistency."),
    "TIME-10-01": ("reference_forward", "IMPLEMENTED", None),
    "TIME-10-02": ("reference_inverse", "IMPLEMENTED", None),
}


class TimeModule(LabModule):
    id = "time"
    version = "1.3.0"
    title = {"en": "Date index (TIME)", "ru": "Индекс дат (TIME)"}
    summary = {"en": "Gregorian dates to DTI-Day, DY/DOY and back; checks the normative vectors and the "
                     "canonical reference implementation.",
               "ru": "Григорианские даты в DTI-Day, DY/DOY и обратно; проверка нормативных векторов и "
                     "канонической эталонной реализации."}
    protocols = ["DKP-0-TIME-001"]
    example_order = ["normative_vectors", "year_boundary", "faulty_time"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_time_module.py"]
    inputs = {
        "dates": {"type": "list", "min_items": 1, "max_items": 200,
                  "items": {"type": "str"}, "default": ["2026-01-01", "1970-01-01", "2000-01-01"],
                  "source": "user", "label": {"en": "Gregorian dates (YYYY-MM-DD)",
                                              "ru": "Григорианские даты (ГГГГ-ММ-ДД)"}},
        "records": {"type": "list", "min_items": 0, "max_items": 50, "items": RECORD, "default": RECORDS, "source": "user",
                    "label": {"en": "Records arriving at the store (§7, §8)", "ru": "Записи, поступающие в хранилище (§7, §8)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        for s in r["dates"]:
            parse_gregorian(s)
        p = []
        ids = [x["id"] for x in r["records"]]
        if len(set(ids)) != len(ids):
            p.append("input.records: repeated id")
        for x in r["records"]:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", x["id"]):
                p.append(f"input.records: id {x['id']!r} must be lowercase letters, digits or _ (at most 24)")
            if len(set(x["given"])) != len(x["given"]):
                p.append(f"input.records: {x['id']} repeats a field in 'given'")
            if "gregorian" in x["given"]:
                try:
                    parse_gregorian(x["gregorian"])
                except LabInputError as e:
                    p += [f"input.records: {x['id']}: {m}" for m in e.problems]
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, resolved: Dict[str, Any]) -> ModuleResult:
        ref = reference_namespace()
        rows = []
        for s in resolved["dates"]:
            y, m, d = parse_gregorian(s)
            jdn = to_dti(y, m, d, resolved["faults"])
            dy, doy = dy_doy(jdn)
            back = jdn_to_gregorian(from_dy_doy(dy, doy))
            r_dd = ref["gregorian_to_dikenocratic"](y, m, d)
            rows.append({"gregorian": s, "dti_day": jdn, "dy": dy, "doy": doy, "canonical": canonical(dy, doy),
                         "roundtrip": "%04d-%02d-%02d" % back,
                         "reference": {"dti_day": ref["gregorian_to_jdn"](y, m, d), "canonical": r_dd.canonical(),
                                       "back": list(ref["dikenocratic_to_gregorian"](r_dd.dy, r_dd.doy))}})
        n = len(rows)
        checks: List[CheckResult] = []

        def add(rid, name, ok, text, **ev):
            checks.append(CheckResult(rid, name, PASS if ok else FAIL, text, evidence=ev))

        add("TIME-3-02", "dti_day_is_jdn", all(r["dti_day"] == r["reference"]["dti_day"] for r in rows),
            f"DTI-Day equals the JDN of the reference algorithm for {n} dates")
        add("TIME-5.1-01", "dy_formula", all(r["dy"] == r["dti_day"] // 360 for r in rows),
            "DY = floor(DTI-Day / 360)")
        add("TIME-5.1-02", "doy_formula", all(r["doy"] == r["dti_day"] % 360 + 1 for r in rows),
            "DOY = (DTI-Day mod 360) + 1")
        add("TIME-5.2-01", "string_form", all(re.fullmatch(r"DY-?\d+-\d{3}", r["canonical"]) for r in rows),
            "canonical form DY<dy>-<doy> with a three-digit DOY")
        add("TIME-6.2-01", "roundtrip", all(r["roundtrip"] == r["gregorian"] for r in rows),
            f"DY/DOY → DTI-Day → Gregorian returns the input for all {n} dates")
        rejected = []
        for bad in (0, 361):
            try:
                from_dy_doy(6836, bad)
            except ValueError:
                rejected.append(bad)
            try:
                ref["DikenocraticDate"](6836, bad)
                ref_ok = False
            except ValueError:
                ref_ok = True
            rejected.append(("reference", bad, ref_ok))
        add("TIME-6.3-01", "invalid_doy_rejected", rejected == [0, ("reference", 0, True), 361, ("reference", 361, True)],
            "DOY 0 and 361 are rejected (lab and reference implementation)")
        add("TIME-10-01", "reference_forward", all(r["canonical"] == r["reference"]["canonical"] for r in rows),
            "the lab's conversion equals the §10 reference implementation (Gregorian → DY/DOY)")
        add("TIME-10-02", "reference_inverse",
            all("%04d-%02d-%02d" % tuple(r["reference"]["back"]) == r["gregorian"] for r in rows),
            "the §10 reference inverse returns the input date")
        vec = []
        for rid, g, jdn_t, dy_t, doy_t, can_t in VECTORS:
            jdn = gregorian_to_jdn(*parse_gregorian(g))
            dy, doy = dy_doy(jdn)
            ok = [jdn, dy, doy, canonical(dy, doy)] == [jdn_t, dy_t, doy_t, can_t]
            consistent = dy_doy(jdn_t) == (dy_t, doy_t)
            vec.append({"requirement_id": rid, "gregorian": g, "table": [jdn_t, dy_t, doy_t, can_t],
                        "computed": [jdn, dy, doy, canonical(dy, doy)], "matches": ok,
                        "table_row_consistent_with_section_5": consistent})
            if ok:
                add(rid, "normative_vector", True, f"{g}: {can_t} reproduced")
            else:
                checks.append(CheckResult(rid, "normative_vector", FAIL,
                                          f"{g}: table says {can_t} (DTI-Day {jdn_t}); §5 gives {canonical(dy, doy)} "
                                          f"for DTI-Day {jdn}. The table row contradicts §5 and §10 — corpus "
                                          f"inconsistency (F-017), erratum pending; the lab does not choose a value",
                                          evidence={"tag": "corpus_inconsistency" if not consistent else "mismatch",
                                                    "table": [jdn_t, dy_t, doy_t, can_t],
                                                    "computed": [jdn, dy, doy, canonical(dy, doy)]}))
        checks += self.structure_checks(resolved, rows, ref)
        stored = store(resolved["records"], resolved["faults"])
        checks += record_checks(resolved, stored)
        checks += principle_checks(resolved, rows, stored, ref)
        explain = [{"en": f"{r['gregorian']} → DTI-Day {r['dti_day']} → {r['canonical']}",
                    "ru": f"{r['gregorian']} → DTI-Day {r['dti_day']} → {r['canonical']}"} for r in rows[:20]]
        if any(not v["matches"] for v in vec):
            explain.append({"en": "The §9 table row for 2000-01-01 (DY6815-026) contradicts §5 and the §10 code, "
                                  "which give DY6809-306. The lab reports both and does not choose.",
                            "ru": "Строка таблицы §9 для 2000-01-01 (DY6815-026) противоречит §5 и коду §10, "
                                  "по которым выходит DY6809-306. Лаборатория показывает оба значения и не выбирает."})
        for x in stored:
            if not x["accepted"]:
                explain.append({"en": f"Record {x['id']}: refused as authoritative ({x['reason']}).",
                                "ru": f"Запись {x['id']}: не принята как авторитетная (только григорианская дата, §7)."})
            elif x["conflicts"]:
                explain.append({"en": f"Record {x['id']}: {', '.join(x['conflicts'])} disagree(s); stored DTI-Day {x['dti_day']} ({canonical(x['dy'], x['doy'])}).",
                                "ru": f"Запись {x['id']}: расходятся {', '.join(x['conflicts'])}; сохранён DTI-Day {x['dti_day']} ({canonical(x['dy'], x['doy'])})."})
        years = [dict(zip(("dy", "first", "last"), (dy,) + year_bounds(dy, resolved["faults"]))) for dy in self.years(rows)]
        return ModuleResult(outputs={"dates": rows, "vectors": vec, "records": stored, "years": years, "operational_use": False},
                            checks=checks, explain=explain)

    @staticmethod
    def years(rows) -> List[int]:
        leap = {dy_doy(gregorian_to_jdn(y, 2, 29))[0] for y in (2000, 2024)}          # years that contain 29 February
        return sorted({r["dy"] + k for r in rows for k in (-1, 0, 1)} | leap)

    def structure_checks(self, resolved, rows, ref) -> List[CheckResult]:
        out: List[CheckResult] = []
        faults = resolved["faults"]

        def add(rid, name, ok, text, bad=None):
            out.append(CheckResult(rid, name, PASS if ok else FAIL, text if ok else f"{text}: violated",
                                   evidence={"violations": bad[:10]} if bad else {}))

        # §2 determinism: one canonical string per DTI-Day, and it parses back to that day only
        window = {d for r in rows for d in range(r["dti_day"] - YEAR, r["dti_day"] + YEAR)}
        strings = {canonical(*dy_doy(d)): d for d in window}
        bad = [s for s, d in strings.items() if from_dy_doy(*parse_canonical(s)) != d]
        rejected = []
        for s in ("DY6836-84", "DY06836-084", "DY+6836-084", "DY6836-361", "DY-0-001"):
            try:
                parse_canonical(s)
            except ValueError:
                rejected.append(s)
        add("TIME-2-02", "unique_from_canonical", len(strings) == len(window) and not bad and len(rejected) == 5,
            f"{len(window)} DTI-Days around the inputs have {len(strings)} distinct canonical strings, each parsing back to its own "
            "day; non-canonical forms (unpadded DOY, padded or signed DY, DOY 361, DY-0) are rejected", bad or [s for s in (
                "DY6836-84", "DY06836-084", "DY+6836-084", "DY6836-361", "DY-0-001") if s not in rejected])
        # §3, §4.2: the year table
        yrs = [(dy,) + year_bounds(dy, faults) for dy in self.years(rows)]
        long = [dy for dy, a, b in yrs if b - a + 1 != YEAR]
        leap_years = [dy for dy, a, b in yrs if any(jdn_to_gregorian(j)[1:] == (2, 29) for j in range(a, b + 1))]
        add("TIME-3-03", "year_360_days", not long, f"{len(yrs)} DTI-Years each hold exactly 360 consecutive DTI-Days", long)
        add("TIME-4.2-01", "no_leap_rule", not [dy for dy in leap_years if dy in long],
            f"{len(leap_years)} DTI-Years containing 29 February still hold 360 days", [dy for dy in leap_years if dy in long])
        off = [dy for dy, a, b in yrs if a != dy * YEAR]
        gaps = [yrs[i][0] for i in range(1, len(yrs)) if yrs[i][0] == yrs[i - 1][0] + 1 and yrs[i][1] != yrs[i - 1][2] + 1]
        add("TIME-4.2-02", "arithmetic_boundaries", not off and not gaps,
            "every DTI-Year starts at DY × 360, whatever the Gregorian date, and years tile without gaps", off + gaps)
        doys = [dy_doy(d)[1] for dy, a, b in yrs for d in (a, b)]
        add("TIME-3-04", "doy_1_to_360", all(1 <= r["doy"] <= YEAR for r in rows) and
            all(dy_doy(a)[1] == 1 and dy_doy(b)[1] == YEAR for dy, a, b in yrs),
            "every DOY lies in 1..360; each year runs from DOY 1 to DOY 360", [x for x in doys if not 1 <= x <= YEAR])
        # §4.1 the civil day; no sub-day units
        nxt = []
        for r in rows:
            y, m, d = parse_gregorian(r["gregorian"])
            if (y, m, d) != (9999, 12, 31):
                t = _date(y, m, d).toordinal() + 1
                n = _date.fromordinal(t)
                if gregorian_to_jdn(n.year, n.month, n.day) - r["dti_day"] != 1:
                    nxt.append(r["gregorian"])
        add("TIME-4.1-01", "civil_day_unit", not nxt, f"the day after each of {len(rows)} dates has the next DTI-Day: one civil day "
            "is one unit", nxt)
        params = {}
        for name in ("gregorian_to_jdn", "jdn_to_gregorian", "jdn_to_dikenocratic", "dikenocratic_to_jdn",
                     "gregorian_to_dikenocratic", "dikenocratic_to_gregorian", "DikenocraticDate"):
            params[name] = list(inspect.signature(ref[name]).parameters)
        for fn in (gregorian_to_jdn, jdn_to_gregorian, dy_doy, from_dy_doy, canonical):
            params["lab." + fn.__name__] = list(inspect.signature(fn).parameters)
        sub = [f"{k}({p})" for k, ps in params.items() for p in ps if p.lower() in NO_SUB_DAY]
        add("TIME-4.1-02", "no_sub_day_units", not sub, f"no function of the §10 reference or of the lab takes an hour, minute, second "
            f"or time-zone argument ({len(params)} signatures)", sub)
        # §5.2 fields, §6.1 standard JDN, §6.3 negative DY
        probe = {-1: "DY-1-360", 0: "DY0-001", 359: "DY0-360", 2461042: "DY6836-083"}
        wrong = [d for d, s_ in probe.items() if canonical(*dy_doy(d)) != s_ or ref["jdn_to_dikenocratic"](d).canonical() != s_]
        bad_rows = [r["canonical"] for r in rows if not re.fullmatch(r"DY-?\d+-\d{3}", r["canonical"])]
        add("TIME-5.2-02", "string_fields", not wrong and not bad_rows,
            "DY is a signed integer (DTI-Day -1 → DY-1-360), DOY three digits zero-padded (DY0-001); lab and §10 agree", wrong + bad_rows)
        jd = [r["gregorian"] for r in rows if _date(*parse_gregorian(r["gregorian"])).toordinal() + 1721425 != r["dti_day"]]
        add("TIME-6.1-01", "standard_jdn", not jd, f"JDN of {len(rows)} dates equals an independent algorithm (proleptic Gregorian "
            "ordinal + 1721425); DTI-Day = JDN; (DY, DOY) by §5", jd)
        try:
            neg = (from_dy_doy(-1, YEAR) == -1 and ref["dikenocratic_to_jdn"](ref["DikenocraticDate"](-1, YEAR)) == -1
                   and dy_doy(-1) == (-1, YEAR))
        except ValueError:
            neg = False
        add("TIME-6.3-02", "negative_dy", neg, "DY -1 is accepted by the lab and the §10 reference and maps to DTI-Day -1")
        # §10 reference: frozen dataclass, __post_init__ rejects DOY outside 1..360
        cls = ref["DikenocraticDate"]
        frozen = dataclasses.is_dataclass(cls) and cls.__dataclass_params__.frozen
        try:
            setattr(cls(6836, 1), "doy", 2)
            frozen = False
        except dataclasses.FrozenInstanceError:
            pass
        add("TIME-10-03", "reference_frozen", frozen, "the §10 DikenocraticDate is a frozen dataclass: a date cannot be changed after "
            "it is made")
        res = []
        for doy in (0, 1, YEAR, YEAR + 1):
            try:
                cls(6836, doy)
                res.append((doy, "accepted"))
            except ValueError as e:
                res.append((doy, str(e)))
        add("TIME-10-04", "reference_rejects_doy",
            res == [(0, "DOY must be in 1..360"), (1, "accepted"), (YEAR, "accepted"), (YEAR + 1, "DOY must be in 1..360")],
            "the §10 __post_init__ rejects DOY 0 and 361 and accepts 1 and 360")
        return out

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"dates": len(outputs["dates"]),
                "vectors_reproduced": sum(1 for v in outputs["vectors"] if v["matches"])}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {"normative_vectors": {"dates": [v[1] for v in VECTORS]},
                "year_boundary": {"dates": ["2025-12-31", "2026-01-01", "2026-12-31"]},
                "faulty_time": {"faults": ["derived_overrides", "gregorian_as_authority", "audit_by_canonical", "leap_day"]}}

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"invalid_date": {"dates": ["2026-02-30"]},
                "invalid_record_date": {"records": [{"id": "a", "given": ["gregorian"], "gregorian": "2026-13-01"}]},
                "repeated_record": {"records": [{"id": "a", "given": ["dti_day"]}, {"id": "a", "given": ["dti_day"]}]},
                "doy_out_of_range": {"records": [{"id": "a", "given": ["dy_doy"], "dy": 1, "doy": 361}]}}


def principle_checks(r: Dict[str, Any], rows, stored, ref) -> List[CheckResult]:
    """TIME §2 design principles 1, 3, 5 and the §3 JDN definition (review КТ5 reading)."""
    faults = r["faults"]
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    # §2.1 neutrality: the origin is arithmetic (DTI-Day = JDN, DY 0 starts at DTI-Day 0), no event re-anchors it
    origin = [f"{x['gregorian']}: DTI-Day {x['dti_day']} != JDN {gregorian_to_jdn(*parse_gregorian(x['gregorian']))}"
              for x in rows if x["dti_day"] != gregorian_to_jdn(*parse_gregorian(x["gregorian"]))]
    if year_bounds(0, faults)[0] != 0:
        origin.append(f"DY 0 starts at DTI-Day {year_bounds(0, faults)[0]}")
    out.append(v("TIME-2-01", "neutral_anchor", origin[:5],
                 "the index has an arithmetic origin: DTI-Day = JDN (§3) and DY 0 begins at DTI-Day 0; no religious, "
                 "cultural, political or personal event anchors it", "{n} dates indexed from another origin"))
    # §3 JDN: an integer count of civil days in the proleptic Gregorian calendar (independent: datetime's proleptic ordinal)
    bad = []
    for y, m, d in PROBES:
        got = to_dti(y, m, d, faults) + (gregorian_to_jdn(*EVENT_EPOCH) if "event_epoch" in faults else 0)
        want = _date(y, m, d).toordinal() + 1721425
        if got != want:
            bad.append(f"{y:04d}-{m:02d}-{d:02d}: {got} != {want}")
    a, b = (to_dti(1582, 10, 4, faults), to_dti(1582, 10, 15, faults))
    if b - a != 11:
        bad.append(f"1582-10-04 -> 1582-10-15 is {b - a} days in the proleptic Gregorian count, not 11")
    out.append(v("TIME-3-01", "jdn_proleptic_count", bad,
                 f"JDN counts civil days in the proleptic Gregorian calendar ({len(PROBES)} probes, including dates before "
                 "1582, agree with an independent proleptic day count)", "{n} days counted otherwise"))
    # §2.3 auditability: every stored record allows independent recomputation of its time index
    acc = [x for x in stored if x["accepted"]]
    bad = []
    for x in acc:
        if x["dy"] is None or x["gregorian_display"] is None:
            bad.append(f"{x['id']}: derived fields missing")
        elif from_dy_doy(x["dy"], x["doy"]) != x["dti_day"] or \
                gregorian_to_jdn(*parse_gregorian(x["gregorian_display"])) != x["dti_day"]:
            bad.append(f"{x['id']}: stored forms do not recompute to DTI-Day {x['dti_day']}")
    out.append(v("TIME-2-03", "recomputable_index", bad,
                 f"{len(acc)} stored records: DTI-Day recomputes from the stored DY/DOY and from the Gregorian display",
                 "{n} records whose time index cannot be recomputed") if acc else
               CheckResult("TIME-2-03", "recomputable_index", NOT_APPLICABLE, "stored records", applicability="no record stored"))
    # §2.5 interoperability: explicit rules both ways, provided by the pinned §10 reference, and they round-trip
    ns = {k: f for k, f in ref.items() if not ("no_inverse_rule" in faults and k == "dikenocratic_to_gregorian")}
    have = [k for k in ("gregorian_to_dikenocratic", "dikenocratic_to_gregorian") if callable(ns.get(k))]
    bad = [f"no {k}" for k in ("gregorian_to_dikenocratic", "dikenocratic_to_gregorian") if k not in have]
    if not bad:
        for x in rows:
            dd = ns["gregorian_to_dikenocratic"](*parse_gregorian(x["gregorian"]))
            if "%04d-%02d-%02d" % tuple(ns["dikenocratic_to_gregorian"](dd.dy, dd.doy)) != x["gregorian"]:
                bad.append(f"{x['gregorian']}: no round trip")
    out.append(v("TIME-2-05", "conversion_rules_provided", bad,
                 "explicit conversion rules to and from the Gregorian calendar are given (§6) and implemented in the pinned "
                 f"§10 reference; both directions round-trip on {len(rows)} dates", "{n} missing or failing conversion rules"))
    return out


def record_checks(r: Dict[str, Any], stored: List[Dict[str, Any]]) -> List[CheckResult]:
    """§6.3, §7, §8 recomputed from the input records and the store."""
    out: List[CheckResult] = []
    inp = {x["id"]: x for x in r["records"]}
    acc = [x for x in stored if x["accepted"]]

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    if not stored:
        for rid, chk in (("TIME-6.3-03", "derived_never_override"), ("TIME-7-01", "gregorian_for_reading"),
                         ("TIME-7-02", "authoritative_has_index"), ("TIME-7-03", "dti_day_wins"),
                         ("TIME-8-01", "signed_store_dti_day"), ("TIME-8-02", "audits_reference_dti_day")):
            out.append(na(rid, chk, "records", "none"))
        return out

    def expected(x):
        i = inp[x["id"]]
        if "dti_day" in i["given"]:
            return i["dti_day"]
        if "dy_doy" in i["given"]:
            return from_dy_doy(i["dy"], i["doy"])
        return None

    out.append(v("TIME-7-02", "authoritative_has_index", [x["id"] for x in acc if expected(x) is None],
                 f"{len(acc)} authoritative records carry DTI-Day or (DY, DOY); {len(stored) - len(acc)} with a Gregorian date only "
                 "were not taken as authoritative", "{n} records authoritative on a Gregorian date alone"))
    wrong = [x["id"] for x in acc if expected(x) is not None and x["dti_day"] != expected(x)]
    derived = [x["id"] for x in acc if (x["dy"], x["doy"]) != dy_doy(x["dti_day"])]
    out.append(v("TIME-6.3-03", "derived_never_override", wrong + derived,
                 "stored DY/DOY are derived from DTI-Day and never replace it", "{n} records where a derived field won"))
    conf = [x for x in acc if x["conflicts"] and "dti_day" in inp[x["id"]]["given"]]
    out.append(v("TIME-7-03", "dti_day_wins", [x["id"] for x in conf if x["dti_day"] != inp[x["id"]]["dti_day"]],
                 f"{len(conf)} conflicting records keep their DTI-Day", "{n} conflicts resolved against DTI-Day")
               if conf else na("TIME-7-03", "dti_day_wins", "conflicting records", "none"))
    disp = [x["id"] for x in acc if x["gregorian_display"] != "%04d-%02d-%02d" % jdn_to_gregorian(x["dti_day"])]
    out.append(v("TIME-7-01", "gregorian_for_reading", disp + [x["id"] for x in acc if expected(x) is None],
                 "every stored record shows its Gregorian date, converted from DTI-Day; no record takes authority from it",
                 "{n} records where the Gregorian date is wrong or authoritative"))
    signed = [x for x in acc if x["signed"]]
    miss = [x["id"] for x in signed if "dti_day" not in x or x["derived"] != ["dy", "doy"]]
    out.append((CheckResult("TIME-8-01", "signed_store_dti_day", UNKNOWN, f"{len(miss)} signed records stored without DTI-Day "
                            "(a SHOULD: whether the deviation is justified is not modelled)", evidence={"records": miss[:10]})
                if miss else CheckResult("TIME-8-01", "signed_store_dti_day", PASS,
                                         f"{len(signed)} signed records store DTI-Day as the authority and DY/DOY as derived fields"))
               if signed else na("TIME-8-01", "signed_store_dti_day", "signed records", "none"))
    aud = [x for x in acc if x["purpose"] != "record"]
    out.append(v("TIME-8-02", "audits_reference_dti_day", [x["id"] for x in aud if x.get("reference") != f"DTI-Day {x['dti_day']}"],
                 f"{len(aud)} audit and dispute records reference DTI-Day", "{n} reference something else")
               if aud else na("TIME-8-02", "audits_reference_dti_day", "audits or disputes", "none"))
    return out


for _spec in TimeModule.inputs.values():
    if _spec["type"] == "list" and _spec["items"]["type"] == "object":
        _spec["default"] = [resolve(x, _spec["items"]["fields"]) for x in _spec["default"]]
