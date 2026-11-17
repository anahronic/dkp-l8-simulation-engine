"""Second round of Keeper fixes from the live acceptance run of 2026-11-17 (KEEPER_LIVE_ACCEPTANCE_2026-11-17.md)."""
import pytest

pytest.importorskip("fastapi")
from keeper.gateway import INSTRUCTIONS
from keeper.policy import instruction_echo, shingles
from tests.keeper.test_gateway import setup, corpus_path, ask, message  # noqa: F401


def test_protocol_id_retrieves_the_protocol_itself(setup):
    client, fake, app = setup()
    found = app.state.index.search("What is DKP-0-ORACLE-001?", k=5)
    assert found[0]["document_id"] == "DKP-0-ORACLE-001"


def test_instruction_echo_is_detected_and_not_published(setup):
    text = INSTRUCTIONS.read_text(encoding="utf-8")
    passage = text[text.index("Вопрос"):text.index("Вопрос") + 160]
    assert instruction_echo("Some words. " + passage, shingles(text))
    assert not instruction_echo("Recovery is mandatory [WORK-CYCLE §7].", shingles(text))
    client, fake, app = setup([message(passage)])
    data = ask(client, question="Explain WORK-CYCLE §7 recovery invariant").json()
    assert passage[:60] not in data["answer"]
    assert any(f["code"] == "instruction_echo" for f in data["flags"])
    assert any(f["code"] == "empty_model_answer" for f in data["flags"])


def test_hebrew_question_is_translated_into_an_english_query_first(setup):
    client, fake, app = setup([message("Dikenocracy justice function"), message("תשובה [JUSTICE §1].")])
    data = ask(client, question="הסבר מהי דיקנוקרטיה", lang="en").json()
    assert fake.chats[0]["tools"] == [] and fake.chats[0]["options"]["num_predict"] <= 40
    assert {"name": "query_translation", "ok": True} in data["provenance"]["tool_calls"]
    assert any("Answer language (lang): Hebrew" in m["content"] for m in fake.chats[1]["messages"])
    assert fake.chats[1]["tools"] == []          # one answer round after the translation
    assert any(fid.startswith("DKP-1-JUSTICE-001") for fid in data["provenance"]["retrieved"])


def test_translation_failure_does_not_break_the_answer(setup):
    client, fake, app = setup([message(""), message("תשובה.")])
    data = ask(client, question="מהי דיקנוקרטיה?", lang="he").json()
    assert data["state"] in ("answer", "no_answer") and {"name": "query_translation", "ok": False} in data["provenance"]["tool_calls"]


def test_invented_numbers_are_removed(setup):
    """Live 2026-11-17: 'The boiling point of mercury is 254.73 K [LAB MODEL_GAPS 12].'"""
    client, fake, app = setup([message("The boiling point is 254.73 K [WORK-CYCLE §7]. Recovery is mandatory [WORK-CYCLE §7].")])
    data = ask(client, question="Explain WORK-CYCLE §7 recovery invariant").json()
    assert "254.73" not in data["answer"] and "Recovery is mandatory" in data["answer"]
    assert any(f["code"] == "unsupported_number" for f in data["flags"])


def test_numbers_from_the_sources_stay():
    from keeper.guardrails import strip_unsupported_numbers
    flags = []
    out = strip_unsupported_numbers("1. A year has 360 days. 2. Rest for 11 hours.", "DTI-Year has 360 DTI-Days; rest 11 hours", flags)
    assert "360" in out and "11 hours" in out and not flags


def test_weak_russian_retrieval_gets_an_english_query(setup):
    """Live 2026-11-17 (round 4): 'Что такое Дикенократия?' retrieved ERROR/DEFENSE sections only."""
    client, fake, app = setup([message("What is Dikenocracy"), message("Ответ [JUSTICE §1].")])
    real = app.state.index.search
    app.state.index.search = lambda q, **kw: [dict(f, score=1.0) for f in real(q, **kw)] if "What is" not in q else real(q, **kw)
    data = ask(client, question="Что такое Дикенократия?", lang="en").json()
    assert {"name": "query_translation", "ok": True} in data["provenance"]["tool_calls"]
    assert any("Answer language (lang): Russian" in m["content"] for m in fake.chats[1]["messages"])


def test_hebrew_question_about_the_framework_never_reaches_the_model_without_sources(setup):
    client, fake, app = setup([message("garbage"), message("תשובה.")])
    real = app.state.index.search
    app.state.index.search = lambda q, **kw: real(q, **kw) if "overview" in q else []
    data = ask(client, question="הסבר מהי דיקנוקרטיה", lang="en").json()
    assert data["provenance"]["retrieved"], "overview sources were not supplied"
