"""Private Keeper HTTP gateway. No lab execution, arbitrary tools or remote page reads."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, fields
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import unquote, urlsplit
import uuid

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException

from lab import api
from lab.modules import MODULES
from keeper.guardrails import flag, intake_work_cycle, postcheck, proposal, provisions, report_summary, safe_data
from keeper.ollama import Ollama
from keeper.search import Index

PREFIX = "/api/keeper/v1"
INSTRUCTIONS = Path(__file__).with_name("instructions") / "v1.md"
COMPUTATIONAL = re.compile(r"\b(?:calculat\w*|simulat\w*|compute\w*|run|workers?|roster|work_cycle)\b|"
                           r"рассчит|расч[её]т|посчита|смодел|запуск|работник|сотрудник", re.I)


@dataclass
class Settings:
    KEEPER_CORPUS: str | None = None
    KEEPER_OLLAMA: str = "http://127.0.0.1:11434"
    KEEPER_MODEL: str = "qwen3.5:2b"
    KEEPER_LAB_URL: str = "http://127.0.0.1:8000"
    KEEPER_LOG: str = "simulation/outputs/keeper"
    NO_SOURCE_SCORE: float = 9.0
    MAX_CONCURRENT: int = 1
    MAX_WAITING: int = 8
    MAX_BODY_BYTES: int = 16384
    RATE_PER_MINUTE: float = 6
    RATE_BURST: int = 6
    TOTAL_TIMEOUT: float = 150
    NUM_PREDICT: int = 700
    NUM_CTX: int = 8192                                  # = OLLAMA_CONTEXT_LENGTH on the server
    CORS_ORIGINS: tuple = ("null", "https://dikenocracy.com", "https://www.dikenocracy.com")
    OLLAMA_TRANSPORT: object = None
    LAB_TRANSPORT: object = None


def settings_from(value):
    config = Settings()
    for field in fields(config):
        name = field.name
        current = getattr(config, name)
        if name in os.environ and not name.endswith("TRANSPORT"):
            raw = os.environ[name]
            setattr(config, name, tuple(x.strip() for x in raw.split(",") if x.strip()) if isinstance(current, tuple)
                    else type(current)(raw) if current is not None else raw)
        if isinstance(value, dict) and name in value:
            setattr(config, name, value[name])
        elif value is not None and hasattr(value, name):
            setattr(config, name, getattr(value, name))
    if config.MAX_CONCURRENT < 1 or config.MAX_WAITING < 0 or config.TOTAL_TIMEOUT <= 0:
        raise ValueError("Invalid Keeper capacity settings")
    return config


class APIError(Exception):
    def __init__(self, status, code, message, headers=None):
        self.status, self.code, self.message, self.headers = status, code, message, headers

    def body(self):
        return {"error": {"code": self.code, "message": self.message}}


class TokenBucket:
    def __init__(self, rate, burst):
        self.rate, self.burst, self.buckets = rate / 60, burst, {}

    def take(self, client):
        now = time.monotonic()
        lifetime = max(60, self.burst / self.rate) if self.rate > 0 else math.inf
        self.buckets = {k: v for k, v in self.buckets.items() if now - v[1] < lifetime}
        tokens, stamp = self.buckets.get(client, (self.burst, now))
        tokens = min(self.burst, tokens + (now - stamp) * self.rate)
        self.buckets[client] = (tokens - 1 if tokens >= 1 else tokens, now)
        return tokens >= 1


class Capacity:
    def __init__(self, config):
        self.config, self.count, self.active = config, 0, 0
        self.semaphore = asyncio.Semaphore(config.MAX_CONCURRENT)

    def reserve(self):
        if self.count >= self.config.MAX_CONCURRENT + self.config.MAX_WAITING:
            raise APIError(503, "busy", "Keeper queue is full", {"Retry-After": "5"})
        self.count += 1


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PrivateLog:
    def __init__(self, directory):
        self.directory = Path(directory)

    def purge(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        cutoff = time.time() - 30 * 86400
        for path in self.directory.glob("keeper-*.jsonl"):
            kept = []
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    if json.loads(line)["time"] >= cutoff:
                        kept.append(line)
                except (ValueError, KeyError, TypeError):
                    continue
            if kept:
                path.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")
            else:
                path.unlink()

    def write(self, result, question, job_id):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.directory / (time.strftime("keeper-%Y-%m-%d", time.gmtime()) + ".jsonl")
        # Flag details and tool arguments can contain visitor text; retain only codes and names.
        row = {**result["provenance"], "time": time.time(), "question_sha256": sha(question),
               "answer_sha256": sha(result["answer"]), "flags": [f["code"] for f in result["flags"]],
               "job_id": job_id}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            file.write(dumps(row) + "\n")


def tool(name, description, properties, required=()):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": list(required),
                           "additionalProperties": False}}}


def input_schema(spec):
    kind = spec["type"]
    result = {"type": {"int": "integer", "bool": "boolean", "str": "string", "enum": "string",
                       "pair": "array", "list": "array"}.get(kind, kind)}
    if kind == "enum":
        result["enum"] = spec["values"]
    elif kind == "object":
        result.update(properties={k: input_schema(s) for k, s in spec["fields"].items()}, additionalProperties=False)
    elif kind in {"list", "pair"}:
        result["items"] = input_schema(spec["items"]) if kind == "list" else {"type": "number"}
    for source, target in (("min", "minimum"), ("max", "maximum"), ("min_items", "minItems"), ("max_items", "maxItems")):
        if source in spec:
            result[target] = spec[source]
    return result


TOOLS = [tool("search_sources", "Search the pinned archive; at most twice.",
              {"query": {"type": "string", "maxLength": 1000}}, ["query"]),
         tool("lab_catalog", "List lab modules, without running them.", {}),
         tool("propose_run", "Prepare work_cycle using only explicit visitor values; never execute.",
              {"module": {"type": "string", "enum": ["work_cycle"]},
               "params": {"type": "object", "additionalProperties": False,
                          "properties": {k: input_schema(s) for k, s in MODULES["work_cycle"].inputs.items()}}},
              ["module", "params"])]


def valid_page(url):
    if not isinstance(url, str) or not url or len(url) > 2048:
        return False
    decoded = unquote(url)
    if any(ord(c) <= 32 for c in decoded) or "\\" in decoded:
        return False
    try:
        parsed = urlsplit(decoded)
        if parsed.scheme or parsed.netloc:
            return (parsed.scheme == "https" and parsed.netloc == "dikenocracy.com"
                    and parsed.path.startswith("/"))
        return not decoded.startswith("//") and bool(parsed.path) and ":" not in parsed.path
    except ValueError:
        return False


def validate_body(raw, explain):
    def reject(value):
        raise ValueError("Non-finite JSON")

    try:
        body = json.loads(raw, parse_constant=reject)
    except (ValueError, UnicodeError, RecursionError):
        raise APIError(400, "bad_json", "Request body must be valid JSON")
    allowed = {"job_id", "token", "lang"} if explain else {"question", "lang", "page", "selection", "stream"}
    valid = isinstance(body, dict) and not body.keys() - allowed
    if valid:
        lang = body.get("lang", "en")
        valid = isinstance(lang, str) and re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})?", lang)
    if valid and explain:
        valid = (isinstance(body.get("job_id"), str) and re.fullmatch(r"[a-f0-9]{32}", body["job_id"])
                 and isinstance(body.get("token"), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", body["token"]))
    elif valid:
        question, selection, page = body.get("question"), body.get("selection", ""), body.get("page", {})
        valid = (isinstance(question, str) and 1 <= len(question) <= 1000 and bool(question.strip())
                 and isinstance(selection, str) and len(selection) <= 2000
                 and type(body.get("stream", False)) is bool and isinstance(page, dict)
                 and not page.keys() - {"url", "doc_id"})
        if valid and "url" in page:
            valid = valid_page(page["url"])
        if valid and "doc_id" in page:
            valid = isinstance(page["doc_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", page["doc_id"])
    if not valid:
        raise APIError(422, "invalid_input", "Invalid Keeper input")
    return {"lang": "en", **body}


def create_app(settings=None):
    config = settings_from(settings)
    raw = INSTRUCTIONS.read_bytes()
    instructions, version = raw.decode("utf-8"), "v1-" + hashlib.sha256(raw).hexdigest()[:8]
    index = Index.load(config.KEEPER_CORPUS) if config.KEEPER_CORPUS else Index([])
    corpus_version = hashlib.sha256(Path(config.KEEPER_CORPUS).read_bytes()).hexdigest()[:12] if config.KEEPER_CORPUS else None
    capacity, limiter, log = Capacity(config), TokenBucket(config.RATE_PER_MINUTE, config.RATE_BURST), PrivateLog(config.KEEPER_LOG)

    @asynccontextmanager
    async def lifespan(app):
        log.purge()
        yield

    async def guard(request: Request):
        if request.method != "POST":
            return
        if not limiter.take(request.client.host if request.client else "unknown"):
            raise APIError(429, "rate_limited", "POST rate limit exceeded", {"Retry-After": "10"})
        length = request.headers.get("content-length")
        if length is not None:
            try:
                length = int(length)
                if length < 0:
                    raise ValueError
            except ValueError:
                raise APIError(400, "bad_json", "Invalid Content-Length")
            if length > config.MAX_BODY_BYTES:
                raise APIError(413, "too_large", "Request body exceeds the byte limit")
        raw_body = bytearray()
        async for chunk in request.stream():
            if len(raw_body) + len(chunk) > config.MAX_BODY_BYTES:
                raise APIError(413, "too_large", "Request body exceeds the byte limit")
            raw_body.extend(chunk)
        request.state.raw_body = raw_body

    app = FastAPI(lifespan=lifespan, dependencies=[Depends(guard)])
    # The Keeper panel runs in a sandboxed iframe (opaque origin "null"); access is by bearer token, never cookies.
    app.add_middleware(CORSMiddleware, allow_origins=list(config.CORS_ORIGINS), allow_credentials=False,
                       allow_methods=["GET", "POST", "OPTIONS"],
                       allow_headers=["Content-Type", "Authorization", "X-Job-Token", "Idempotency-Key"],
                       expose_headers=["Retry-After", "Content-Disposition"], max_age=600)
    app.state.settings, app.state.capacity, app.state.index = config, capacity, index

    @app.exception_handler(APIError)
    async def error(request, exc):
        return JSONResponse(exc.body(), status_code=exc.status, headers=exc.headers)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return await error(request, APIError(exc.status_code, "not_found" if exc.status_code == 404
                                           else "method_not_allowed", "Route unavailable"))

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return await error(request, APIError(500, "internal_error", "Internal server error"))

    def ollama():
        return Ollama(config.KEEPER_OLLAMA, config.KEEPER_MODEL, config.OLLAMA_TRANSPORT, config.NUM_CTX)

    def remember(fragments, found):
        known = {f["fid"] for f in fragments}
        added = []
        for f in found:
            if f["fid"] not in known:
                fragment = {k: v for k, v in f.items() if k not in {"search_ru", "score"}}
                fragment["text"] = f["text"][:1500]
                fragments.append(fragment)
                added.append(fragment)
                known.add(f["fid"])
        return added

    def format_fragments(fragments):
        return "\n\n".join(f"[{f['cite']}] ({f['source_type']}, {f['status']})\n{f['text']}" for f in fragments)

    async def lab_report(body):
        async with httpx.AsyncClient(base_url=config.KEEPER_LAB_URL, transport=config.LAB_TRANSPORT,
                                     timeout=None, follow_redirects=False) as client:
            try:
                response = await client.get(f"/api/lab/v1/jobs/{body['job_id']}/report",
                                            headers={"Authorization": "Bearer " + body["token"]})
                if response.status_code in {401, 404, 409}:
                    code = {401: "missing_token", 404: "not_found", 409: "conflict"}[response.status_code]
                    raise APIError(response.status_code, code, "Lab report is unavailable")
                response.raise_for_status()
                return report_summary(response.json())
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                raise APIError(503, "lab_unavailable", "Lab report is unavailable")

    async def generate(body, explain, emit, result):
        fragments, summary = [], None
        question = body.get("question", "Explain the completed lab report.")
        if explain:
            summary, rids = await lab_report(body)
            remember(fragments, provisions(index, rids))
            result["result_id"] = json.loads(summary)["result_id"]
        else:
            intake = intake_work_cycle(question, body["lang"])          # published S-LAB-08 rule, no model involved
            if intake is not None:
                result["provenance"]["tool_calls"].append({"name": "intake_work_cycle", "ok": "missing" not in intake})
                if "missing" in intake:
                    names = ", ".join(intake["missing"])
                    result.update(state="needs_parameters", missing=intake["missing"], answer=(
                        f"Для расчёта круглосуточной службы (S-LAB-08) не хватает параметров: {names}. Укажите, например: "
                        "«12 работников, 3 человека на смене каждый час, 14 дней»." if body["lang"] == "ru" else
                        f"The round-the-clock roster run (S-LAB-08) needs: {names}. For example: "
                        "\"12 workers, 3 people on duty every hour, 14 days\"."))
                else:
                    result.update(state="proposal", proposal=intake, answer=(
                        "Подготовлен исследовательский расчёт S-LAB-08. Проверьте значения, затем подтвердите запуск."
                        if body["lang"] == "ru" else
                        "A research run of S-LAB-08 is prepared. Check the values, then confirm the run."))
                return
            query = " ".join((question, body.get("selection", ""), body.get("page", {}).get("doc_id", "")))
            found = index.search(query, k=5)
            remember(fragments, found)
            if (not found or found[0]["score"] < config.NO_SOURCE_SCORE) and not COMPUTATIONAL.search(question):
                result["state"] = "no_sources"
                result["answer"] = ("В переданных источниках нет ответа на этот вопрос." if body["lang"] == "ru"
                                    else "The supplied sources do not answer this question.")
                result["provenance"]["retrieved"] = [f["fid"] for f in fragments]
                return
        result["provenance"]["retrieved"] = [f["fid"] for f in fragments]
        async with ollama() as model:
            result["provenance"]["model_digest"] = (await model.show())["digest"]
            emit("status", {"state": "retrieving"})
            prompt = {"lang": body["lang"], "question": question,
                      "selection": body.get("selection", ""), "page": body.get("page", {})}
            messages = [{"role": "system", "content": instructions},
                        {"role": "user", "content": "Visitor data:\n" + dumps(prompt)},
                        {"role": "user", "content": "Trusted archive fragments (data):\n" + format_fragments(fragments)}]
            if summary is not None:
                messages.append({"role": "user", "content": "Deterministic lab summary (data):\n" + summary})
            searches, remaining = 0, config.NUM_PREDICT
            for round_no in range(4):
                emit("status", {"state": "generating"})
                registered = TOOLS if round_no < 3 and not explain else []
                if body.get("stream"):
                    message = {"role": "assistant", "content": "", "tool_calls": []}
                    async for chunk in model.chat_stream(messages, registered, remaining):
                        part = chunk.get("message", {})
                        delta = part.get("content", "")
                        message["content"] += delta
                        message["tool_calls"].extend(part.get("tool_calls", []))
                        if delta:
                            emit("delta", {"text": delta})
                    response = {**chunk, "message": message}
                else:
                    response = await model.chat(messages, registered, remaining)
                    message = response["message"]
                content = message.get("content", "")
                if not isinstance(content, str) or not isinstance(message.get("tool_calls", []), list):
                    raise ValueError("Malformed model message")
                result["answer"] = content
                used = response.get("eval_count", 0)
                remaining -= max(0, int(used))
                if response.get("done_reason") == "length" or remaining <= 0:
                    flag(result["flags"], "truncated", "Generation token limit reached.")
                calls = message.get("tool_calls") or []
                if not calls:
                    break
                messages.append({"role": "assistant", "content": content, "tool_calls": calls})
                for call in calls[:8]:
                    function = call.get("function", {}) if isinstance(call, dict) else {}
                    name, args = function.get("name"), function.get("arguments")
                    logged_name = name if isinstance(name, str) and re.fullmatch(r"[a-z_]{1,40}", name) else "unregistered"
                    record = {"name": logged_name, "ok": False}
                    result["provenance"]["tool_calls"].append(record)
                    output = {"error": "Tool or arguments rejected"}
                    try:
                        if round_no >= 3 or explain or not isinstance(args, dict) or not safe_data(args):
                            raise ValueError("Tool denied")
                        if name == "search_sources" and set(args) == {"query"}:
                            if searches >= 2 or not isinstance(args["query"], str) or not args["query"].strip():
                                raise ValueError("Search limit or query")
                            searches += 1
                            output = {"fragments": format_fragments(remember(fragments, index.search(args["query"], k=5)))}
                            result["provenance"]["retrieved"] = [f["fid"] for f in fragments]
                        elif name == "lab_catalog" and not args:
                            output = [{"id": m["id"], "title": m["title"].get(body["lang"], m["title"].get("en", "")),
                                       "summary": m["summary"].get(body["lang"], m["summary"].get("en", ""))[:240]}
                                      for m in api.catalog_payload()["modules"]]
                        elif name == "propose_run" and set(args) == {"module", "params"}:
                            output = proposal(args["module"], args["params"], question, body["lang"])
                            result.pop("missing", None)
                            if "missing" in output:
                                result.update(state="needs_parameters", proposal=None, missing=output["missing"])
                            else:
                                result.update(state="proposal", proposal=output)
                        else:
                            raise ValueError("Unknown tool or arguments")
                        record["ok"] = True
                    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
                        flag(result["flags"], "tool_rejected", "Tool name, arguments or budget outside the contract.")
                    messages.append({"role": "tool", "tool_name": logged_name, "content": dumps(output)})
                if len(calls) > 8 or round_no >= 3 or remaining <= 0:
                    flag(result["flags"], "truncated", "Tool or generation limit reached.")
                    if len(calls) > 8:
                        flag(result["flags"], "tool_rejected", "Too many tool calls.")
                    break
        emit("status", {"state": "checking"})
        if result["state"] == "needs_parameters":
            result["answer"] = (("Уточните параметры: " if body["lang"] == "ru" else "Please supply parameters: ")
                                + ", ".join(result["missing"]))
        result["answer"] = postcheck(result["answer"], fragments, result["flags"], summary)
        # An open author question among the sources is stated by the server, not left to the model (AI-SUBJECT §§1-2):
        # the lab does not choose a reading and neither does the Keeper.
        open_qs = [f for f in fragments if f["source_type"] == "question" and f["status"] == "UNRESOLVED"
                   and f["fid"].endswith("#0")]
        if open_qs and result["state"] == "answer" and not explain:
            ru = body["lang"] == "ru"
            result["answer"] = result["answer"].rstrip() + "\n\n" + (
                "Открытый вопрос автору — прочтение не выбрано ни лабораторией, ни Хранителем, решение принадлежит автору: "
                if ru else "Open question to the author — neither the lab nor the Keeper chooses a reading; the author decides: ") + \
                "; ".join(f"[{f['cite']}] {f['heading']}" for f in open_qs[:2])
            flag(result["flags"], "open_author_question", ", ".join(f["cite"] for f in open_qs[:2]))
        # citations = the trusted fragments the answer actually cites, in order of first use; all retrieved stay in provenance
        used = [m.group(1) for m in re.finditer(r"\[([^\[\]\n]+)\]", result["answer"])]
        by_cite = {}
        for f in fragments:
            by_cite.setdefault(f["cite"], f)
        result["citations"] = [{k: by_cite[c][k] for k in ("cite", "fid", "url", "heading", "source_type", "status", "revision")}
                               for c in dict.fromkeys(used) if c in by_cite]
        result["provenance"]["retrieved"] = [f["fid"] for f in fragments]
        if result["state"] == "answer" and not result["answer"].strip():      # the model produced nothing usable
            flag(result["flags"], "empty_model_answer", "The model gave no answer; nothing is asserted.")
            result["answer"] = ("Хранитель не смог составить ответ по найденным источникам. Откройте найденные разделы "
                                "или переформулируйте вопрос." if body["lang"] == "ru" else
                                "The Keeper could not compose an answer from the sources found. Open the sections or rephrase.")
        elif result["state"] == "answer" and not result["citations"] and not explain:
            flag(result["flags"], "uncited_answer", "No statement of this answer is tied to a source.")

    async def dispatch(request, explain=False):
        body = validate_body(request.state.raw_body, explain)
        capacity.reserve()
        events = asyncio.Queue()
        result = {"state": "answer", "answer": "", "citations": [], "flags": [], "proposal": None,
                  "provenance": {"request_id": uuid.uuid4().hex, "model": config.KEEPER_MODEL,
                                 "model_digest": None, "instructions_version": version,
                                 "corpus_version": corpus_version, "retrieved": [], "tool_calls": []}}

        released = []

        def release_reservation(_=None):                # once, inside the task or when it is cancelled before it ran
            if not released:
                released.append(True)
                capacity.count -= 1

        def emit(event, data):
            if body.get("stream"):
                events.put_nowait((event, data))

        async def work():
            try:
                async with asyncio.timeout(config.TOTAL_TIMEOUT):
                    async with capacity.semaphore:
                        capacity.active += 1
                        try:
                            await generate(body, explain, emit, result)
                        finally:
                            capacity.active -= 1
                emit("final", result)
                return result
            except TimeoutError:
                raise APIError(504, "timeout", "Keeper request timed out")
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                raise APIError(503, "model_unavailable", "Model is unavailable")
            finally:
                release_reservation()
                log.write(result, body.get("question", ""), body.get("job_id"))

        task = asyncio.create_task(work())
        task.add_done_callback(release_reservation)

        async def stop():
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError, APIError):
                await task

        async def next_event():
            while events.empty():
                if task.done():
                    await task
                    return None
                if await request.is_disconnected():
                    raise asyncio.CancelledError
                await asyncio.sleep(0.02)
            return events.get_nowait()

        if body.get("stream"):
            try:
                first = await next_event()  # Preflight failures still have an HTTP error status.
            except BaseException:
                await stop()
                raise

            async def stream():
                event = first
                try:
                    while event is not None:
                        yield f"event: {event[0]}\ndata: {dumps(event[1])}\n\n"
                        if event[0] == "final":
                            break
                        event = await next_event()
                except APIError as exc:
                    yield f"event: error\ndata: {dumps(exc.body())}\n\n"
                finally:
                    await stop()

            return StreamingResponse(stream(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        try:
            while not task.done():
                if await request.is_disconnected():
                    raise asyncio.CancelledError
                await asyncio.wait({task}, timeout=0.05)
            return await task
        finally:
            await stop()

    @app.post(PREFIX + "/ask")
    async def ask(request: Request):
        return await dispatch(request)

    @app.post(PREFIX + "/explain")
    async def explain(request: Request):
        return await dispatch(request, True)

    @app.get(PREFIX + "/health")
    async def health():
        digest, loaded = None, False
        try:
            async with asyncio.timeout(min(5, config.TOTAL_TIMEOUT)):
                async with ollama() as model:
                    digest = await model.digest()
                    running = await model.ps()
                    names = {config.KEEPER_MODEL, config.KEEPER_MODEL + ":latest"}
                    loaded = any(m.get("name", m.get("model")) in names for m in running.get("models", []))
        except (TimeoutError, httpx.HTTPError, ValueError, TypeError):
            loaded = False
        # ok = the model is installed and Ollama answers; "loaded" only says whether it is in memory now (keep-alive)
        return {"ok": bool(digest and index.frags), "model": {"name": config.KEEPER_MODEL, "digest": digest, "loaded": loaded},
                "corpus_version": corpus_version, "instructions_version": version,
                "busy": capacity.active, "queue_limit": config.MAX_WAITING}

    return app


app = create_app()
