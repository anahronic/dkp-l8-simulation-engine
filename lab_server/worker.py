"""Run one spawned computation at a time; supervise its timeout and lease."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import time
import uuid

from lab_server import Settings, settings_from
from lab_server.queue import Queue


def _compute(request, stage, progress):
    from lab.api import run_package
    from lab.core.export import provenance

    doc, package = run_package(request, progress=progress, provenance=provenance() | {"runtime": "server"})
    stage = Path(stage)
    (stage / "report.json").write_text(json.dumps(doc, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    (stage / "package.zip").write_bytes(package)
    return {"result_id": doc["result_id"],
            "input_ids": {"request": doc["input_id"],
                          "variants": {n: v["input_id"] for n, v in doc["variants"].items()}}}


def _child(request, stage, sender):
    try:
        result = _compute(request, stage, lambda p, m: sender.send(("progress", (p, m))))
        sender.send(("done", result))
    except Exception as exc:
        sender.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        sender.close()


class _Stopped(Exception):
    pass


def process_one(db, store, worker_id, clock=None, *, inline=False, settings=None):
    """Return the claimed job's final/current row, or None. Inline is for serial tests only."""
    config = settings_from(settings)
    queue = Queue(db, store=store, now=clock or time.time, max_attempts=config.MAX_ATTEMPTS)
    queue.worker_heartbeat(worker_id)
    job = queue.claim(worker_id, config.LEASE_SECONDS)
    if job is None:
        return None
    job_id, lease_id = job["id"], job["lease_id"]
    stage = Path(store).resolve() / ".staging" / job_id / lease_id
    process = receiver = sender = None
    started = time.monotonic()

    def heartbeat(progress=0, message="running"):
        queue.worker_heartbeat(worker_id)
        if not queue.heartbeat(job_id, lease_id, progress, message):
            current = queue.get(job_id)
            if current and current["cancel_requested"]:
                queue.mark_cancelled(job_id, lease_id)
            raise _Stopped
        if time.monotonic() - started >= config.JOB_TIMEOUT:
            queue.fail(job_id, lease_id, "timeout")
            raise _Stopped

    try:
        stage.mkdir(parents=True, exist_ok=True)
        request = json.loads(job["request_json"])
        if inline:
            heartbeat()
            result = _compute(request, stage, heartbeat)
            heartbeat(1, "packaged")
        else:
            context = multiprocessing.get_context("spawn")
            receiver, sender = context.Pipe(duplex=False)
            process = context.Process(target=_child, args=(request, str(stage), sender))
            process.start()
            sender.close()
            result, error = None, None
            progress, message = 0, "running"
            pipe_open = True
            interval = min(config.POLL_SECONDS, config.LEASE_SECONDS / 3)

            def ready(timeout=0):
                nonlocal pipe_open
                if not pipe_open:
                    return False
                try:
                    return receiver.poll(timeout)
                except (EOFError, BrokenPipeError):
                    # Windows can signal a closed pipe from poll(), not only recv().
                    pipe_open = False
                    return False

            while True:
                heartbeat(progress, message)
                if ready(interval):
                    for _ in range(100):
                        try:
                            kind, payload = receiver.recv()
                        except (EOFError, BrokenPipeError):
                            pipe_open = False
                            break
                        if kind == "progress":
                            progress, message = payload
                        elif kind == "done":
                            result = payload
                        elif kind == "error":
                            error = payload
                        if not ready():
                            break
                elif not pipe_open:
                    process.join(interval)
                if not process.is_alive():
                    # Drain a final message sent just before exit on the next iteration.
                    if ready():
                        continue
                    process.join()
                    if error or result is None or process.exitcode != 0:
                        queue.fail(job_id, lease_id, error or f"child exited with code {process.exitcode}")
                        return queue.get(job_id)
                    heartbeat(1, "packaged")
                    break
        queue.complete(job_id, lease_id, result["result_id"], result["input_ids"],
                       stage / "report.json", stage / "package.zip")
    except _Stopped:
        pass
    except Exception as exc:
        queue.fail(job_id, lease_id, f"{type(exc).__name__}: {exc}")
    finally:
        if process is not None and process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(2)
            if process.is_alive():
                process.kill()
                process.join()
            process.close()
        for endpoint in (receiver, sender):
            if endpoint is not None:
                endpoint.close()
        # Only this attempt's directory: never remove another worker's files.
        if stage.exists():
            staging_root = Path(store).resolve() / ".staging"
            if not stage.resolve().is_relative_to(staging_root) or stage.resolve() == staging_root:
                raise ValueError("Refusing to remove an attempt outside staging")
            shutil.rmtree(stage)
        queue.worker_heartbeat(worker_id)
    return queue.get(job_id)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m lab_server.worker")
    parser.add_argument("--db", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings(JOB_TIMEOUT=float(os.environ.get("JOB_TIMEOUT", "120")))
    worker_id = uuid.uuid4().hex
    queue = Queue(args.db, store=args.store)
    loops = 0
    try:
        while True:
            job = process_one(args.db, args.store, worker_id, settings=settings)
            if loops % settings.PURGE_EVERY == 0:
                queue.purge(settings.RETENTION_SECONDS)
            loops += 1
            if args.once:
                break
            if job is None:
                time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
