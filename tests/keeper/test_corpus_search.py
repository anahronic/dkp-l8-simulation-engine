"""Keeper corpus and retrieval (GPT КТ8 TZ §10): pinned sources, fragment provenance, control questions."""
import json
import os
import re

import pytest

from keeper import corpus
from keeper.eval_search import QUESTIONS
from keeper.search import Index


RU = os.environ.get("KEEPER_RU_SOURCES")                  # unpublished translation: a search key only, not in the repo


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("corpus")
    man = corpus.build(str(out), RU)
    frags = [json.loads(line) for line in open(out / f"corpus-{man['version']}.jsonl", encoding="utf-8")]
    return man, frags


def test_every_fragment_carries_provenance(built):
    man, frags = built
    assert man["fragments"] == len(frags) and len({f["fid"] for f in frags}) == len(frags)
    for f in frags:
        assert f["sha256"] == corpus.sha(f["text"]) and f["source_type"] and f["cite"] and f["status"]
        assert ("world_commit" in f["revision"]) == (f["source_type"] in ("protocol", "code", "glossary"))
    norms = [f for f in frags if f["source_type"] in ("protocol", "code")]
    assert norms and all(f["url"].startswith(corpus.SITE + "/pages/protocols/") for f in norms)
    assert {f["status"] for f in frags if f["source_type"] == "module"} == {"lab model (not a norm)"}


def test_build_is_reproducible(built, tmp_path):
    assert corpus.build(str(tmp_path), RU)["version"] == built[0]["version"]


def test_control_questions(built):
    idx = Index(built[1])
    qs = [(q, g) for q, g in QUESTIONS if RU or not re.search("[а-яё]", q, re.I) or re.search(r"[A-Z]-\d{3}|§", q)]
    hits = sum(any(g in [f["fid"] for f in idx.search(q, 5)] for g in gold) for q, gold in qs)
    assert hits >= len(qs) - 1, (hits, len(qs))
    assert idx.search("WORK-CYCLE §7", 1)[0]["fid"] == "DKP-5-WORK-CYCLE-001#§7"
    assert idx.search("Q-065", 1)[0]["document_id"] == "Q-065"
