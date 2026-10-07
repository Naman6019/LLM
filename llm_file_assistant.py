"""llm_file_assistant -- an LLM agent that operates on files through ``fs_tools`` (Part B).

How it works
------------
1. The user's request and the four tool definitions (``tool_schemas.TOOL_SPECS``) are sent to
   the model (Anthropic, OpenAI, Gemini, OpenRouter or Ollama, chosen at runtime).
2. If the model answers with *tool calls* instead of text, we run each one through
   ``tool_schemas.execute_tool`` (validated, sandboxed, never raises) and send the results
   back as ``tool_result`` / ``tool`` messages.
3. Steps 1-2 repeat until the model replies with plain text (or an iteration cap is hit).

The loop is written by hand rather than with an SDK "tool runner" so the mechanics of function
calling are explicit.  Provider differences (message shapes, stop reasons, argument encoding)
are confined to two small ``Provider`` adapters -- native Anthropic, and an OpenAI-compatible
one reused for OpenAI / Gemini / OpenRouter / Ollama via ``PROVIDERS`` -- while the ``Agent``
loop is provider-agnostic.

Usage::

    python llm_file_assistant.py                       # interactive chat
    python llm_file_assistant.py -q "List all resumes"  # one-shot
    python llm_file_assistant.py --provider gemini
    python llm_file_assistant.py --provider ollama --model qwen3:8b
    python llm_file_assistant.py --list-providers
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import tool_schemas

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProviderSpec:
    """Everything needed to configure one LLM backend.

    ``kind`` selects the adapter: ``"anthropic"`` (native Messages API) or ``"openai_compat"``
    (the Chat Completions protocol, which OpenAI, Gemini, OpenRouter and Ollama all speak).
    """

    name: str
    kind: str
    key_envs: tuple[str, ...]                 # accepted API-key variables, first one set wins
    model_env: str
    default_model: str
    base_url_env: str | None = None
    default_base_url: str | None = None       # None -> the SDK's own default endpoint
    key_required: bool = True
    placeholder_key: str = ""                 # sent when no key is needed (the SDK insists on a value)
    strip_additional_properties: bool = False # drop 'additionalProperties' from tool schemas (see below)
    description: str = ""


PROVIDERS: dict[str, ProviderSpec] = {
    spec.name: spec
    for spec in (
        ProviderSpec(
            "anthropic", "anthropic", ("ANTHROPIC_API_KEY",), "ANTHROPIC_MODEL", "claude-opus-5-5",
            description="Anthropic Claude (native Messages API)",
        ),
        ProviderSpec(
            "openai", "openai_compat", ("OPENAI_API_KEY",), "OPENAI_MODEL", "gpt-4o-mini",
            base_url_env="OPENAI_BASE_URL", description="OpenAI",
        ),
        ProviderSpec(
            "gemini", "openai_compat", ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "GEMINI_MODEL", "gemini-3.8-flash",
            base_url_env="GEMINI_BASE_URL",
            default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            # Gemini's function-declaration schema is a restricted OpenAPI subset. Dropping the
            # (purely advisory) 'additionalProperties' keyword avoids any chance of a schema
            # rejection; execute_tool() still enforces it server-side.
            strip_additional_properties=True,
            description="Google Gemini (OpenAI-compatible endpoint)",
        ),
        ProviderSpec(
            "openrouter", "openai_compat", ("OPENROUTER_API_KEY",), "OPENROUTER_MODEL", "openai/gpt-4o-mini",
            base_url_env="OPENROUTER_BASE_URL", default_base_url="https://openrouter.ai/api/v1",
            description="OpenRouter (hundreds of models behind one key; use 'vendor/model' names)",
        ),
        ProviderSpec(
            "ollama", "openai_compat", ("OLLAMA_API_KEY",), "OLLAMA_MODEL", "qwen3:8b",
            base_url_env="OLLAMA_BASE_URL", default_base_url="http://localhost:11434/v1",
            key_required=False, placeholder_key="ollama",
            description="Ollama (local models, no API key; OLLAMA_API_KEY only for Ollama cloud)",
        ),
    )
}
DEFAULT_MODELS = {name: spec.default_model for name, spec in PROVIDERS.items()}

MAX_TOKENS = 16_000                 # per model response
DEFAULT_MAX_ITERATIONS = 15         # model<->tool round trips per user message
MAX_TOOL_RESULT_CHARS = 60_000      # hard cap on what we feed back to the model per tool call

SYSTEM_PROMPT = """\
You are a resume file assistant. You help the user inspect, search and summarise resume files \
stored in a project directory, using the file-system tools you have been given.

Rules:
- Resumes live in `resumes/` (PDF, DOCX or TXT). Files you generate belong in `output/`. \
All paths are relative to the project root.
- Never invent file names or resume contents. Discover files with list_files and base every \
statement on tool output.
- To check many resumes for something, list the files first, then call search_in_file (or \
read_file) on each one. Independent calls can be issued together in a single turn.
- When reporting search results, name each file, say whether it matches, and briefly quote the \
relevant snippet. Distinguish real experience from passing mentions (e.g. "basic Python", or an \
introductory course).
- write_file refuses to overwrite existing files. Choose a fresh descriptive filename (for \
example output/<candidate>_summary.md) unless the user explicitly asks you to replace a file.
- If a tool returns an error, read the message and fix the call if you can (wrong path or \
extension); otherwise tell the user plainly what went wrong.
- Be concise. When you finish, state what you did and where any files were written.
"""


class ConfigError(RuntimeError):
    """Missing API key / unknown provider -- reported to the user without a traceback."""


# --------------------------------------------------------------------------- #
# Provider-neutral data model
# --------------------------------------------------------------------------- #

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] | None          # None when the model sent unparseable JSON
    parse_error: str | None = None


@dataclass
class ToolResult:
    call_id: str
    name: str
    content: str                               # JSON text sent back to the model
    is_error: bool = False


@dataclass
class Turn:
    """One model response, normalised across vendors."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end"                   # end | tool_use | max_tokens | refusal | other


@dataclass
class AgentResult:
    text: str
    iterations: int
    tool_calls: list[tuple[str, dict[str, Any] | None, bool]] = field(default_factory=list)  # (name, args, success)
    stopped_early: str | None = None           # set if the loop ended abnormally


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #

class Provider(ABC):
    """Owns the vendor-native message history and talks to one vendor API."""

    name: str
    model: str

    @abstractmethod
    def add_user_message(self, text: str) -> None: ...

    @abstractmethod
    def complete(self) -> Turn:
        """Send the history + tools, record the assistant reply in the history, return it."""

    @abstractmethod
    def add_tool_results(self, results: list[ToolResult]) -> None: ...

    @abstractmethod
    def checkpoint(self) -> int:
        """Opaque marker for the current history length (see ``rollback``)."""

    @abstractmethod
    def rollback(self, marker: int) -> None:
        """Drop everything after ``marker`` so a failed turn cannot corrupt the history."""

    @abstractmethod
    def reset(self) -> None: ...


class AnthropicProvider(Provider):
    """Claude via the Messages API (native ``tool_use`` / ``tool_result`` blocks)."""

    name = "anthropic"
    _STOP_MAP = {"tool_use": "tool_use", "end_turn": "end", "max_tokens": "max_tokens", "refusal": "refusal"}

    def __init__(self, model: str | None = None, client: Any = None, system: str = SYSTEM_PROMPT) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.client = client
        self.model = model or DEFAULT_MODELS["anthropic"]
        self.system = system
        self.tools = tool_schemas.anthropic_tools()
        self.messages: list[dict[str, Any]] = []

    def add_user_message(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def complete(self) -> Turn:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=self.system,
            tools=self.tools,
            messages=self.messages,
        )
        # Store the content blocks exactly as returned: thinking blocks (if any) must be echoed
        # back unchanged when the conversation continues after a tool call.
        self.messages.append({"role": "assistant", "content": response.content})
        text = "".join(b.text for b in response.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, b.input) for b in response.content if b.type == "tool_use"]
        return Turn(text, calls, self._STOP_MAP.get(response.stop_reason, "other"))

    def add_tool_results(self, results: list[ToolResult]) -> None:
        # All results for one assistant turn go in ONE user message (required for parallel calls).
        self.messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.call_id,
                        "content": r.content,
                        **({"is_error": True} if r.is_error else {}),
                    }
                    for r in results
                ],
            }
        )

    def checkpoint(self) -> int:
        return len(self.messages)

    def rollback(self, marker: int) -> None:
        del self.messages[marker:]

    def reset(self) -> None:
        self.messages.clear()


class OpenAIProvider(Provider):
    """Any backend that speaks OpenAI Chat Completions function calling.

    Used for OpenAI itself and, via ``base_url``, for Gemini, OpenRouter and Ollama -- the
    ``name`` argument only changes what is displayed.  Local/compat servers are less uniform
    than OpenAI proper, so this adapter is deliberately forgiving: it tolerates missing tool-call
    ids, arguments delivered as an object instead of a JSON string, and malformed JSON (which is
    reported back to the model as a tool error rather than crashing the loop).
    """

    def __init__(
        self,
        model: str | None = None,
        client: Any = None,
        system: str = SYSTEM_PROMPT,
        name: str = "openai",
        strip_additional_properties: bool = False,
    ) -> None:
        if client is None:
            import openai

            client = openai.OpenAI()  # reads OPENAI_API_KEY / OPENAI_BASE_URL
        self.client = client
        self.name = name
        self.model = model or DEFAULT_MODELS.get(name, DEFAULT_MODELS["openai"])
        self.system = system
        self.tools = tool_schemas.openai_tools(strip_additional_properties=strip_additional_properties)
        self.messages: list[dict[str, Any]] = []
        self.reset()

    def add_user_message(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def complete(self) -> Turn:
        response = self.client.chat.completions.create(
            model=self.model, messages=self.messages, tools=self.tools
        )
        choice = response.choices[0]
        message = choice.message
        raw_calls = [tc for tc in (message.tool_calls or []) if getattr(tc, "function", None)]

        calls: list[ToolCall] = []
        history_calls: list[dict[str, Any]] = []
        for index, tc in enumerate(raw_calls):
            # Some compat servers omit or blank the id; the follow-up 'tool' message needs one.
            call_id = tc.id or f"call_{len(self.messages)}_{index}"
            raw_args = tc.function.arguments
            if isinstance(raw_args, dict):       # some servers return an object, not a JSON string
                arg_text, args, error = json.dumps(raw_args), raw_args, None
            else:
                arg_text = raw_args or "{}"
                try:
                    args, error = json.loads(arg_text), None
                except json.JSONDecodeError as exc:  # models occasionally emit malformed JSON
                    args, error = None, f"Arguments were not valid JSON: {exc}"
            calls.append(ToolCall(call_id, tc.function.name, args, error))
            history_calls.append(
                {"id": call_id, "type": "function", "function": {"name": tc.function.name, "arguments": arg_text}}
            )

        entry: dict[str, Any] = {"role": "assistant", "content": message.content}
        if history_calls:
            entry["tool_calls"] = history_calls
        self.messages.append(entry)

        stop = {"stop": "end", "tool_calls": "tool_use", "length": "max_tokens", "content_filter": "refusal"}.get(
            choice.finish_reason, "other"
        )
        return Turn(message.content or "", calls, stop)

    def add_tool_results(self, results: list[ToolResult]) -> None:
        for r in results:  # OpenAI wants one 'tool' message per call
            self.messages.append({"role": "tool", "tool_call_id": r.call_id, "content": r.content})

    def checkpoint(self) -> int:
        return len(self.messages)

    def rollback(self, marker: int) -> None:
        del self.messages[marker:]

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": self.system}]


def _env(*names: str) -> str | None:
    """First non-empty value among the given environment variables."""
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return None


def _is_configured(spec: ProviderSpec) -> bool:
    """Used for auto-detection: a key is present, or (key-less backends) a base URL was set."""
    if _env(*spec.key_envs):
        return True
    return (not spec.key_required) and bool(spec.base_url_env and _env(spec.base_url_env))


def _normalise_base_url(spec: ProviderSpec, url: str | None) -> str | None:
    """Forgive a bare Ollama host (``http://localhost:11434``) by appending the ``/v1`` path."""
    if spec.name == "ollama" and url and urlparse(url).path in ("", "/"):
        return url.rstrip("/") + "/v1"
    return url


def resolve_provider_name(explicit: str | None = None) -> str:
    """CLI flag > LLM_PROVIDER env var > first provider (in registry order) with credentials.

    Ollama needs no key, so it is only auto-selected when ``OLLAMA_API_KEY`` or
    ``OLLAMA_BASE_URL`` is set; otherwise pick it explicitly with ``--provider ollama``.
    """
    name = (explicit or os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if name:
        if name not in PROVIDERS:
            raise ConfigError(f"Unknown provider '{name}'. Choose one of: {', '.join(PROVIDERS)}.")
        return name
    for candidate, spec in PROVIDERS.items():
        if _is_configured(spec):
            return candidate
    keys = ", ".join(spec.key_envs[0] for spec in PROVIDERS.values() if spec.key_required)
    raise ConfigError(
        f"No provider configured. Copy .env.example to .env and set one of: {keys} "
        "(or run Ollama locally and pass --provider ollama)."
    )


def create_provider(name: str | None = None, model: str | None = None) -> Provider:
    spec = PROVIDERS[resolve_provider_name(name)]
    api_key = _env(*spec.key_envs)
    if spec.key_required and not api_key:
        raise ConfigError(
            f"{' or '.join(spec.key_envs)} is not set. Add it to .env or export it, or pick another --provider."
        )
    chosen_model = model or _env(spec.model_env) or spec.default_model

    if spec.kind == "anthropic":
        return AnthropicProvider(model=chosen_model)

    import openai

    base_url = _normalise_base_url(spec, (_env(spec.base_url_env) if spec.base_url_env else None) or spec.default_base_url)
    client = openai.OpenAI(api_key=api_key or spec.placeholder_key, base_url=base_url)
    return OpenAIProvider(
        model=chosen_model,
        client=client,
        name=spec.name,
        strip_additional_properties=spec.strip_additional_properties,
    )


def describe_providers() -> list[dict[str, Any]]:
    """Rows for ``--list-providers``: name, key variable(s), default model, and readiness."""
    rows = []
    for spec in PROVIDERS.values():
        rows.append(
            {
                "name": spec.name,
                "description": spec.description,
                "key": " or ".join(spec.key_envs) if spec.key_required else "(none needed)",
                "model_env": spec.model_env,
                "default_model": spec.default_model,
                "ready": bool(_env(*spec.key_envs)) or not spec.key_required,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Agent loop
# --------------------------------------------------------------------------- #

EventHandler = Callable[..., None]


def serialize_result(result: dict[str, Any]) -> str:
    """JSON-encode a tool result for the model, hard-capping its size."""
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + f'... [truncated: result exceeded {MAX_TOOL_RESULT_CHARS:,} characters]'
    return text


class Agent:
    """Runs the request -> tool call -> result -> ... -> answer loop on top of a Provider.

    ``on_event(kind, **data)`` is invoked for observability (used by the CLI trace):

    * ``"assistant_text"``  text=str            -- model prose emitted alongside tool calls
    * ``"tool_call"``       call=ToolCall
    * ``"tool_result"``     call=ToolCall, result=dict
    """

    def __init__(
        self,
        provider: Provider,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        on_event: EventHandler | None = None,
    ) -> None:
        self.provider = provider
        self.max_iterations = max_iterations
        self.on_event = on_event or (lambda *a, **k: None)

    def reset(self) -> None:
        self.provider.reset()

    def run(self, user_message: str) -> AgentResult:
        marker = self.provider.checkpoint()
        try:
            return self._run(user_message)
        except BaseException:
            self.provider.rollback(marker)  # leave history consistent so the chat can continue
            raise

    def _run(self, user_message: str) -> AgentResult:
        self.provider.add_user_message(user_message)
        executed: list[tuple[str, dict[str, Any] | None, bool]] = []

        for iteration in range(1, self.max_iterations + 1):
            turn = self.provider.complete()

            if not turn.tool_calls:
                text, stopped = turn.text.strip(), None
                if turn.stop_reason == "max_tokens":
                    stopped = "max_tokens"
                    text += "\n\n[Response was cut off: the model hit its output token limit.]"
                elif turn.stop_reason == "refusal":
                    stopped = "refusal"
                    text = text or "[The model declined to respond to this request.]"
                return AgentResult(text, iteration, executed, stopped)

            if turn.text.strip():
                self.on_event("assistant_text", text=turn.text.strip())

            results: list[ToolResult] = []
            for call in turn.tool_calls:
                self.on_event("tool_call", call=call)
                if call.parse_error or call.arguments is None:
                    result = {"success": False, "error": {"type": "invalid_argument", "message": call.parse_error or "No arguments."}}
                else:
                    result = tool_schemas.execute_tool(call.name, call.arguments)
                success = bool(result.get("success", False))
                executed.append((call.name, call.arguments, success))
                self.on_event("tool_result", call=call, result=result)
                results.append(ToolResult(call.id, call.name, serialize_result(result), is_error=not success))
            self.provider.add_tool_results(results)

        return AgentResult(
            f"[Stopped after {self.max_iterations} tool-use rounds without a final answer. "
            "Try a narrower request.]",
            self.max_iterations,
            executed,
            "max_iterations",
        )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def summarize_result(name: str, result: dict[str, Any]) -> str:
    """One-line human summary of a tool result for the console trace."""
    if not result.get("success"):
        err = result.get("error", {})
        return f"{err.get('type', 'error')}: {err.get('message', 'unknown error')}"
    if name == "list_files":
        names = [f["name"] for f in result.get("files", [])]
        shown = ", ".join(names[:6]) + (f", +{len(names) - 6} more" if len(names) > 6 else "")
        return f"{result.get('count', len(names))} file(s)" + (f": {shown}" if names else "")
    if name == "read_file":
        meta = result.get("metadata", {})
        flag = ", truncated" if meta.get("truncated") else ""
        return f"{result.get('filepath')} - {meta.get('word_count', '?')} words ({meta.get('format', '?')}{flag})"
    if name == "search_in_file":
        n = result.get("total_matches", 0)
        return f"{n} match{'es' if n != 1 else ''} for '{result.get('keyword')}' in {result.get('filepath')}"
    if name == "write_file":
        verb = "overwrote" if result.get("overwritten") else "created"
        return f"{verb} {result.get('filepath')} ({result.get('bytes_written', 0):,} bytes)"
    return json.dumps(result, default=str)[:120]


def format_arguments(arguments: dict[str, Any] | None, limit: int = 60) -> str:
    """Compact ``key='value'`` rendering; long strings (e.g. file content) are elided."""
    if not arguments:
        return ""
    parts = []
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > limit:
            value = value[:limit] + f"... ({len(value)} chars)"
        parts.append(f"{key}={value!r}")
    return ", ".join(parts)


class ConsoleTracer:
    """Pretty-prints the tool-calling trace with ``rich`` (this is what the demo video shows)."""

    def __init__(self, console: Any) -> None:
        self.console = console

    def __call__(self, kind: str, **data: Any) -> None:
        from rich.markup import escape

        if kind == "assistant_text":
            self.console.print(f"[dim italic]{escape(data['text'])}[/]")
        elif kind == "tool_call":
            call: ToolCall = data["call"]
            self.console.print(
                f"  [bold cyan]> {escape(call.name)}[/][dim]({escape(format_arguments(call.arguments))})[/]"
            )
        elif kind == "tool_result":
            call, result = data["call"], data["result"]
            summary = escape(summarize_result(call.name, result))
            mark = "[green]ok[/]" if result.get("success") else "[bold red]error[/]"
            self.console.print(f"    [dim]<-[/] {mark} [dim]{summary}[/]")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Chat with an LLM that can list, read, search and write files via tool calling."
    )
    p.add_argument("-q", "--query", help="Run a single request and exit (default: interactive chat).")
    p.add_argument("--provider", choices=list(PROVIDERS), help="LLM provider (default: auto-detect from API keys).")
    p.add_argument("--model", help="Model name (default: per-provider default or <PROVIDER>_MODEL env var).")
    p.add_argument("--list-providers", action="store_true", help="Show supported providers, their env vars and defaults, then exit.")
    p.add_argument("--root", help="Sandbox root directory the tools may access (default: this project folder).")
    p.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS, help="Tool-use rounds per request.")
    p.add_argument("--no-trace", action="store_true", help="Hide the tool-call trace; print only the final answer.")
    return p


HELP_TEXT = (
    "Commands: /tools  list available tools   /reset  clear conversation   /help   /exit\n"
    "Try: 'Read all resumes in the resumes folder'  |  'Find resumes mentioning Python experience'  |  "
    "'Create a summary file for resume_john_doe.pdf'"
)


def error_hint(provider: Provider, exc: Exception) -> str | None:
    """A short, actionable pointer for common provider failures (None if nothing useful to add)."""
    status = getattr(exc, "status_code", None)
    if provider.name == "ollama" and (type(exc).__name__ == "APIConnectionError" or status == 404):
        return (f"Is Ollama running (`ollama serve`) and is the model pulled (`ollama pull {provider.model}`)? "
                "Also check OLLAMA_BASE_URL.")
    if status in (401, 403):
        spec = PROVIDERS.get(provider.name)
        return f"The API key was rejected. Check {' / '.join(spec.key_envs) if spec else 'your API key'}."
    if status == 404:
        spec = PROVIDERS.get(provider.name)
        extra = " OpenRouter names look like 'vendor/model'." if provider.name == "openrouter" else ""
        return f"Model '{provider.model}' was not found for this provider; set --model or {spec.model_env if spec else 'the model variable'}.{extra}"
    if status == 400 and provider.name != "anthropic":
        return "A 400 can mean this model doesn't support tool calling; try a model that does."
    return None


def looks_like_unexecuted_tool_call(text: str) -> bool:
    """True if the model's *text* is a tool call written out as JSON instead of a real tool call.

    Some local models (seen with Ollama) lack native tool-calling support and answer with
    ``{"name": "list_files", "arguments": {...}}`` as plain text, so nothing actually runs.
    """
    body = text.strip()
    if body.startswith("```"):
        body = body.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return False
    known = {spec["name"] for spec in tool_schemas.TOOL_SPECS}
    return isinstance(data, dict) and data.get("name") in known


def _print_providers(console: Any) -> None:
    from rich.table import Table

    table = Table(title="Supported providers", show_lines=False)
    for column in ("provider", "API key variable", "model variable", "default model", "ready"):
        table.add_column(column)
    for row in describe_providers():
        table.add_row(row["name"], row["key"], row["model_env"], row["default_model"], "yes" if row["ready"] else "no key")
    console.print(table)
    console.print("[dim]Auto-detect order: " + " > ".join(PROVIDERS) + ". Force one with --provider or LLM_PROVIDER.[/]")


def _print_answer(console: Any, text: str) -> None:
    from rich.markdown import Markdown
    from rich.panel import Panel

    console.print(Panel(Markdown(text or "(no text response)"), title="assistant", border_style="green"))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a legacy codepage
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    from rich.console import Console

    console = Console()
    args = build_parser().parse_args(argv)

    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent / ".env")
    except ImportError:  # python-dotenv is a convenience, not a requirement
        pass
    if args.root:
        os.environ["FS_ROOT"] = str(Path(args.root).expanduser().resolve())
    if args.list_providers:
        _print_providers(console)
        return 0

    try:
        provider = create_provider(args.provider, args.model)
    except ConfigError as exc:
        console.print(f"[bold red]Configuration error:[/] {exc}")
        return 2

    import fs_tools

    agent = Agent(
        provider,
        max_iterations=args.max_iterations,
        on_event=None if args.no_trace else ConsoleTracer(console),
    )
    console.print(f"[bold]LLM File Assistant[/] - provider=[cyan]{provider.name}[/] model=[cyan]{provider.model}[/] "
                  f"root=[dim]{fs_tools.get_root()}[/]")

    def handle(request: str) -> None:
        try:
            result = agent.run(request)
        except Exception as exc:  # network / auth / rate-limit errors from the vendor SDK
            console.print(f"[bold red]Request failed:[/] {type(exc).__name__}: {exc}")
            hint = error_hint(provider, exc)
            if hint:
                console.print(f"[yellow]Hint:[/] {hint}")
            return
        _print_answer(console, result.text)
        if not result.tool_calls and looks_like_unexecuted_tool_call(result.text):
            console.print(
                f"[yellow]Hint:[/] '{provider.model}' wrote a tool call as text instead of calling the tool, so "
                "nothing ran. It probably lacks native tool-calling support; try a model that advertises "
                "'tools' (for Ollama, see ollama.com/search?c=tools)."
            )

    if args.query:
        console.print(f"[bold]you>[/] {args.query}")
        handle(args.query)
        return 0

    console.print(f"[dim]{HELP_TEXT}[/]")
    while True:
        try:
            request = console.input("[bold]you>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return 0
        if not request:
            continue
        command = request.lower()
        if command in {"/exit", "/quit", "exit", "quit"}:
            return 0
        if command == "/help":
            console.print(f"[dim]{HELP_TEXT}[/]")
        elif command == "/reset":
            agent.reset()
            console.print("[dim]Conversation cleared.[/]")
        elif command == "/tools":
            for spec in tool_schemas.TOOL_SPECS:
                console.print(f"[cyan]{spec['name']}[/] - {spec['description'].split('. ')[0]}.")
        else:
            handle(request)


if __name__ == "__main__":
    sys.exit(main())
