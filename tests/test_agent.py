"""Tests for llm_file_assistant: agent loop, provider adapters and CLI helpers.

No network access or API key is needed -- vendor clients are replaced by scripted fakes that
record the exact payloads we would have sent, so the wire formats are asserted too.
"""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

import llm_file_assistant as lfa
from llm_file_assistant import Agent, AnthropicProvider, OpenAIProvider, ToolCall, Turn


# ----------------------------------------------------------------------------- helpers

class ScriptedProvider(lfa.Provider):
    """Replays pre-written Turns and records every tool-result batch it is handed."""

    name, model = "scripted", "fake"

    def __init__(self, turns):
        self.turns = list(turns)
        self.history: list = []
        self.result_batches: list = []

    def add_user_message(self, text): self.history.append(("user", text))
    def complete(self):
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        self.history.append(("assistant", turn))
        return turn
    def add_tool_results(self, results):
        self.result_batches.append(results)
        self.history.append(("tool", results))
    def checkpoint(self): return len(self.history)
    def rollback(self, marker): del self.history[marker:]
    def reset(self): self.history.clear()


def tc(id_, name, **args): return ToolCall(id_, name, args)


# ----------------------------------------------------------------------------- Agent loop

class TestAgentLoop:
    def test_plain_answer_without_tools(self):
        agent = Agent(ScriptedProvider([Turn("Hello!", [], "end")]))
        r = agent.run("hi")
        assert r.text == "Hello!" and r.iterations == 1 and r.tool_calls == []

    def test_tool_call_then_answer(self, sandbox):
        provider = ScriptedProvider([
            Turn("", [tc("c1", "list_files", directory="resumes")], "tool_use"),
            Turn("Found 3 resumes.", [], "end"),
        ])
        r = Agent(provider).run("list resumes")
        assert r.text == "Found 3 resumes." and r.iterations == 2
        assert r.tool_calls == [("list_files", {"directory": "resumes"}, True)]
        (batch,) = provider.result_batches
        payload = json.loads(batch[0].content)
        assert batch[0].call_id == "c1" and payload["count"] == 3 and not batch[0].is_error

    def test_parallel_calls_return_one_batch(self, sandbox):
        provider = ScriptedProvider([
            Turn("", [tc("a", "search_in_file", filepath="resumes/resume_alex_chen.txt", keyword="react"),
                      tc("b", "search_in_file", filepath="resumes/resume_john_doe.pdf", keyword="react")], "tool_use"),
            Turn("done", [], "end"),
        ])
        Agent(provider).run("q")
        assert len(provider.result_batches) == 1 and [r.call_id for r in provider.result_batches[0]] == ["a", "b"]

    def test_tool_error_is_fed_back_flagged_and_model_can_recover(self, sandbox):
        provider = ScriptedProvider([
            Turn("", [tc("c1", "read_file", filepath="resumes/nope.pdf")], "tool_use"),
            Turn("", [tc("c2", "list_files", directory="resumes")], "tool_use"),
            Turn("Recovered.", [], "end"),
        ])
        r = Agent(provider).run("read nope")
        first = provider.result_batches[0][0]
        assert first.is_error and json.loads(first.content)["error"]["type"] == "not_found"
        assert r.text == "Recovered." and [c[2] for c in r.tool_calls] == [False, True]

    def test_unknown_tool_and_bad_arguments_do_not_crash(self):
        provider = ScriptedProvider([
            Turn("", [tc("1", "rm_rf", path="/"), ToolCall("2", "read_file", None, "Arguments were not valid JSON")], "tool_use"),
            Turn("ok", [], "end"),
        ])
        Agent(provider).run("q")
        kinds = [json.loads(r.content)["error"]["type"] for r in provider.result_batches[0]]
        assert kinds == ["unknown_tool", "invalid_argument"]

    def test_path_traversal_attempt_is_blocked_end_to_end(self, sandbox):
        provider = ScriptedProvider([
            Turn("", [tc("1", "read_file", filepath="../../etc/passwd")], "tool_use"),
            Turn("blocked", [], "end"),
        ])
        Agent(provider).run("read passwd")
        assert json.loads(provider.result_batches[0][0].content)["error"]["type"] == "outside_sandbox"

    def test_iteration_cap(self, sandbox):
        loop = [Turn("", [tc(str(i), "list_files", directory=".")], "tool_use") for i in range(10)]
        r = Agent(ScriptedProvider(loop), max_iterations=3).run("loop forever")
        assert r.stopped_early == "max_iterations" and r.iterations == 3 and len(r.tool_calls) == 3

    def test_max_tokens_and_refusal_are_surfaced(self):
        r = Agent(ScriptedProvider([Turn("partial", [], "max_tokens")])).run("q")
        assert r.stopped_early == "max_tokens" and "cut off" in r.text
        r = Agent(ScriptedProvider([Turn("", [], "refusal")])).run("q")
        assert r.stopped_early == "refusal" and "declined" in r.text

    def test_history_rolled_back_when_api_fails_mid_turn(self, sandbox):
        provider = ScriptedProvider([
            Turn("", [tc("1", "list_files", directory="resumes")], "tool_use"),
            RuntimeError("503 overloaded"),
        ])
        agent = Agent(provider)
        with pytest.raises(RuntimeError):
            agent.run("q")
        assert provider.history == []          # no dangling user/tool_use/tool_result entries

    def test_events_emitted_in_order(self, sandbox):
        events = []
        provider = ScriptedProvider([
            Turn("Let me look.", [tc("1", "list_files", directory="resumes")], "tool_use"),
            Turn("done", [], "end"),
        ])
        Agent(provider, on_event=lambda kind, **d: events.append(kind)).run("q")
        assert events == ["assistant_text", "tool_call", "tool_result"]

    def test_oversized_results_are_capped(self):
        text = lfa.serialize_result({"success": True, "blob": "x" * (lfa.MAX_TOOL_RESULT_CHARS + 500)})
        assert len(text) < lfa.MAX_TOOL_RESULT_CHARS + 200 and "truncated" in text


# ----------------------------------------------------------------------------- Anthropic adapter

class FakeAnthropic:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
        self.messages = NS(create=self._create)

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})  # snapshot
        return self.responses.pop(0)


def a_text(t): return NS(type="text", text=t)
def a_tool(id_, name, **inp): return NS(type="tool_use", id=id_, name=name, input=inp)


class TestAnthropicProvider:
    def test_full_roundtrip_wire_format(self, sandbox):
        client = FakeAnthropic([
            NS(content=[a_text("Checking."), a_tool("tu_1", "read_file", filepath="resumes/missing.txt"),
                        a_tool("tu_2", "list_files", directory="resumes")], stop_reason="tool_use"),
            NS(content=[a_text("All done.")], stop_reason="end_turn"),
        ])
        provider = AnthropicProvider(model="claude-test", client=client)
        result = Agent(provider).run("do things")
        assert result.text == "All done." and result.iterations == 2

        first, second = client.calls
        assert first["model"] == "claude-test" and first["system"] == lfa.SYSTEM_PROMPT
        assert [t["name"] for t in first["tools"]][:2] == ["list_files", "read_file"]
        assert "tool_choice" not in first                      # forced tool use is unsupported on newer models
        assert first["messages"] == [{"role": "user", "content": "do things"}]

        # 2nd request: user, assistant (blocks echoed verbatim), ONE user message with BOTH results
        assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
        assert second["messages"][1]["content"][1].id == "tu_1"
        results = second["messages"][2]["content"]
        assert [r["tool_use_id"] for r in results] == ["tu_1", "tu_2"]
        assert all(r["type"] == "tool_result" for r in results)
        assert results[0]["is_error"] is True and "is_error" not in results[1]
        assert json.loads(results[1]["content"])["count"] == 3

    def test_stop_reason_mapping(self):
        for api, expected in [("end_turn", "end"), ("max_tokens", "max_tokens"), ("refusal", "refusal"), ("weird", "other")]:
            client = FakeAnthropic([NS(content=[a_text("x")], stop_reason=api)])
            p = AnthropicProvider(client=client)
            p.add_user_message("q")
            assert p.complete().stop_reason == expected

    def test_reset_checkpoint_rollback(self):
        p = AnthropicProvider(client=FakeAnthropic([]))
        p.add_user_message("a")
        marker = p.checkpoint()
        p.add_user_message("b")
        p.rollback(marker)
        assert len(p.messages) == 1
        p.reset()
        assert p.messages == []


# ----------------------------------------------------------------------------- OpenAI adapter

class FakeOpenAI:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


def o_resp(content=None, calls=(), finish="stop"):
    tool_calls = [NS(id=i, type="function", function=NS(name=n, arguments=a)) for i, n, a in calls] or None
    return NS(choices=[NS(message=NS(content=content, tool_calls=tool_calls), finish_reason=finish)])


class TestOpenAIProvider:
    def test_full_roundtrip_wire_format(self, sandbox):
        client = FakeOpenAI([
            o_resp(None, [("call_1", "list_files", '{"directory": "resumes"}'),
                          ("call_2", "read_file", '{"filepath": "resumes/resume_alex_chen.txt"}')], "tool_calls"),
            o_resp("Here you go.", finish="stop"),
        ])
        provider = OpenAIProvider(model="gpt-test", client=client)
        result = Agent(provider).run("read all")
        assert result.text == "Here you go." and len(result.tool_calls) == 2

        first, second = client.calls
        assert first["model"] == "gpt-test" and first["messages"][0] == {"role": "system", "content": lfa.SYSTEM_PROMPT}
        assert first["tools"][0]["type"] == "function"
        msgs = second["messages"]
        assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool", "tool"]
        assert msgs[2]["tool_calls"][0] == {"id": "call_1", "type": "function",
                                            "function": {"name": "list_files", "arguments": '{"directory": "resumes"}'}}
        assert [m["tool_call_id"] for m in msgs[3:]] == ["call_1", "call_2"]
        assert json.loads(msgs[3]["content"])["success"] is True

    def test_malformed_json_arguments_become_error_result(self):
        client = FakeOpenAI([o_resp(None, [("c1", "read_file", "{not json")], "tool_calls"), o_resp("sorry")])
        provider = OpenAIProvider(client=client)
        Agent(provider).run("q")
        tool_msg = client.calls[1]["messages"][-1]
        assert tool_msg["role"] == "tool" and json.loads(tool_msg["content"])["error"]["type"] == "invalid_argument"

    def test_empty_arguments_default_to_object(self):
        provider = OpenAIProvider(client=FakeOpenAI([o_resp(None, [("c1", "list_files", "")], "tool_calls")]))
        provider.add_user_message("q")
        (call,) = provider.complete().tool_calls
        assert call.arguments == {} and call.parse_error is None

    def test_finish_reason_mapping_and_reset_keeps_system_prompt(self):
        for finish, expected in [("stop", "end"), ("length", "max_tokens"), ("content_filter", "refusal")]:
            p = OpenAIProvider(client=FakeOpenAI([o_resp("x", finish=finish)]))
            p.add_user_message("q")
            assert p.complete().stop_reason == expected
        p.reset()
        assert p.messages == [{"role": "system", "content": lfa.SYSTEM_PROMPT}]


# ----------------------------------------------------------------------------- config + CLI helpers

ALL_PROVIDER_ENV = sorted(
    {"LLM_PROVIDER"}
    | {v for s in lfa.PROVIDERS.values() for v in (*s.key_envs, s.model_env, s.base_url_env) if v}
)


@pytest.fixture()
def clean_env(monkeypatch):
    """No provider credentials/settings leak in from the developer's real environment."""
    for var in ALL_PROVIDER_ENV:
        monkeypatch.delenv(var, raising=False)


@pytest.mark.usefixtures("clean_env")
class TestProviderSelection:
    def test_no_keys_is_a_friendly_error(self):
        with pytest.raises(lfa.ConfigError, match="No provider configured") as exc:
            lfa.resolve_provider_name()
        assert "ANTHROPIC_API_KEY" in str(exc.value) and "OPENROUTER_API_KEY" in str(exc.value)

    def test_autodetect_follows_registry_order(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        assert lfa.resolve_provider_name() == "openrouter"
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        assert lfa.resolve_provider_name() == "gemini"
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        assert lfa.resolve_provider_name() == "openai"
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        assert lfa.resolve_provider_name() == "anthropic"

    def test_blank_values_do_not_count_as_configured(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")   # .env.example ships empty `KEY=` lines
        monkeypatch.setenv("OPENAI_API_KEY", "")
        with pytest.raises(lfa.ConfigError):
            lfa.resolve_provider_name()

    def test_explicit_beats_env_beats_autodetect(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        assert lfa.resolve_provider_name() == "openai"
        assert lfa.resolve_provider_name("anthropic") == "anthropic"
        assert lfa.resolve_provider_name(" Gemini ") == "gemini"      # case/space tolerant

    def test_unknown_provider(self):
        with pytest.raises(lfa.ConfigError, match="Unknown provider") as exc:
            lfa.resolve_provider_name("bogus")
        assert "ollama" in str(exc.value) and "openrouter" in str(exc.value)

    def test_selected_provider_without_its_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        with pytest.raises(lfa.ConfigError, match="OPENAI_API_KEY"):
            lfa.create_provider("openai")
        with pytest.raises(lfa.ConfigError, match="GEMINI_API_KEY or GOOGLE_API_KEY"):
            lfa.create_provider("gemini")
        with pytest.raises(lfa.ConfigError, match="OPENROUTER_API_KEY"):
            lfa.create_provider("openrouter")

    def test_model_resolution_order(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert lfa.create_provider("openai").model == lfa.DEFAULT_MODELS["openai"]
        monkeypatch.setenv("OPENAI_MODEL", "from-env")
        assert lfa.create_provider("openai").model == "from-env"
        assert lfa.create_provider("openai", "from-flag").model == "from-flag"


@pytest.mark.usefixtures("clean_env")
class TestProviderRegistry:
    def test_registry_is_well_formed(self):
        assert list(lfa.PROVIDERS) == ["anthropic", "openai", "gemini", "openrouter", "ollama"]
        for name, spec in lfa.PROVIDERS.items():
            assert spec.name == name and spec.kind in {"anthropic", "openai_compat"}
            assert spec.default_model and spec.model_env.endswith("_MODEL")
            if spec.key_required:
                assert spec.key_envs
            else:
                assert spec.placeholder_key           # SDK refuses an empty api_key
        assert lfa.DEFAULT_MODELS == {n: s.default_model for n, s in lfa.PROVIDERS.items()}

    @pytest.mark.parametrize("name, key_var, base_url", [
        ("openai", "OPENAI_API_KEY", "https://api.openai.com/v1"),
        ("gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai"),
        ("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
    ])
    def test_compat_providers_wire_key_and_base_url(self, monkeypatch, name, key_var, base_url):
        monkeypatch.setenv(key_var, "secret-key")
        provider = lfa.create_provider(name)
        assert isinstance(provider, lfa.OpenAIProvider) and provider.name == name
        assert provider.client.api_key == "secret-key"
        assert str(provider.client.base_url).rstrip("/") == base_url
        assert provider.model == lfa.DEFAULT_MODELS[name]

    def test_base_url_override_via_env(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        monkeypatch.setenv("OPENROUTER_BASE_URL", "https://proxy.example.com/v1")
        assert str(lfa.create_provider("openrouter").client.base_url).startswith("https://proxy.example.com/v1")

    def test_gemini_accepts_google_api_key_but_prefers_gemini_api_key(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "google")
        assert lfa.create_provider("gemini").client.api_key == "google"
        monkeypatch.setenv("GEMINI_API_KEY", "gemini")
        assert lfa.create_provider("gemini").client.api_key == "gemini"

    def test_openai_tools_can_strip_additional_properties(self):
        import tool_schemas

        for tool in tool_schemas.openai_tools(strip_additional_properties=True):
            assert "additionalProperties" not in tool["function"]["parameters"]
            assert tool["function"]["parameters"]["required"]       # everything else intact
        for tool in tool_schemas.openai_tools():                    # default is unchanged
            assert tool["function"]["parameters"]["additionalProperties"] is False

    def test_only_gemini_strips_schema_keyword(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        monkeypatch.setenv("OPENAI_API_KEY", "k")

        def keeps_keyword(p):
            return all("additionalProperties" in t["function"]["parameters"] for t in p.tools)

        assert not keeps_keyword(lfa.create_provider("gemini"))
        assert keeps_keyword(lfa.create_provider("openrouter")) and keeps_keyword(lfa.create_provider("openai"))

    def test_ollama_needs_no_key(self):
        provider = lfa.create_provider("ollama")
        assert provider.name == "ollama" and provider.model == "qwen3:8b"
        assert provider.client.api_key == "ollama"                  # placeholder
        assert str(provider.client.base_url).rstrip("/") == "http://localhost:11434/v1"

    def test_ollama_overrides_and_bare_host_gets_v1(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://gpu-box:11434")   # forgot the /v1
        monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
        provider = lfa.create_provider("ollama")
        assert str(provider.client.base_url).rstrip("/") == "http://gpu-box:11434/v1"
        assert provider.model == "llama3.2"
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://gpu-box:11434/custom/v1")
        assert "/custom/v1" in str(lfa.create_provider("ollama").client.base_url)

    def test_ollama_cloud_key_is_used_when_given(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "cloud-key")
        assert lfa.create_provider("ollama").client.api_key == "cloud-key"

    def test_ollama_autodetected_only_when_configured(self, monkeypatch):
        with pytest.raises(lfa.ConfigError):
            lfa.resolve_provider_name()                    # nothing set -> not silently chosen
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        assert lfa.resolve_provider_name() == "ollama"

    def test_describe_providers(self, monkeypatch):
        rows = {r["name"]: r for r in lfa.describe_providers()}
        assert set(rows) == set(lfa.PROVIDERS)
        assert rows["anthropic"]["ready"] is False and rows["ollama"]["ready"] is True
        assert rows["ollama"]["key"] == "(none needed)" and "GOOGLE_API_KEY" in rows["gemini"]["key"]
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        assert {r["name"]: r for r in lfa.describe_providers()}["openrouter"]["ready"] is True


class TestOpenAICompatQuirks:
    def test_missing_tool_call_ids_are_generated_and_consistent(self):
        client = FakeOpenAI([
            o_resp(None, [("", "list_files", '{"directory": "."}'), (None, "list_files", '{"directory": "."}')], "tool_calls"),
            o_resp("ok"),
        ])
        provider = OpenAIProvider(client=client, name="ollama")
        Agent(provider).run("q")
        msgs = client.calls[1]["messages"]
        call_ids = [c["id"] for c in msgs[2]["tool_calls"]]
        assert all(call_ids) and len(set(call_ids)) == 2                       # non-empty, unique
        assert [m["tool_call_id"] for m in msgs if m["role"] == "tool"] == call_ids

    def test_dict_arguments_are_accepted(self):
        calls = [NS(id="c1", type="function", function=NS(name="list_files", arguments={"directory": "."}))]
        client = FakeOpenAI([NS(choices=[NS(message=NS(content="", tool_calls=calls), finish_reason="tool_calls")])])
        provider = OpenAIProvider(client=client)
        provider.add_user_message("q")
        (call,) = provider.complete().tool_calls
        assert call.arguments == {"directory": "."} and call.parse_error is None
        assert provider.messages[-1]["tool_calls"][0]["function"]["arguments"] == '{"directory": "."}'

    def test_local_models_that_report_stop_with_tool_calls_still_loop(self, sandbox):
        # Some Ollama models answer finish_reason="stop" even when they emitted tool calls.
        client = FakeOpenAI([
            o_resp(None, [("c1", "list_files", '{"directory": "."}')], finish="stop"),
            o_resp("done"),
        ])
        result = Agent(OpenAIProvider(client=client, name="ollama")).run("q")
        assert result.text == "done" and len(result.tool_calls) == 1

    def test_default_model_follows_provider_name(self):
        assert OpenAIProvider(client=FakeOpenAI([]), name="gemini").model == "gemini-3.8-flash"
        assert OpenAIProvider(client=FakeOpenAI([])).model == "gpt-4o-mini"


class TestErrorHints:
    class Boom(Exception):
        def __init__(self, status=None):
            super().__init__("boom")
            self.status_code = status

    def provider(self, name, model="m"):
        return NS(name=name, model=model)

    def test_ollama_connection_error(self):
        APIConnectionError = type("APIConnectionError", (Exception,), {})
        hint = lfa.error_hint(self.provider("ollama", "qwen3:8b"), APIConnectionError("Connection error."))
        assert "ollama serve" in hint and "ollama pull qwen3:8b" in hint

    def test_bad_key_names_the_variables(self):
        assert "GEMINI_API_KEY / GOOGLE_API_KEY" in lfa.error_hint(self.provider("gemini"), self.Boom(401))

    def test_unknown_model_hints(self):
        assert "vendor/model" in lfa.error_hint(self.provider("openrouter", "nope"), self.Boom(404))
        assert "OPENAI_MODEL" in lfa.error_hint(self.provider("openai", "nope"), self.Boom(404))

    def test_400_on_compat_providers_mentions_tool_support(self):
        assert "tool calling" in lfa.error_hint(self.provider("ollama"), self.Boom(400))
        assert lfa.error_hint(self.provider("anthropic"), self.Boom(400)) is None

    def test_unrelated_errors_have_no_hint_and_unknown_provider_is_safe(self):
        assert lfa.error_hint(self.provider("openai"), RuntimeError("x")) is None
        assert lfa.error_hint(self.provider("scripted"), self.Boom(404))     # no KeyError


class TestCliHelpers:
    def test_summaries(self):
        ok = {"success": True}
        assert "2 file(s)" in lfa.summarize_result("list_files", {**ok, "count": 2, "files": [{"name": "a"}, {"name": "b"}]})
        assert "0 file(s)" == lfa.summarize_result("list_files", {**ok, "count": 0, "files": []})
        assert "120 words" in lfa.summarize_result(
            "read_file", {**ok, "filepath": "a.pdf", "metadata": {"word_count": 120, "format": "pdf", "truncated": True}})
        assert lfa.summarize_result("search_in_file", {**ok, "total_matches": 1, "keyword": "x", "filepath": "a"}).startswith("1 match for")
        assert "created output/a.md" in lfa.summarize_result("write_file", {**ok, "filepath": "output/a.md", "bytes_written": 5})
        assert lfa.summarize_result("read_file", {"success": False, "error": {"type": "not_found", "message": "gone"}}) == "not_found: gone"

    @pytest.mark.parametrize("text, expected", [
        ('{"name": "list_files", "arguments": {"directory": "resumes"}}', True),
        ('```json\n{"name": "read_file", "arguments": {"filepath": "a.txt"}}\n```', True),
        ('{"name": "not_a_tool", "arguments": {}}', False),
        ("I found three resumes.", False),
        ('{"candidates": ["John"]}', False),
        ("[1, 2, 3]", False),
        ("", False),
    ])
    def test_detects_tool_call_written_as_text(self, text, expected):
        assert lfa.looks_like_unexecuted_tool_call(text) is expected

    def test_format_arguments_elides_long_strings(self):
        out = lfa.format_arguments({"filepath": "a.txt", "content": "z" * 500})
        assert "filepath='a.txt'" in out and "(500 chars)" in out and len(out) < 150
        assert lfa.format_arguments(None) == ""

    def test_missing_key_exits_cleanly(self, monkeypatch, capsys, tmp_path, clean_env):
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
        assert lfa.main(["-q", "hi", "--root", str(tmp_path)]) == 2
        assert "Configuration error" in capsys.readouterr().out

    def test_list_providers_flag(self, monkeypatch, capsys, clean_env):
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        monkeypatch.setenv("COLUMNS", "200")          # rich wraps at 80 columns under capture
        assert lfa.main(["--list-providers"]) == 0
        out = capsys.readouterr().out
        for name in ("anthropic", "openai", "gemini", "openrouter", "ollama"):
            assert name in out
        assert "gemini-3.8-flash" in out and "(none needed)" in out

    def test_provider_flag_accepts_every_registered_provider(self):
        parser = lfa.build_parser()
        for name in lfa.PROVIDERS:
            assert parser.parse_args(["--provider", name]).provider == name
        with pytest.raises(SystemExit):
            parser.parse_args(["--provider", "bogus"])


# ----------------------------------------------------------------------------- end-to-end on shipped data

def test_example_query_find_python_resumes(real_project, tmp_path):
    """A scripted 'model' that behaves like a good one on 'Find resumes mentioning Python'."""
    from fs_tools import list_files

    names = [f["path"] for f in list_files("resumes")]
    provider = ScriptedProvider([
        Turn("", [tc("l", "list_files", directory="resumes")], "tool_use"),
        Turn("", [tc(f"s{i}", "search_in_file", filepath=p, keyword="Python") for i, p in enumerate(names)], "tool_use"),
        Turn("summary", [], "end"),
    ])
    result = Agent(provider).run("Find resumes mentioning Python experience")
    assert result.iterations == 3 and len(result.tool_calls) == 1 + len(names)
    counts = {c[1]["filepath"]: json.loads(r.content)["total_matches"]
              for c, r in zip(result.tool_calls[1:], provider.result_batches[1])}
    assert counts["resumes/resume_david_okafor.docx"] == 0
    assert counts["resumes/resume_john_doe.pdf"] > 0
