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
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple

from lab.core.checks import FAIL, PASS, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError

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


IMPLEMENTS = {
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
    version = "1.1.0"
    title = {"en": "Date index (TIME)", "ru": "Индекс дат (TIME)"}
    summary = {"en": "Gregorian dates to DTI-Day, DY/DOY and back; checks the normative vectors and the "
                     "canonical reference implementation.",
               "ru": "Григорианские даты в DTI-Day, DY/DOY и обратно; проверка нормативных векторов и "
                     "канонической эталонной реализации."}
    protocols = ["DKP-0-TIME-001"]
    example_order = ["normative_vectors", "year_boundary"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_time_module.py"]
    inputs = {
        "dates": {"type": "list", "min_items": 1, "max_items": 200,
                  "items": {"type": "str"}, "default": ["2026-01-01", "1970-01-01", "2000-01-01"],
                  "source": "user", "label": {"en": "Gregorian dates (YYYY-MM-DD)",
                                              "ru": "Григорианские даты (ГГГГ-ММ-ДД)"}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        for s in r["dates"]:
            parse_gregorian(s)
        return r

    def evaluate(self, resolved: Dict[str, Any]) -> ModuleResult:
        ref = reference_namespace()
        rows = []
        for s in resolved["dates"]:
            y, m, d = parse_gregorian(s)
            jdn = gregorian_to_jdn(y, m, d)
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
        explain = [{"en": f"{r['gregorian']} → DTI-Day {r['dti_day']} → {r['canonical']}",
                    "ru": f"{r['gregorian']} → DTI-Day {r['dti_day']} → {r['canonical']}"} for r in rows[:20]]
        if any(not v["matches"] for v in vec):
            explain.append({"en": "The §9 table row for 2000-01-01 (DY6815-026) contradicts §5 and the §10 code, "
                                  "which give DY6809-306. The lab reports both and does not choose.",
                            "ru": "Строка таблицы §9 для 2000-01-01 (DY6815-026) противоречит §5 и коду §10, "
                                  "по которым выходит DY6809-306. Лаборатория показывает оба значения и не выбирает."})
        return ModuleResult(outputs={"dates": rows, "vectors": vec}, checks=checks, explain=explain)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"dates": len(outputs["dates"]),
                "vectors_reproduced": sum(1 for v in outputs["vectors"] if v["matches"])}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {"normative_vectors": {"dates": [v[1] for v in VECTORS]},
                "year_boundary": {"dates": ["2025-12-31", "2026-01-01", "2026-12-31"]}}

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"invalid_date": {"dates": ["2026-02-30"]}}
