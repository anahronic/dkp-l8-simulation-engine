"""Control questions for the Keeper's retrieval (GPT КТ8 TZ §10, §14): recall of the expected fragments in the top k.

Usage: python -m keeper.eval_search CORPUS.jsonl [K]
Gold fragments were chosen from the section headings of the pinned corpus before running the search.  The no-answer
question has no gold: it is reported with its best score so the answer path can say "not in the sources".
"""
from __future__ import annotations

import json
import sys

from keeper.search import Index

QUESTIONS = [
    ("Сколько часов восстановления гарантирует рабочий день?", ["DKP-5-WORK-CYCLE-001#§5.1", "DKP-5-WORK-CYCLE-001#§5.3",
                                                                "DKP-5-WORK-CYCLE-001#§7"]),
    ("Можно ли сократить восстановление во время кризиса?", ["DKP-5-WORK-CYCLE-001#§10", "DKP-5-WORK-CYCLE-001#§7"]),
    ("What is the recovery invariant?", ["DKP-5-WORK-CYCLE-001#§7"]),
    ("Как устроен шестидневный рабочий цикл?", ["DKP-5-WORK-CYCLE-001#§4.1"]),
    ("Какие требования к сменам в круглосуточной службе?", ["DKP-5-WORK-CYCLE-001#§8.2", "DKP-5-WORK-CYCLE-001#§8.1"]),
    ("Что такое DTI-Day?", ["DKP-0-TIME-001#§3"]),
    ("Что говорит WORK-CYCLE §9?", ["DKP-5-WORK-CYCLE-001#§9"]),
    ("Можно ли унаследовать контроль над критической инфраструктурой оракулов?", ["CODE-OF-PLANETARY-SYNERGY#§A.6"]),
    ("Что такое период охлаждения при выходе из системы?", ["DKP-6-EXIT-001#§6"]),
    ("Какие основные принципы приватности?", ["DKP-7-PRIVACY-001#§5"]),
    ("Может ли ИИ определять нормы и какие у него полномочия?", ["DKP-7-AI-SUBJECT-001#§1"]),
    ("Что за находка F-001?", ["F-001#0"]),
    ("Что за вопрос автору Q-065?", ["Q-065#0"]),
    ("Что лаборатория умеет считать про круглосуточную службу и смены?", ["MODULE-work_cycle"]),
]
NO_ANSWER = "Какой рецепт борща у Хранителя?"


def main() -> None:
    idx = Index.load(sys.argv[1])
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    hit_any, recall, rows = 0, 0.0, []
    for q, gold in QUESTIONS:
        got = [f["fid"] for f in idx.search(q, k)]
        found = [g for g in gold if g in got]
        hit_any += bool(found)
        recall += len(found) / len(gold)
        rows.append({"q": q, "found": found, "missing": [g for g in gold if g not in got], "top": got[:3]})
    na = idx.search(NO_ANSWER, 1)
    print(json.dumps({"k": k, "questions": len(QUESTIONS), "hit_at_k": hit_any, "mean_recall": round(recall / len(QUESTIONS), 3),
                      "no_answer_best": [(f["fid"], f["score"]) for f in na], "rows": rows}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
