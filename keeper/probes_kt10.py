"""Offline KT10 gateway probes. python -m keeper.probes_kt10 CORPUS [--baseline]

--baseline loads the HEAD versions of gateway/guardrails in memory, without checkout
or modification. Both versions use the same supplied corpus and scripted transport.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types

import httpx
from fastapi.testclient import TestClient

from keeper.gateway import create_app, PREFIX
from keeper.guardrails import postcheck, report_summary
from lab.core.run import run_request
from tests.keeper.test_gateway import FakeOllama, message


def main():
    factory, check = create_app, postcheck
    if "--baseline" in sys.argv:
        old = sys.modules["keeper.guardrails"]
        for name in ("guardrails", "gateway"):
            module = types.ModuleType("keeper." + name)
            module.__file__ = str(Path("keeper", name + ".py").resolve())
            sys.modules[module.__name__] = module
            source = subprocess.check_output(["git", "show", "HEAD:keeper/" + name + ".py"]).decode("utf-8")
            exec(compile(source, module.__file__, "exec"), module.__dict__)
            if name == "guardrails":
                check = module.postcheck
            else:
                factory = module.create_app
        sys.modules["keeper.guardrails"] = old
    out = {"baseline": "--baseline" in sys.argv, "model": "scripted transport, no live Ollama", "probes": {}}
    with tempfile.TemporaryDirectory() as directory:
        for name, question, text in [
            ("code_request", "Please write Python code for WORK-CYCLE section 7 recovery invariant.",
             "```python\nprint(42)\n```\n[WORK-CYCLE §7]"),
            ("off_topic_with_page", "Расскажи анекдот про программиста.", "Вот анекдот про программиста."),
            ("empty_with_Q", "Explain Q-065 CRISIS entry without L3 escalation.", ""),
            ("uncited_with_Q", "Explain Q-065 CRISIS entry without L3 escalation.",
             "This statement has no citation from the model."),
        ]:
            model = FakeOllama([message(text)])
            app = factory({"KEEPER_CORPUS": str(Path(sys.argv[1]).resolve()), "KEEPER_LOG": directory,
                           "OLLAMA_TRANSPORT": httpx.MockTransport(model.handle), "RATE_BURST": 100})
            with TestClient(app) as client:
                response = client.post(PREFIX + "/ask", json={"question": question, "lang": "ru",
                                       "page": {"doc_id": "DKP-5-WORK-CYCLE-001"}})
            data = response.json()
            out["probes"][name] = {"http": response.status_code, "state": data.get("state"),
                                   "answer": data.get("answer"), "answer_kind": data.get("answer_kind"),
                                   "flags": [f["code"] for f in data.get("flags", [])],
                                   "citations": [c["cite"] for c in data.get("citations", [])],
                                   "notice_links": [c["cite"] for n in data.get("notices", []) for c in n["links"]],
                                   "model_requests": len(model.requests)}
        report = run_request({"schema": "dkp-lab-input/1", "module": "work_cycle", "variants": [
            {"name": "visitor", "input": {"workers": 12, "horizon_days": 14, "demand": [3] * 24}}]})
        summary, _ = report_summary(report)
        flags = []
        checked = check("дефицит продолжался 336 часов", [], flags, summary)
        out["probes"]["swapped_metric"] = {"observed_hours": 336, "deficit_hours": 210,
                                          "accepted": bool(checked), "flags": flags}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
