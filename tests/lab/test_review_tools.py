"""A6 review tooling: decisions are explicit, validated and append-only; the registry is never modified."""
import json

import pytest

from lab.tools import review_record


def test_record_validates_and_appends(tmp_path, monkeypatch):
    log = tmp_path / "author_reviews.jsonl"
    monkeypatch.setattr(review_record, "LOG", log)
    review_record.main(["WORKCYCLE-2-01", "confirmed", "--reviewer", "test-reviewer", "--note", "synthetic"])
    review_record.main(["Q-001", "deferred", "--reviewer", "test-reviewer"])
    entries = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    assert [e["decision"] for e in entries] == ["confirmed", "deferred"]
    assert entries[0]["kind"] == "provision" and len(entries[0]["item_sha256"]) == 64


@pytest.mark.parametrize("args", [["NOPE-1", "confirmed"], ["WORKCYCLE-2-01", "answered"], ["Q-001", "confirmed"],
                                  ["WORKCYCLE-2-01", "confirmed", "--reviewer", " "]])
def test_record_refuses_invalid(tmp_path, monkeypatch, args):
    monkeypatch.setattr(review_record, "LOG", tmp_path / "log.jsonl")
    if "--reviewer" not in args:
        args = args + ["--reviewer", "r"]
    with pytest.raises(SystemExit):
        review_record.main(args)
    assert not (tmp_path / "log.jsonl").exists()


def test_review_workbook_has_protocol_dependency_and_criticality_controls(tmp_path):
    from lab.tools import review_queue
    n, counts = review_queue.build(tmp_path / "index.html")
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert n == sum(counts.values()) > 1700
    assert all(f"id={x}" in page for x in ("d", "p", "o")) and "criticality, high first" in page
    assert "data-crit=" in page and "data-deps=" in page and "DKP-8-SIMULATION-001" in page
