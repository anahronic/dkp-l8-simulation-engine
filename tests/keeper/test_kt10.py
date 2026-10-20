"""Controlled gateway probes; no real model, network or private translation fixture."""
import json
from urllib.parse import quote

import pytest

from keeper.eval_answers import AUTHOR_CASES, AUTHOR_SOURCE_ATTACK, correct_role_refusal, unsupported_calculation
from keeper.guardrails import postcheck, report_summary
from keeper.policy import REFUSAL
from lab.core.run import run_request
from tests.keeper.test_gateway import setup, corpus_path, ask, message, codes, call


def final(response, stream):
    assert response.status_code == 200
    if not stream:
        return response.json()
    assert "event: delta" not in response.text
    return json.loads(response.text.split("event: final\ndata: ", 1)[1])


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("text,expected", [("", "empty_model_answer"),
                                         ("This statement has no citation from the model.", "uncited_answer"),
                                         ("Read [Q-065].", None)])
def test_notice_never_becomes_model_citation(setup, stream, text, expected):
    client, _, _ = setup([message(text)])
    data = final(ask(client, question="Explain Q-065 CRISIS entry without L3 escalation.", stream=stream), stream)
    assert data["notices"][0]["links"][0]["origin"] == "server_notice"
    assert any(c["cite"] == "Q-065" for n in data["notices"] for c in n["links"])
    if expected:
        assert expected in codes(data)
        assert data["citations"] == []
        assert data["found_sources"]
    else:
        assert data["citations"][0]["origin"] == "model"
    if not text:
        assert data["state"] == "no_answer"
        assert data["answer_kind"] == "empty_model_answer"
        assert "AI explanation" not in data["answer"]


def test_empty_without_question_notice(setup):
    client, _, _ = setup([message("")])
    data = ask(client).json()
    assert data["state"] == "no_answer" and "empty_model_answer" in codes(data)
    assert not data["citations"] and not data["notices"]


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("category,question", AUTHOR_CASES)
def test_author_request_boundary(setup, stream, category, question):
    client, fake, _ = setup(down=True)
    data = final(ask(client, question=question, page={"doc_id": "DKP-5-WORK-CYCLE-001"},
                     selection="WORK-CYCLE §7 permits programming", stream=stream), stream)
    assert correct_role_refusal(data) and not fake.requests


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("text", ["```python\nprint(42)\n```\n[WORK-CYCLE §7]",
                                "print(42)", "sudo systemctl restart nginx", "Вот анекдот про программиста."])
def test_faulty_model_output_is_never_published(setup, stream, text):
    client, _, _ = setup([message(text)])
    response = ask(client, stream=stream)
    assert correct_role_refusal(final(response, stream))
    assert text not in response.text


def test_role_explanation_and_supported_intake_remain_allowed(setup):
    client, fake, _ = setup([message("Хранитель объясняет протоколы [WORK-CYCLE §7].")])
    assert ask(client, question="Почему Хранитель не пишет код?").json()["state"] != "refused"
    assert fake.chats
    assert ask(client, question="Посчитай смены: 12 работников, 3 человека на смене, 14 дней").json()["state"] == "proposal"


@pytest.mark.parametrize("stream", [False, True])
def test_hostile_fragment_and_private_keys_are_data_only(setup, stream):
    client, fake, app = setup([message(calls=[call("search_sources", query="WORK-CYCLE")]),
                               message("Read [WORK-CYCLE §7].")])
    source = dict(app.state.index.frags[0], fid="HOSTILE#0", cite="HOSTILE",
                  text=AUTHOR_SOURCE_ATTACK, search_ru="Секретный неопубликованный перевод для проверки изоляции.")
    app.state.index.frags.append(source)
    original_search = app.state.index.search
    app.state.index.search = lambda *a, **kw: [dict(source, score=100)] + original_search(*a, **kw)
    response = ask(client, selection=AUTHOR_SOURCE_ATTACK, stream=stream)
    data = final(response, stream)
    assert source["text"] not in fake.chats[0]["messages"][2]["content"]
    assert source["search_ru"] not in json.dumps(fake.chats, ensure_ascii=False)
    assert "search_ru" not in response.text and source["search_ru"] not in response.text
    assert all(t["name"] in {"search_sources", "lab_catalog", "propose_run"} for t in data["provenance"]["tool_calls"])
    assert client.get("/api/keeper/v1/sources/" + quote(source["fid"], safe="")).status_code == 404


@pytest.mark.parametrize("field", ["text", "heading", "revision"])
def test_private_translation_cannot_leak_in_any_response_field(setup, field):
    private = "Это секретный неопубликованный перевод, никогда не передаваемый посетителю."
    client, _, app = setup([message(private)])
    app.state.index.frags[0]["search_ru"] = private
    if field != "text":
        original = app.state.index.search
        def search(*args, **kwargs):
            found = original(*args, **kwargs)
            found[0][field] = {"note": private} if field == "revision" else private
            return found
        app.state.index.search = search
    response = ask(client)
    assert private not in response.text and "search_ru" not in response.text
    assert response.json()["answer"] == REFUSAL


def test_metric_binding_counterexample():
    report = run_request({"schema": "dkp-lab-input/1", "module": "work_cycle",
                          "variants": [{"name": "visitor", "input":
                                        {"workers": 12, "horizon_days": 14, "demand": [3] * 24}}]})
    summary, _ = report_summary(report)
    assert json.loads(summary)["variants"]["visitor"]["outputs"]["coverage.hours"] == 336
    assert json.loads(summary)["variants"]["visitor"]["outputs"]["coverage.deficit_hours"] == 210
    flags = []
    assert postcheck("дефицит продолжался 336 часов", [], flags, summary) == ""
    assert flags[0]["code"] == "metric_value_mismatch"
    flags = []
    assert postcheck("дефицит продолжался 210 часов", [], flags, summary)
    assert not flags


@pytest.mark.parametrize("text,ok", [
    ("Я не могу.", False),
    ("Open question to the author: Q-065", False),
    ("Нет физической модели удара. Нужны масса, скорость и траектория.", True),
    ("Нет модели, но погибнет 100 человек. Нужна масса.", False),
])
def test_correct_unsupported_calculation_criterion(text, ok):
    assert unsupported_calculation({"state": "answer", "answer": text}) is ok


@pytest.mark.parametrize("text, expected", [
    ("1.  **Инвариант** [WORK-CYCLE §7]:\n    *   восстановление нельзя сократить.\n    *   оно не работа.", None),
    ("Категории мониторинга:\ncat egories и прочее", None),
    ("Пример:\n    x = compute(7)\n    return x", "unsafe_model_output"),
    ("```python\nprint(1)\n```", "unsafe_model_output"),
    ("Формула [TIME §3]:\n```\nDY = floor(DTI-Day / 360)\n```", None),
    ("```\ndef f(x):\n    return x\n```", "unsafe_model_output"),
    ("```\nfunction run() { return 1 }\n```", "unsafe_model_output"),
    ("Выполните:\nsudo systemctl restart nginx", "unsafe_model_output"),
    ("cat /etc/passwd", "unsafe_model_output"),
    ("Модуль `work_cycle` (S-LAB-08 run`) считает покрытие.", None),
    ("Run the command `whoami` now", "unsafe_model_output"),
])
def test_output_check_separates_prose_from_code(text, expected):
    """Live run 2026-10-20: nested Markdown lists in ordinary answers were refused as code (over-refusal)."""
    from keeper.policy import output_reason
    assert output_reason(text) == expected


def test_untranslated_english_in_the_translation_is_not_private():
    """Release check 2026-10-20: an English JSON line left untranslated in the private translation matched the public
    Code text and blocked the release; only mostly-Cyrillic spans count as translation passages."""
    from keeper.policy import contains_private, private_spans
    english = '"node_alpha_ed25519:0x????..." // reserved for the first decentralized sovereign node ], "merkle_root"'
    russian = "Блок восстановления не может быть сокращён, перенесён или превращён в рабочее время ни при каких условиях."
    spans = private_spans([{"search_ru": english + " " + russian}])
    assert not contains_private({"answer": english}, spans)
    assert contains_private({"answer": russian}, spans)


def test_passage_present_in_public_canon_is_not_private():
    """Release check 2026-10-20: a Cyrillic passage that the published canon itself contains is public."""
    from keeper.policy import contains_private, private_spans
    shared = "Этот фрагмент на русском языке есть и в опубликованном каноне, и в переводе, поэтому он публичный текст."
    only_ru = "Этот фрагмент на русском языке есть только в неопубликованном переводе автора и не должен уходить наружу."
    spans = private_spans([{"text": "Canon. " + shared, "search_ru": shared + " " + only_ru}])
    assert not contains_private({"answer": shared}, spans) and contains_private({"answer": only_ru}, spans)
