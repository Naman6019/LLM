# LLM-Powered File System Assistant

[![tests](https://github.com/Naman6019/LLM/actions/workflows/tests.yml/badge.svg)](https://github.com/Naman6019/LLM/actions/workflows/tests.yml)

Sandboxed file-system tools (`read_file`, `list_files`, `write_file`, `search_in_file`) that an LLM
can call to work with resume files (PDF / DOCX / TXT). Ask in plain English:

> *"Find resumes mentioning Python experience"* -> the model lists the folder, searches every file
> in parallel, and answers from the tool results.

Works with **Anthropic Claude, OpenAI, Google Gemini, OpenRouter or Ollama** (local, no key); the
provider is chosen at runtime. See [Providers](#providers).

```
you> Find resumes mentioning Python experience
  > list_files(directory='resumes')
    <- ok 8 file(s): resume_alex_chen.txt, resume_david_okafor.docx, ...
  > search_in_file(filepath='resumes/resume_alex_chen.txt', keyword='Python')
  > search_in_file(filepath='resumes/resume_david_okafor.docx', keyword='Python')
    ... (one call per resume, issued in parallel)
    <- ok 0 matches for 'Python' in resumes/resume_david_okafor.docx
+------------------------------ assistant ------------------------------+
| Strong Python experience: John Doe (8 yrs, FastAPI/Django), ...        |
+-----------------------------------------------------------------------+
```
*(trace format shown for illustration; the answer text is written by the model)*

---

## Contents

1. [Quick start](#quick-start)
2. [Providers](#providers)
3. [Usage](#usage)
4. [Architecture](#architecture)
5. [Tool reference](#tool-reference)
6. [Design decisions](#design-decisions)
7. [Sample data](#sample-data)
8. [Testing](#testing)
9. [Extending](#extending)
10. [Limitations](#limitations)
11. [Troubleshooting](#troubleshooting)

## Quick start

Requires **Python 3.10+**.

```bash
# 1. create an environment and install dependencies
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. add a key for ONE provider (or use Ollama, which needs none -- see Providers)
cp .env.example .env                 # Windows: copy .env.example .env
#    ...then edit .env, e.g. set GEMINI_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY

# 3. check what is configured, then run it
python llm_file_assistant.py --list-providers
python llm_file_assistant.py
```

The `resumes/` folder already contains 8 dummy resumes, so it works out of the box. To rebuild
them: `python generate_resumes.py`.

The tools in `fs_tools.py` need **no API key** and can be used on their own:

```python
from fs_tools import read_file, list_files, search_in_file, write_file

list_files("resumes", ".pdf")
read_file("resumes/resume_john_doe.pdf")["metadata"]
search_in_file("resumes/resume_alex_chen.txt", "python")["matches"][0]["context"]
write_file("output/notes.txt", "hello")
```

## Providers

| Provider | `--provider` | Key variable | Default model | Notes |
|---|---|---|---|---|
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` | `claude-opus-5-5` | Native Messages API. `ANTHROPIC_MODEL=claude-sonnet-5-5` is cheaper. |
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` | `OPENAI_BASE_URL` lets you point at Azure/proxies/any OpenAI-compatible server. |
| Google Gemini | `gemini` | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | `gemini-3.8-flash` | Via Google's OpenAI-compatible endpoint. Get a key at [AI Studio](https://aistudio.google.com/apikey). |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY` | `openai/gpt-4o-mini` | One key, hundreds of models. Set `OPENROUTER_MODEL` to any `vendor/model` slug from the [model list](https://openrouter.ai/models). |
| Ollama | `ollama` | none (local) | `qwen3:8b` | Runs models on your machine. `OLLAMA_API_KEY` is only for Ollama cloud. |

Each provider has a `<NAME>_MODEL` variable (and Gemini/OpenRouter/Ollama/OpenAI a `<NAME>_BASE_URL`);
`--model` overrides them per run. **Selection order:** `--provider` flag, then `LLM_PROVIDER`, then
the first provider with a key set (order above). Ollama has no key, so it is auto-selected only if
`OLLAMA_API_KEY` or `OLLAMA_BASE_URL` is set; otherwise pass `--provider ollama`.
`python llm_file_assistant.py --list-providers` shows the table with what is configured on your machine.

```bash
python llm_file_assistant.py --provider gemini
python llm_file_assistant.py --provider openrouter --model anthropic/claude-sonnet-5.5
python llm_file_assistant.py --provider ollama --model qwen3:8b
```

**Gemini, OpenRouter, Ollama and OpenAI share one adapter** because they all speak the OpenAI Chat
Completions protocol; only the base URL, key and model differ (see `PROVIDERS` in
`llm_file_assistant.py`). Anthropic uses its native Messages API.

### Running locally with Ollama

```bash
ollama pull qwen3:8b            # once; a multi-GB download
ollama serve                    # if the Ollama app/service isn't already running
python llm_file_assistant.py --provider ollama
```

Things that matter for local models:

* **Pick a model that supports tool calling.** Models without support are rejected by Ollama with a 400 (`... does not support tools`), and some models answer with a tool call written out as JSON text, so nothing runs; the CLI detects both and prints a hint. Small models are also much less reliable at multi-step tool use (wrong arguments, wrong conclusions).
* **Context length.** Ollama's OpenAI-compatible API cannot set the context size, and default windows can be small. Reading all 8 resumes in one conversation needs several thousand tokens; if answers look truncated or the model "forgets" files, build a variant with a bigger window (`PARAMETER num_ctx 16384` in a Modelfile, then `ollama create`) and pass that name via `--model`.
* `OLLAMA_BASE_URL` defaults to `http://localhost:11434/v1`; a bare host such as `http://gpu-box:11434` gets `/v1` appended automatically.

### OpenRouter notes

Model names are `vendor/model` and **not every model supports tools**; pick one whose page lists
"tools" under supported parameters. OpenRouter's slugs differ from vendors' own IDs (for example
Anthropic's Sonnet is `anthropic/claude-sonnet-5.5` there). A 404 means the slug is wrong.

### Verification status

| Provider | Status |
|---|---|
| Ollama | Run against a real local server: tool calls, results and answers work with `qwen2.5:1.5b` (a 1.5B model is unreliable at multi-step tasks); `qwen2.5-coder:14b` printed tool calls as text (hint shown); `gemma3:12b` has no tool support (400 + hint shown). |
| Anthropic, OpenAI, Gemini, OpenRouter | Request/response handling is covered by automated tests against fake clients, with endpoints and defaults checked against each provider's docs. **Not yet run against the live APIs** (no keys were available when this was built). |

## Usage

```bash
python llm_file_assistant.py                          # interactive chat (keeps conversation context)
python llm_file_assistant.py -q "List all PDF resumes" # one-shot
python llm_file_assistant.py --provider openai --model gpt-4o-mini
python llm_file_assistant.py --no-trace -q "..."      # hide tool calls, print only the answer
```

| Flag | Meaning |
|---|---|
| `-q, --query` | Run one request and exit (omit for interactive mode) |
| `--provider NAME` | `anthropic`, `openai`, `gemini`, `openrouter` or `ollama`. Default: see [Providers](#providers) |
| `--model NAME` | Default: the provider's `<NAME>_MODEL` variable, else its default model |
| `--list-providers` | Show providers, key/model variables, defaults and whether each is ready, then exit |
| `--root DIR` | Sandbox root for the tools (default: project folder, or `FS_ROOT`) |
| `--max-iterations N` | Cap on model<->tool round trips per request (default 15) |
| `--no-trace` | Suppress the tool-call trace |

Interactive commands: `/tools`, `/reset` (clear conversation), `/help`, `/exit`.

### Example requests

| Request | What the model typically does |
|---|---|
| `Read all resumes in the resumes folder` | `list_files("resumes")`, then `read_file` for each, then a summary per candidate |
| `Find resumes mentioning Python experience` | `list_files`, then `search_in_file(..., "Python")` per file in parallel, then ranks real experience vs. passing mentions |
| `Create a summary file for resume_john_doe.pdf` | `read_file`, then `write_file("output/john_doe_summary.md", ...)` |
| `Which candidates know Kubernetes? Save the list to output/k8s.txt` | searches, then writes the report |
| `Read ../../secrets.txt` | tool returns `outside_sandbox`; the model explains it can't |

Model behaviour is non-deterministic: the exact calls and wording vary between runs.

## Architecture

```
            +------------------------------ llm_file_assistant.py ------------------------------+
 user ----> |  Agent loop                                                                          |
            |   1. send history + tool schemas ----------------> Provider adapter ---> LLM API    |
            |   2. reply has tool calls?  --no--> return text      (5 providers)                 |
            |            | yes                                                                     |
            |   3. execute_tool(name, args)  <-------------+                                       |
            |   4. append tool results to history, goto 1  |                                       |
            +----------------------------------------------|---------------------------------------+
                                                           v
                              tool_schemas.py  (validate args, route, never raises)
                                                           v
                              fs_tools.py      (sandbox + the 4 tools)
```

| File | Responsibility |
|---|---|
| [`fs_tools.py`](fs_tools.py) | Part A. The four tools, text extraction, sandbox, error envelope. No LLM dependency. |
| [`tool_schemas.py`](tool_schemas.py) | One provider-neutral JSON-Schema spec per tool, projected into Anthropic and OpenAI-compatible formats, plus `execute_tool()` (argument validation and dispatch). |
| [`llm_file_assistant.py`](llm_file_assistant.py) | Part B. The `PROVIDERS` registry, two adapters (`AnthropicProvider`; `OpenAIProvider`, reused for OpenAI/Gemini/OpenRouter/Ollama), the provider-agnostic `Agent` loop, CLI + rich tracer. |
| [`generate_resumes.py`](generate_resumes.py) | Deterministic builder for the sample resumes (reportlab, python-docx). |
| [`tests/`](tests) | 144 pytest tests; no network or API key needed. |

### The tool-calling loop

The loop is hand-written (not an SDK "tool runner") so the mechanics are visible:

1. **Declare** the tools with every request (`tools=` / `input_schema` for Anthropic; `tools=[{"type":"function",...}]` for OpenAI).
2. The model responds with **tool calls** (Anthropic `tool_use` blocks, stop reason `tool_use`; OpenAI `tool_calls`, finish reason `tool_calls`). Several can arrive in one turn.
3. We **execute** each via `execute_tool`, which validates arguments against the schema and never raises.
4. We return **all results from that turn together** (Anthropic: one user message of `tool_result` blocks with `is_error` set on failures; OpenAI: one `tool` message per call) and call the model again.
5. When the reply contains no tool calls, that text is the answer.

Provider differences are isolated in the adapters: message shapes, stop-reason names, and OpenAI's JSON-*string* arguments (malformed JSON becomes an error result the model can correct, not a crash).

Robustness details:

* **Iteration cap** (`--max-iterations`) stops runaway loops.
* **Rollback on failure**: if the API errors mid-turn (rate limit, network), the history is rolled back to before the request, so the next message doesn't hit a dangling `tool_use` with no result.
* **Truncated/refused responses** (`max_tokens`, `refusal`) are reported rather than silently shown as complete answers.
* **Tool results are size-capped** (60k chars) before being sent back.

## Tool reference

All dict-returning tools use one envelope: success is `{"success": true, ...}`; failure is
`{"success": false, "error": {"type": "<slug>", "message": "<human-readable, actionable>"}}`.
Error types: `not_found`, `outside_sandbox`, `unsupported_format`, `extraction_failed`,
`invalid_argument`, `file_exists`, `permission_denied`, `io_error`.

### `read_file(filepath, max_chars=20000) -> dict`

Extracts text from `.pdf` (pypdf), `.docx` (python-docx; paragraphs **and** table cells, in document order) or `.txt` (UTF-8, BOM-aware, latin-1 fallback).

```json
{"success": true, "filepath": "resumes/resume_john_doe.pdf", "content": "John Doe\n Senior Backend Engineer ...",
 "metadata": {"filename": "resume_john_doe.pdf", "extension": ".pdf", "format": "pdf", "size_bytes": 3143,
              "modified": "2026-10-07T04:40:44+00:00", "char_count": 1480, "word_count": 203,
              "truncated": false, "page_count": 1}}
```
Also `table_count` (DOCX) and `encoding` (TXT). Fails cleanly on missing files, directories, unsupported
types, corrupt or password-protected PDFs, and scanned/empty documents ("no extractable text, OCR is not supported").
Content beyond `max_chars` is cut and `metadata.truncated` is `true`.

### `list_files(directory, extension=None) -> list`

Returns `[{"name", "path", "size_bytes", "modified", "extension"}, ...]` sorted by name. The extension filter accepts `pdf`, `.pdf` or `.PDF`. Non-recursive; skips sub-directories and dotfiles. Raises `FsToolError` for a missing directory or sandbox violation (see [design decisions](#design-decisions)); through the LLM interface this becomes a normal error result.

### `write_file(filepath, content, overwrite=False) -> dict`

Creates missing parent directories, writes UTF-8 **atomically** (temp file then `os.replace`), and returns
`{"success", "filepath", "bytes_written", "created_directories", "overwritten"}`.
Refuses to overwrite unless `overwrite=True`; allows only `.txt .md .json .csv .log`; 1 MB limit.

### `search_in_file(filepath, keyword, context_chars=80, max_matches=20, whole_word=False) -> dict`

Case-insensitive **literal** search (regex metacharacters are escaped, so `C++` works) over the *full* extracted text.

```json
{"success": true, "filepath": "resumes/resume_alex_chen.txt", "keyword": "python",
 "total_matches": 2, "returned_matches": 2, "truncated": false,
 "matches": [{"line": 14, "offset": 617, "match": "Python",
              "context": "...* Wrote basic Python scripts to automate asset pipelines..."}]}
```
`match` keeps the original casing; `line` is 1-based in the extracted text; zero matches is a *successful* result (`total_matches: 0`). `whole_word=True` stops `Java` matching `JavaScript`.

## Design decisions

* **Sandboxing.** An LLM that picks file paths must not be able to read arbitrary files. Every path is resolved against a root (`FS_ROOT`, default the project folder); `..` traversal, absolute paths outside the root, and symlink escapes return `outside_sandbox`.
* **Errors are data, not exceptions.** The model can read `"File not found ... Use list_files"` and fix its call. Tool failures are sent as `is_error` results rather than crashing the loop.
* **Argument validation at the boundary.** Model-supplied arguments are untrusted: unknown tools, missing/extra/ill-typed arguments produce error results.
* **Provider-neutral tool spec.** Written once in `tool_schemas.py`; a test asserts the schema parameters match the Python signatures, so they can't drift apart.
* **No forced tool choice and no prefill.** The loop uses the default `auto` tool choice, which is the portable behaviour across all providers and newer Claude models.

Deliberate points to be aware of (small deviations/extensions of the brief):

| Brief | Implementation | Why |
|---|---|---|
| `list_files(...) -> list` | Returns a plain list; raises `FsToolError` on bad input | Keeps the specified signature. The LLM path wraps it into `{"success", "count", "files"}` / an error envelope. |
| `write_file(filepath, content)` | Extra `overwrite=False` flag; plain-text extensions only | Prevents an LLM from silently destroying resumes or producing a corrupt "PDF". Pass `overwrite=True` to replace. |
| `read_file(filepath)` | Optional `max_chars` | Bounds context-window usage. |
| `search_in_file(filepath, keyword)` | Optional `context_chars`, `max_matches`, `whole_word` | Tunable context and result size. |

## Sample data

`resumes/` holds 8 fictional candidates (3 PDF, 3 DOCX, 2 TXT) built so the demo queries are non-trivial:

| File | Profile | Python? |
|---|---|---|
| `resume_john_doe.pdf` | Senior backend engineer (FastAPI/Django) | Core skill, 8 yrs |
| `resume_priya_sharma.docx` | Data scientist (pandas, PyTorch) | Core skill |
| `resume_sara_lindqvist.txt` | ML engineer, NLP | Core skill |
| `resume_rahul_mehta.pdf` | Recent graduate | Coursework, internship, projects |
| `resume_maria_garcia.pdf` | Site reliability engineer | Automation tooling |
| `resume_alex_chen.txt` | Frontend engineer (React) | "Basic Python scripting" |
| `resume_emily_watson.docx` | Product manager | Only an introductory course |
| `resume_david_okafor.docx` | Java/Kotlin backend developer | None |

All names, e-mails (`example.com`) and phone numbers (555-01xx) are fictional. The DOCX files store skills in a real table, which exercises the table extraction.

## Testing

```bash
pytest
```

144 tests, no network or API key required (the LLM clients are replaced by scripted fakes that record the exact payloads):

* `test_fs_tools.py`: every tool's happy path and failure modes (missing/corrupt/blank/scanned files, truncation, encodings, sandbox escapes including symlinks, overwrite guard, atomic-write cleanup, literal vs. regex search, whole-word, line numbers) and checks on the shipped sample corpus.
* `test_tool_schemas.py`: schema/signature consistency, both vendor formats, argument validation.
* `test_agent.py`: the loop (parallel calls, error recovery, iteration cap, rollback, `max_tokens`/`refusal`), the exact Anthropic and OpenAI wire formats, the provider registry (key/base-URL/model resolution for all five providers, auto-detection, Ollama defaults), OpenAI-compatible quirks (missing tool-call ids, object arguments, `stop` with tool calls), error hints, CLI helpers.

The test run uses a project-local temp dir (`.pytest_tmp`, set in `pytest.ini`). One test (symlink escape) is skipped where the OS doesn't permit creating symlinks, e.g. Windows without Developer Mode.

Live-model runs are not part of the automated suite; they need a key and are non-deterministic. Use the example requests above to try them.

## Extending

Add a tool in three steps: (1) write the function in `fs_tools.py` (decorate with `@safe_tool` if it returns a dict); (2) add its spec to `TOOL_SPECS` and its function to `_REGISTRY` in `tool_schemas.py`; (3) done: both providers, validation and the trace pick it up. `tests/test_tool_schemas.py` will fail if the schema and signature disagree. To add another **OpenAI-compatible** provider (LM Studio, vLLM, Groq, Together, ...), add one `ProviderSpec` entry to `PROVIDERS` (key variable, base URL, default model) and a row to `.env.example`; no adapter code is needed. A provider with its own protocol needs a new `Provider` subclass (five small methods) and a branch in `create_provider`.

## Limitations

* No OCR: scanned (image-only) PDFs return `extraction_failed`.
* `list_files` is non-recursive; `search_in_file` searches one file per call (the model fans out in parallel).
* PDF text extraction quality depends on how the PDF was produced; multi-column layouts may interleave.
* Conversation history grows for the life of an interactive session (use `/reset`). There is no summarisation.
* The sandbox is path-based; it is not an OS-level security boundary.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Configuration error: No API key found` | Create `.env` from `.env.example` (or export the variable) |
| `ANTHROPIC_API_KEY is not set` when using `--provider anthropic` | Set that key, or use `--provider openai` |
| `Request failed: ... 404 model` | The model name isn't available to your account; set the provider's `<NAME>_MODEL` variable or `--model` (OpenRouter slugs are `vendor/model`) |
| `Request failed: APIConnectionError` with Ollama | Start Ollama (`ollama serve`), `ollama pull <model>`, check `OLLAMA_BASE_URL`; the CLI prints this as a hint |
| 400 error or the model never calls tools (OpenRouter/Ollama) | The chosen model doesn't support tool calling; pick one that does |
| Ollama model ignores files or answers look cut off | Context window too small; see [Running locally with Ollama](#running-locally-with-ollama) |
| `No provider configured` | Set one provider's key in `.env`, or run Ollama and pass `--provider ollama` |
| Model keeps calling tools and stops with "tool-use rounds" | Narrow the request, or raise `--max-iterations` |
| Garbled characters in the Windows console | Use Windows Terminal; the CLI already switches stdout to UTF-8 |
| pytest `PermissionError` on a temp dir | Already handled via `--basetemp=.pytest_tmp` in `pytest.ini` |

## Demo video

A suggested 2-3 minute walkthrough is in [DEMO_SCRIPT.md](DEMO_SCRIPT.md).
