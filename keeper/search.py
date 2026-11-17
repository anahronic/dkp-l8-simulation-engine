"""Retrieval over the Keeper corpus (GPT КТ8 TZ §10): BM25 on the English text, heading and the Russian search key, plus
direct hits for ids named in the question (F-001, Q-065, module names, "WORK-CYCLE §7").  Pure Python, no vector store:
chosen on the control questions (keeper/eval_search.py) and on the server's memory.  The Russian key only matches; the
fragment returned is the canonical text."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional

WORD = re.compile(r"[^\W_]+(?:[.-][^\W_]+)*")          # any letters/digits (Hebrew, Arabic, ...), was Latin+Cyrillic only
STOP = set("""the a an of and or to in on for is are be by with as at from that this it its not no any all each
и в во на не что как это для по из к ко о об от с со у же ли или а но да при до за так то его ее её их можно ли ли
какой какая какие каков где кто когда чем""".split())
ID = re.compile(r"\b(F-\d{3}|Q-\d{3}|H-[A-Z]{2,4}-\d+)\b")
DOC_ID = re.compile(r"\bDKP-\d-[A-Z]+(?:-[A-Z]+)*-\d{3}(?:-PATCH)?\b")


def stem(w: str) -> str:
    """Prefix stem: enough for Russian inflection and English plurals in BM25 over a small corpus."""
    return w[:6] if len(w) > 6 else w


def tokens(text: str) -> List[str]:
    out = []
    for w in WORD.findall(text.lower().replace("ё", "е")):
        for part in re.split(r"[.-]", w) if not re.fullmatch(r"\d+(\.\d+)+", w) else [w]:
            if part and part not in STOP and (len(part) > 1 or part.isdigit()):
                out.append(stem(part))
    return out


class Index:
    def __init__(self, fragments: List[Dict[str, Any]], k1: float = 1.4, b: float = 0.7):
        self.frags = fragments
        self.k1, self.b = k1, b
        self.docs = []
        for f in fragments:
            bag = tokens(f["heading"]) * 2 + tokens(f["cite"]) + tokens(f["text"]) + tokens(f.get("search_ru", ""))
            self.docs.append(Counter(bag))
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lens) / max(1, len(self.lens))
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.names = {}
        for i, f in enumerate(fragments):
            doc = f["cite"].split(" ")[0].lower()
            if f["source_type"] in ("protocol", "code"):
                self.names.setdefault(doc, []).append(i)

    @classmethod
    def load(cls, jsonl_path: str) -> "Index":
        with open(jsonl_path, encoding="utf-8") as fh:
            return cls([json.loads(line) for line in fh if line.strip()])

    def search(self, query: str, k: int = 6, types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        q = tokens(query)
        scores = [0.0] * len(self.docs)
        for i, d in enumerate(self.docs):
            if types and self.frags[i]["source_type"] not in types:
                continue
            norm = self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg)
            scores[i] = sum(self.idf.get(t, 0) * d[t] * (self.k1 + 1) / (d[t] + norm) for t in set(q) if t in d)
        ql = query.lower()
        for m in ID.finditer(query.upper()):                    # named findings, questions, hypotheses
            for i, f in enumerate(self.frags):
                if f["document_id"] == m.group(1) or m.group(1) in f["text"][:400]:
                    scores[i] += 25 if f["document_id"] == m.group(1) else 5
        for m in DOC_ID.finditer(query.upper()):                # "DKP-0-ORACLE-001": the protocol's own text first
            for i, f in enumerate(self.frags):                  # (live 2026-11-17: author questions Q-010/Q-005 won)
                if f["document_id"] == m.group(0):
                    scores[i] += 12 if f["section"] in ("title", "§0", "§1") else 6
        for name, idx in self.names.items():                    # "WORK-CYCLE §7", "work-cycle 5.3"
            if name in ql:
                sec = re.search(re.escape(name) + r"\s*§?\s*([0-9A-Z]+(?:\.[0-9]+)*)", ql, re.I)
                for i in idx:
                    scores[i] += 3
                    if sec and self.frags[i]["section"].lower() == "§" + sec.group(1).lower():
                        scores[i] += 30
        for i, f in enumerate(self.frags):                      # module named by id
            if f["source_type"] == "module" and f["document_id"][7:].lower() in ql.replace(" ", "_"):
                scores[i] += 20
        best = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [dict(self.frags[i], score=round(scores[i], 3)) for i in best if scores[i] > 0]
