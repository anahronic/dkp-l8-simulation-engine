"""Source hand-offs count as availability, without disguising them as model citations."""
import pytest

from keeper.eval_answers import CASES, check


@pytest.mark.parametrize("citations,found_sources,via", [
    ([{"cite": "F-001"}], [], "citation"),
    ([], [{"cite": "F-001"}], "found_source"),
    ([{"cite": "F-002"}], [{"cite": "F-001"}], "found_source"),
    ([{"cite": "F-001"}], [{"cite": "F-001"}], "citation"),
    ([], [{"cite": "F-002"}], None),
    ([], [], None),
])
def test_expected_source_match_reports_its_origin(citations, found_sources, via):
    case = next(c for c in CASES if c[0] == "finding")
    result = check(case, {"state": "answer", "answer": "Check [F-001]", "citations": citations,
                          "found_sources": found_sources})
    assert result["cite_via"] == via
    assert result["citation_ok"] == result["ok"] == (via is not None)


def test_no_source_requirement_does_not_claim_a_match():
    case = ("test", "test", "question", {"answer"}, [], [], [])
    result = check(case, {"state": "answer", "found_sources": [{"cite": "F-001"}]})
    assert result["citation_ok"] and result["ok"] and result["cite_via"] is None


def test_handoff_does_not_bypass_other_answer_checks():
    case = ("test", "test", "question", {"answer"}, ["F-001"], [r"required"], [r"forbidden"])
    result = check(case, {"state": "answer", "answer": "forbidden", "found_sources": [{"cite": "F-001"}]})
    assert result["citation_ok"] and result["cite_via"] == "found_source"
    assert not result["content_ok"] and not result["forbidden_absent"] and not result["ok"]
