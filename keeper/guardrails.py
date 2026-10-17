"""Deterministic boundaries; model text never supplies provenance or executes jobs."""
from __future__ import annotations

import copy
import json
import re
from decimal import Decimal

from lab import api
from lab.core.registry import requirements
from lab.modules import MODULES

SUPPORTED = {"work_cycle"}
# H-WC-1..4: phases, even allocation, recovery placement, daily demand profile.
ASSUMPTIONS = {"phase_offsets", "shift_starts", "work_before_recovery", "demand"}
NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?(?!\w)")
BRACKET = re.compile(r"\[([^\[\]\n]+)\]")
UNSAFE = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://|\bwww\.|[a-z]:[\\/]|(?:^|\s)[\\/~]\w|\w[\\/]\w+[\\/]|\.\.|`|[;$]|"   # paths, not "24/7"
    r"\b(?:run_shell|exec|eval|subprocess|powershell|cmd\.exe|python|bash|curl|wget)\b|"
    r"\b(?:import|def)\s+\w+|\w+\s*\([^)]*\)|\b\w+\.(?:py|sh|exe|txt|json|csv)\b)", re.I)


def flag(flags, code, detail):
    item = {"code": code, "detail": detail}
    if item not in flags:
        flags.append(item)


def safe_data(value):
    if isinstance(value, str):
        return len(value) <= 1000 and not UNSAFE.search(value)
    if isinstance(value, dict):
        return all(safe_data(k) and safe_data(v) for k, v in value.items())
    if isinstance(value, list):
        return all(safe_data(v) for v in value)
    return value is None or type(value) in (bool, int, float)


def numbers(text):
    return {Decimal(m.group().replace(",", ".")) for m in NUMBER.finditer(text)}


def leaves(value):
    if isinstance(value, dict):
        return [x for v in value.values() for x in leaves(v)]
    if isinstance(value, list):
        return [x for v in value for x in leaves(v)]
    return [value]


def proposal(module, params, question, lang):
    if module not in SUPPORTED or not isinstance(params, dict):
        raise ValueError("Unsupported proposal")
    manifest = MODULES[module].manifest()
    schema = manifest["inputs"]
    if params.keys() - schema.keys():
        raise ValueError("Unknown input key")
    req = copy.deepcopy(api.example_request(module))
    req["variants"] = [{"name": "visitor", "input": {**req["variants"][0]["input"], **params}}]
    validation = api.validate_payload(req)
    if not validation["ok"]:
        raise ValueError("Invalid module input")
    bound = intake_values(question)
    missing = [key for key, value in params.items() if key not in bound or value != bound[key]]
    if not params:
        missing = list(INTAKE)
    if missing:
        return {"missing": sorted(set(missing))}
    resolved = validation["resolved"]["visitor"]
    req["variants"][0]["input"] = resolved
    fields = []
    for key, spec in schema.items():
        hypothesis = spec.get("source") in {"hypothesis", "alternative"} or key in ASSUMPTIONS
        field = {**spec, "key": key, "value": resolved[key],
                 "origin": "user" if key in params else "hypothesis" if hypothesis else "default",
                 "label": spec.get("label", {}).get(lang, spec.get("label", {}).get("en", key))}
        if hypothesis:
            field["note"] = "Modelling assumption (H-WC-1..4); editable by the visitor."
        fields.append(field)
    return {"module": module, "scenario": "S-LAB-08", "request": req, "fields": fields,
            "validation": {"ok": True, "problems": []},
            "note": "Research run of the lab (alpha). Not a calibrated model; not for real enforcement."}


# Published intake rule for S-LAB-08 (КТ8 TZ §6: free text maps to a scenario only through a limited, published set).
# A request to compute a round-the-clock roster is recognised by a calculation verb plus a roster term; the three
# numbers the run needs are read literally from the question.  Nothing is inferred by the model.
CALC = re.compile(r"\b(посчита|рассчита|вычисл|смоделир|calculat|comput|simulat)", re.I)
ROSTER = re.compile(r"смен|круглосуточ|24/7|график|покрыти|штат|shift|roster|coverage|staff|round-the-clock", re.I)
INTAKE = {
    "workers": re.compile(r"(\d{1,4})\s*(?:работник|сотрудник|человек\s+в\s+штате|workers?\b|staff\b|employees?\b)", re.I),
    "demand": re.compile(r"(\d{1,3})\s*(?:человек\w*|people|persons?)\s*(?:на\s+смене|на\s+дежурств\w*|в\s+час|каждый\s+час|"
                         r"on\s+duty|on\s+shift|per\s+hour|every\s+hour)|по\s+(\d{1,3})\s+человек\w*", re.I),
    "horizon_days": re.compile(r"(\d{1,3})\s*(?:дн|день|дня|сут|days?\b)", re.I),
}
# Do not accept the tail of a decimal, negative number or protocol identifier.
INTAKE = {key: re.compile(r"(?<![\w.,+\-])(?:" + rx.pattern + ")", re.I) for key, rx in INTAKE.items()}


def intake_values(question):
    params = {}
    for key, rx in INTAKE.items():
        values = {int(next(g for g in m.groups() if g)) for m in rx.finditer(question)}
        if len(values) == 1:
            value = values.pop()
            params[key] = [value] * 24 if key == "demand" else value
    return params


def intake_work_cycle(question, lang):
    """None when the question is not a S-LAB-08 calculation request; else a proposal or {"missing": [...]}."""
    if not (CALC.search(question) and ROSTER.search(question)):
        return None
    params = intake_values(question)
    missing = [k for k in INTAKE if k not in params]
    if missing:
        return {"missing": missing}
    try:
        return proposal("work_cycle", params, question, lang)
    except ValueError:
        return {"missing": sorted(params)}


def postcheck(answer, fragments, flags, summary=None):
    trusted = {f["cite"] for f in fragments}

    def citation(match):
        if match[1] in trusted:
            return match[0]
        flag(flags, "unknown_citation", "Removed a citation not supplied in this request.")
        return ""

    answer = BRACKET.sub(citation, answer)
    texts = [" ".join(f["text"].split()) for f in fragments]

    def quote(match):
        inner = next(x for x in match.groups() if x is not None)
        if len(inner) >= 20 and not any(" ".join(inner.split()) in text for text in texts):
            flag(flags, "unverified_quote", "Removed quotation marks from a non-verbatim span.")
            return inner
        return match[0]

    answer = re.sub(r'«([^»]*)»|"([^"]*)"|“([^”]*)”', quote, answer)
    if summary is not None:
        clean = BRACKET.sub("", answer)
        clean = re.sub(r"(?m)^\s*\d{1,2}[.)]\s+", "", clean)
        extra = numbers(clean) - numbers(summary)
        if extra:
            flag(flags, "number_not_in_result", "Numbers absent from summary: " + ", ".join(map(str, sorted(extra))))
    return answer


def report_summary(report):
    result = {"module": report["module"]["id"], "result_id": report["result_id"], "variants": {}}
    rids = set()

    def outputs(value, prefix=""):
        out = {}
        for key, item in sorted(value.items()):
            path = prefix + key
            if type(item) in (int, float) or (isinstance(item, list) and len(item) <= 24
                    and all(type(x) in (int, float, bool) or isinstance(x, str) and len(x) <= 80 for x in item)):
                out[path] = item
            elif isinstance(item, dict):
                out.update(outputs(item, path + "."))
        return out

    for name, variant in sorted(report["variants"].items()):
        counts = dict.fromkeys(("PASS", "FAIL", "UNKNOWN", "N/A"), 0)
        issues = []
        for check in variant["checks"]:
            rids.add(check["requirement_id"])
            status = "N/A" if check["status"] == "NOT_APPLICABLE" else check["status"]
            counts[status] += 1
            if status in {"FAIL", "UNKNOWN"}:
                issues.append({k: check[k] for k in ("requirement_id", "check", "status", "explanation")})
        result["variants"][name] = {"outputs": outputs(variant["outputs"]), "counts": counts, "issues": issues}
    return json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False), rids


def provisions(index, rids):
    # Resolve registry ids to pinned document sections, never guess from id spelling.
    wanted = set()
    docs = {f["document_id"] for f in index.frags if f["source_type"] in {"protocol", "code"}}
    for doc in sorted(docs):
        for req in requirements(doc):
            if req["id"] in rids:
                wanted.add((doc, "§" + req["section"]))
    return [f for f in index.frags if (f["document_id"], f["section"]) in wanted][:5]


# Known UNRESOLVED questions for S-LAB-08, bound to registry requirements, not search rank.
WORK_CYCLE_QUESTIONS = {"Q-012": {"WORKCYCLE-3-02", "WORKCYCLE-8.1-01"},
                        "Q-013": {"WORKCYCLE-5.1-01", "WORKCYCLE-8.2-02"}}


def work_cycle_questions(index, rids=None):
    wanted = {qid for qid, linked in WORK_CYCLE_QUESTIONS.items() if rids is None or linked & rids}
    return [f for f in index.frags if f["document_id"] in wanted and f["fid"].endswith("#0")
            and f["source_type"] == "question" and f["status"] == "UNRESOLVED"]


def summary_answer(summary, index, lang):
    """Only trusted report fields; percentages have an explicit Decimal conversion."""
    data = json.loads(summary)
    lines = ["Сводка лаборатории (без генеративного объяснения)." if lang == "ru" else
             "Lab summary (no generated explanation)."]
    lines.append("result_id: " + data["result_id"])
    for name, variant in data["variants"].items():
        lines.extend(["", name + ":", "; ".join(f"{k}: {v}" for k, v in variant["counts"].items())])
        for key, value in variant["outputs"].items():
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
            if key == "coverage.covered_fraction":
                percent = Decimal(str(value)) * 100
                lines.append(f"coverage.covered_percent: {percent}% (coverage.covered_fraction × 100)")
        for issue in variant["issues"]:
            refs = " ".join(f"[{f['cite']}]" for f in provisions(index, {issue["requirement_id"]}))
            lines.append(f"{issue['status']} {issue['requirement_id']} / {issue['check']}: "
                         f"{issue['explanation']} {refs}".rstrip())
    return "\n".join(lines)
