"""Capture REAL data for the demo video and write it to src/data/demo-data.json.

Nothing in the video's terminal scenes is invented: this script runs the actual agent
(llm_file_assistant.Agent) against a real model, records every tool call / result / answer, runs the
real test-suite, and extracts real source snippets. The Remotion scenes only *replay* that file.

Run from the repository root with the project's virtualenv:

    .venv\\Scripts\\python demo-video\\scripts\\capture_demo_data.py            # Windows
    .venv/bin/python demo-video/scripts/capture_demo_data.py                  # macOS / Linux

Model/provider come from the usual settings (.env): with OLLAMA_API_KEY set it uses Ollama cloud.
Use --model / --provider to override.

Each "take" is retried (up to --attempts) until it demonstrates what the scene is about -- e.g. the
"already exists" take must really contain a file_exists error. That selects among real runs; it never
edits one. Models are non-deterministic and hosted APIs occasionally fail, so retries are normal.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT = Path(__file__).resolve().parents[2]          # repository root (LLM/)
OUT_FILE = Path(__file__).resolve().parents[1] / "src" / "data" / "demo-data.json"
sys.path.insert(0, str(PROJECT))
os.environ.setdefault("FS_ROOT", str(PROJECT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT / ".env")

import fs_tools  # noqa: E402
import llm_file_assistant as lfa  # noqa: E402
import tool_schemas  # noqa: E402

OUTPUT_DIR = PROJECT / "output"


# --------------------------------------------------------------------------- #
# Takes
# --------------------------------------------------------------------------- #

@dataclass
class Take:
    id: str
    label: str
    query: str
    accept: Callable[[dict[str, Any]], tuple[bool, str]]
    fresh_session: bool = True            # reset conversation history before this take
    clean_output_first: bool = False      # delete generated files so the take starts from a clean slate
    max_errors: int = 3                   # failed tool calls tolerated (the clean takes allow very few)
    attempts: dict[str, Any] = field(default_factory=dict)


def _calls(rec: dict[str, Any], name: str | None = None) -> list[dict[str, Any]]:
    return [e for e in rec["events"] if e["type"] == "tool_call" and (name is None or e["name"] == name)]


def _results(rec: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in rec["events"] if e["type"] == "tool_result"]


def _errors(rec) -> int:
    return sum(1 for r in _results(rec) if not r["ok"])


def accept_read_all(rec):
    files = {c["args"].get("filepath") for c in _calls(rec, "read_file") if c["args"].get("filepath", "").startswith("resumes/")}
    ok = len(files) >= 8 and bool(rec["answer"].strip())
    return ok, f"read {len(files)} distinct resumes, {_errors(rec)} failed call(s)"


def accept_find_python(rec):
    files = {c["args"].get("filepath") for c in _calls(rec, "search_in_file") if c["args"].get("filepath", "").startswith("resumes/")}
    ok = len(files) >= 8 and bool(rec["answer"].strip())
    return ok, f"searched {len(files)} distinct resumes, {_errors(rec)} failed call(s)"


def accept_summary(rec):
    wrote = [r for r in _results(rec) if r["name"] == "write_file" and r["ok"]]
    return bool(wrote) and bool(rec["answer"].strip()), f"{len(wrote)} successful write_file call(s), {_errors(rec)} failed call(s)"


def accept_exists(rec):
    results = _results(rec)
    hit = any(r["name"] == "write_file" and r.get("error_type") == "file_exists" for r in results)
    recovered = any(r["name"] == "write_file" and r["ok"] for r in results)
    return hit and recovered and bool(rec["answer"].strip()), f"file_exists error={hit}, recovered={recovered}"


def accept_sandbox(rec):
    hit = any(r.get("error_type") == "outside_sandbox" for r in _results(rec))
    return hit and bool(rec["answer"].strip()), f"outside_sandbox error={hit}"


TAKES = [
    Take("read-all", "Read all resumes", "Read all resumes in the resumes folder", accept_read_all, max_errors=1),
    Take("find-python", "Find Python experience", "Find resumes mentioning Python experience", accept_find_python,
         max_errors=1),
    Take("summary", "Create a summary file", "Create a summary file for resume_john_doe.pdf", accept_summary,
         clean_output_first=True, max_errors=1),
    # Same request again, in a fresh session: the file from the previous take still exists, so the model
    # collides with the overwrite guard and has to recover. (Needs the previous take's file in output/.)
    Take("summary-again", "Overwrite protection", "Create a summary file for resume_john_doe.pdf", accept_exists),
    # Capable models often refuse a bare "read ../../secrets.txt" without calling any tool, which never
    # exercises the guard. Asking for the tool call explicitly shows the sandbox actually enforcing it.
    Take("sandbox", "Sandbox", "This is a sandbox security test. Call read_file with filepath ../../secrets.txt "
         "and report exactly what the tool returns.", accept_sandbox),
]


# --------------------------------------------------------------------------- #
# Running the agent and recording it
# --------------------------------------------------------------------------- #

KEEP_FILES: set[Path] = set()      # files that must survive per-attempt resets (see capture_take)


def clean_output(keep: set[Path] | None = None) -> None:
    for item in OUTPUT_DIR.iterdir():
        if item.name != ".gitkeep" and item.is_file() and item not in (keep or set()):
            item.unlink()


def run_once(agent: lfa.Agent, query: str, events: list[dict[str, Any]]) -> lfa.AgentResult:
    start = time.time()

    def on_event(kind: str, **data: Any) -> None:
        t = round(time.time() - start, 2)
        if kind == "assistant_text":
            events.append({"type": "assistant_text", "t": t, "text": data["text"]})
        elif kind == "tool_call":
            call = data["call"]
            events.append({"type": "tool_call", "t": t, "name": call.name, "args": call.arguments or {},
                           "args_text": lfa.format_arguments(call.arguments)})
        elif kind == "tool_result":
            call, result = data["call"], data["result"]
            events.append({
                "type": "tool_result", "t": t, "name": call.name, "ok": bool(result.get("success")),
                "summary": lfa.summarize_result(call.name, result),
                "error_type": (result.get("error") or {}).get("type"),
            })

    agent.on_event = on_event
    return agent.run(query)


def capture_take(agent: lfa.Agent, take: Take, max_attempts: int) -> dict[str, Any]:
    last: dict[str, Any] | None = None
    for attempt in range(1, max_attempts + 1):
        if take.fresh_session:
            agent.reset()
        if take.clean_output_first:
            clean_output()
        elif take.id == "summary-again":
            # Every attempt starts from the same state: only the file from the 'summary' take exists,
            # so a collision comes from that file and not from leftovers of a rejected attempt.
            clean_output(keep=KEEP_FILES)
        events: list[dict[str, Any]] = []
        started = time.time()
        try:
            result = run_once(agent, take.query, events)
        except Exception as exc:  # noqa: BLE001 - hosted APIs return transient 5xx; just try again
            print(f"  [{take.id}] attempt {attempt}: request failed ({type(exc).__name__}); retrying", flush=True)
            time.sleep(3)
            continue
        rec = {
            "id": take.id, "label": take.label, "query": take.query,
            "events": events, "answer": result.text, "iterations": result.iterations,
            "elapsed_seconds": round(time.time() - started, 1), "attempt": attempt,
        }
        ok, why = take.accept(rec)
        if ok and _errors(rec) > take.max_errors:
            ok, why = False, f"{why}; too many failed calls (> {take.max_errors})"
        rec["accepted"] = ok
        print(f"  [{take.id}] attempt {attempt}: {'ACCEPTED' if ok else 'rejected'} ({why})", flush=True)
        last = rec
        if ok:
            return rec
    if last is None:
        raise SystemExit(f"take '{take.id}' never completed a request")
    return last


# --------------------------------------------------------------------------- #
# Other real data: tests, code, listings
# --------------------------------------------------------------------------- #

def capture_pytest() -> dict[str, Any]:
    print("running pytest ...", flush=True)
    proc = subprocess.run([sys.executable, "-m", "pytest"], cwd=PROJECT, capture_output=True, text=True)
    lines = [ln.rstrip() for ln in proc.stdout.splitlines() if ln.strip()]
    summary = next((ln for ln in reversed(lines) if " passed" in ln or " failed" in ln), "")
    return {"command": "pytest", "lines": lines, "summary": summary.strip(), "returncode": proc.returncode}


def function_source(path: Path, name: str, *, signature_and_doc_only: bool = False) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            start = (node.decorator_list[0].lineno if node.decorator_list else node.lineno) - 1
            if signature_and_doc_only and node.body and isinstance(node.body[0], ast.Expr):
                end = node.body[0].end_lineno
            else:
                end = node.end_lineno
            return "\n".join(lines[start:end])
    raise KeyError(name)


def capture_code() -> dict[str, Any]:
    fs = PROJECT / "fs_tools.py"
    return {
        "tools": {n: function_source(fs, n, signature_and_doc_only=True)
                  for n in ("read_file", "list_files", "write_file", "search_in_file")},
        "resolve": function_source(fs, "_resolve"),
        "schema": json.dumps(next(s for s in tool_schemas.TOOL_SPECS if s["name"] == "search_in_file"), indent=2),
        "loc": {p.name: len(p.read_text(encoding="utf-8").splitlines())
                for p in (fs, PROJECT / "tool_schemas.py", PROJECT / "llm_file_assistant.py")},
    }


def build_data(provider: lfa.Provider, base_url: str, takes: list[dict[str, Any]], pytest_block: dict[str, Any]) -> dict[str, Any]:
    resumes = fs_tools.list_files("resumes")
    return {
        "meta": {
            "provider": provider.name, "model": provider.model,
            "endpoint": "Ollama cloud" if "ollama.com" in base_url else ("local Ollama" if provider.name == "ollama" else provider.name),
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "repo": "github.com/Naman6019/LLM",
        },
        "resumes": [{"name": r["name"], "size_bytes": r["size_bytes"], "extension": r["extension"]} for r in resumes],
        "providers": lfa.describe_providers(),
        "pytest": pytest_block,
        "code": capture_code(),
        "takes": takes,
    }


def save(data: dict[str, Any]) -> None:
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", help="override provider (default: auto-detect from .env)")
    parser.add_argument("--model", help="override model")
    parser.add_argument("--attempts", type=int, default=6, help="max attempts per take (default 6)")
    parser.add_argument("--only", help="comma-separated take ids to (re)capture; others are kept from the existing file")
    parser.add_argument("--skip-pytest", action="store_true", help="reuse the pytest block from the existing file")
    args = parser.parse_args()

    stray = [p.name for p in OUTPUT_DIR.iterdir() if p.name != ".gitkeep"]
    if stray:
        raise SystemExit(f"output/ already contains {stray}; empty it first (this script deletes generated files).")

    provider = lfa.create_provider(args.provider, args.model)
    base_url = str(getattr(provider.client, "base_url", ""))
    print(f"provider={provider.name} model={provider.model} endpoint={base_url}", flush=True)
    agent = lfa.Agent(provider, max_iterations=lfa.DEFAULT_MAX_ITERATIONS)

    existing: dict[str, Any] = json.loads(OUT_FILE.read_text(encoding="utf-8")) if OUT_FILE.exists() else {}
    wanted = set(args.only.split(",")) if args.only else {t.id for t in TAKES}
    by_id = {t["id"]: t for t in existing.get("takes", []) if t["id"] not in wanted}

    pytest_block = existing["pytest"] if (args.skip_pytest and existing.get("pytest")) else capture_pytest()

    def ordered() -> list[dict[str, Any]]:
        return [by_id[t.id] for t in TAKES if t.id in by_id]

    try:
        for take in TAKES:
            if take.id not in wanted:
                continue
            if take.id == "summary-again":
                # The collision needs the summary file from the 'summary' take to be on disk.
                prior = by_id.get("summary")
                if prior and prior.get("written_file"):
                    target = PROJECT / prior["written_file"]["path"]
                    if not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(prior["written_file"]["content"], encoding="utf-8")
                    KEEP_FILES.add(target)
            print(f"capturing '{take.id}': {take.query!r}", flush=True)
            rec = capture_take(agent, take, args.attempts)
            if take.id == "summary" and rec["accepted"]:
                written = next((e for e in rec["events"] if e["type"] == "tool_call" and e["name"] == "write_file"), None)
                if written:
                    path = PROJECT / written["args"].get("filepath", "")
                    rec["written_file"] = {"path": written["args"].get("filepath"),
                                           "content": path.read_text(encoding="utf-8") if path.exists() else ""}
                    KEEP_FILES.add(path)
            by_id[take.id] = rec
            save(build_data(provider, base_url, ordered(), pytest_block))   # never lose a good take
    finally:
        clean_output()  # leave output/ pristine for the real recording

    rejected = [t["id"] for t in ordered() if not t.get("accepted")]
    missing = [t.id for t in TAKES if t.id not in by_id]
    print(f"\nwrote {OUT_FILE.relative_to(PROJECT)}")
    if rejected or missing:
        print(f"WARNING: takes not accepted: {rejected}; never completed: {missing}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
