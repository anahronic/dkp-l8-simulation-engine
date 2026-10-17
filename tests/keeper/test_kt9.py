"""KT9 regressions: field provenance is semantic binding, never numeric overlap."""
import json
from pathlib import Path

import pytest

from keeper.guardrails import WORK_CYCLE_QUESTIONS, intake_work_cycle, proposal


@pytest.mark.parametrize("question,params,missing", [
    ("Our staff is 12 workers. We plan for 14 days. Explain work_cycle.",
     {"workers": 14, "horizon_days": 12}, {"workers", "horizon_days"}),
    ("12 workers, 12 days", {"workers": 12, "horizon_days": 12}, set()),
    ("12 days; explain WORK-CYCLE", {"workers": 12}, {"workers"}),
    ("Explain protocol DKP-12-WORK-CYCLE-001", {"workers": 12}, {"workers"}),
    ("12 workers or 14 workers, 7 days", {"workers": 12, "horizon_days": 7}, {"workers"}),
    ("12 workers, 7 days or 14 days", {"workers": 12, "horizon_days": 7}, {"horizon_days"}),
    ("12 workers, 3 people on duty or 4 people on duty", {"demand": [3] * 24}, {"demand"}),
    ("12 workers, 12 workers, 14 days", {"workers": 12, "horizon_days": 14}, set()),
    ("-12 workers, 1.12 workers", {"workers": 12}, {"workers"}),
    ("12 workers, presence_hours 12", {"presence_hours": 12}, {"presence_hours"}),
])
def test_field_binding(question, params, missing):
    result = proposal("work_cycle", params, question, "en")
    assert set(result.get("missing", [])) == missing
    if missing:
        assert "fields" not in result and "request" not in result
    else:
        fields = {f["key"]: f for f in result["fields"]}
        assert all(fields[k]["origin"] == "user" and fields[k]["value"] == v for k, v in params.items())


@pytest.mark.parametrize("question", [
    "Calculate roster: 12 workers or 14 workers, 3 people on duty every hour, 14 days",
    "Посчитай смены: 12 работников или 14 работников, 3 человека на смене каждый час, 14 дней",
])
def test_intake_does_not_choose_between_competing_values(question):
    assert intake_work_cycle(question, "en") == {"missing": ["workers"]}


def test_known_question_bindings_match_registry():
    questions = json.loads(Path("lab/registry/open_questions.json").read_text(encoding="utf-8"))["questions"]
    linked = {q["id"]: set(q["requirements"]) for q in questions
              if q["status"] == "UNRESOLVED" and "DKP-5-WORK-CYCLE-001" in q["documents"]}
    assert WORK_CYCLE_QUESTIONS == linked
