"""Tests for tool_schemas: vendor projections and the validating dispatcher."""

from __future__ import annotations

import fs_tools
import tool_schemas as ts


def err(result: dict) -> str:
    assert result["success"] is False
    return result["error"]["type"]


class TestProjections:
    def test_every_tool_has_a_registry_entry_and_valid_schema(self):
        names = [s["name"] for s in ts.TOOL_SPECS]
        assert names == ["list_files", "read_file", "search_in_file", "write_file"]
        assert set(names) == set(ts._REGISTRY)
        for spec in ts.TOOL_SPECS:
            schema = spec["parameters"]
            assert schema["type"] == "object" and schema["additionalProperties"] is False
            assert set(schema["required"]) <= set(schema["properties"])
            assert spec["description"]

    def test_schema_params_match_python_signatures(self):
        import inspect

        py = {
            "read_file": fs_tools.read_file, "search_in_file": fs_tools.search_in_file,
            "write_file": fs_tools.write_file, "list_files": fs_tools.list_files,
        }
        for spec in ts.TOOL_SPECS:
            sig = set(inspect.signature(py[spec["name"]]).parameters)
            assert set(spec["parameters"]["properties"]) == sig, spec["name"]

    def test_anthropic_format(self):
        tools = ts.anthropic_tools()
        assert {"name", "description", "input_schema"} == set(tools[0])
        assert tools[1]["input_schema"] is ts.TOOL_SPECS[1]["parameters"]

    def test_openai_format(self):
        tools = ts.openai_tools()
        assert tools[0]["type"] == "function"
        assert {"name", "description", "parameters"} == set(tools[0]["function"])


class TestExecuteTool:
    def test_routes_to_each_tool(self, sandbox):
        listed = ts.execute_tool("list_files", {"directory": "resumes", "extension": "pdf"})
        assert listed["success"] and listed["count"] == 1 and listed["files"][0]["name"] == "resume_john_doe.pdf"
        assert ts.execute_tool("read_file", {"filepath": "resumes/resume_alex_chen.txt"})["success"]
        found = ts.execute_tool("search_in_file", {"filepath": "resumes/resume_alex_chen.txt", "keyword": "react"})
        assert found["success"] and found["total_matches"] >= 1
        wrote = ts.execute_tool("write_file", {"filepath": "output/x.txt", "content": "hi"})
        assert wrote["success"] and (sandbox / "output/x.txt").exists()

    def test_list_files_explains_an_empty_filter_result(self, sandbox):
        # Real failure seen with a small local model: it passed 'pdf,docx' as one extension.
        r = ts.execute_tool("list_files", {"directory": "resumes", "extension": "pdf,docx"})
        assert r["success"] and r["count"] == 0
        assert "3 file(s)" in r["note"] and ".docx" in r["note"] and "ONE extension" in r["note"]

    def test_list_files_has_no_note_when_nothing_to_explain(self, sandbox):
        assert "note" not in ts.execute_tool("list_files", {"directory": "resumes", "extension": "pdf"})
        assert "note" not in ts.execute_tool("list_files", {"directory": "resumes"})
        (sandbox / "empty").mkdir()
        assert "note" not in ts.execute_tool("list_files", {"directory": "empty", "extension": "pdf"})

    def test_list_files_errors_become_envelopes(self, sandbox):
        r = ts.execute_tool("list_files", {"directory": "missing"})
        assert err(r) == "not_found"
        assert err(ts.execute_tool("list_files", {"directory": ".."})) == "outside_sandbox"

    def test_unknown_tool(self):
        r = ts.execute_tool("delete_everything", {})
        assert err(r) == "unknown_tool" and "read_file" in r["error"]["message"]

    def test_missing_required_argument(self):
        r = ts.execute_tool("read_file", {})
        assert err(r) == "invalid_argument" and "filepath" in r["error"]["message"]

    def test_unknown_argument_rejected(self):
        r = ts.execute_tool("read_file", {"filepath": "a.txt", "mode": "rb"})
        assert err(r) == "invalid_argument" and "mode" in r["error"]["message"]

    def test_wrong_type(self):
        r = ts.execute_tool("read_file", {"filepath": 5})
        assert err(r) == "invalid_argument" and "string" in r["error"]["message"]

    def test_bool_is_not_an_integer(self):
        r = ts.execute_tool("read_file", {"filepath": "a.txt", "max_chars": True})
        assert err(r) == "invalid_argument"

    def test_non_dict_arguments(self):
        assert err(ts.execute_tool("read_file", "resumes/a.txt")) == "invalid_argument"
        assert err(ts.execute_tool("read_file", None)) == "invalid_argument"

    def test_overwrite_flag_passthrough(self, sandbox):
        args = {"filepath": "output/x.txt", "content": "1"}
        assert ts.execute_tool("write_file", args)["success"]
        assert err(ts.execute_tool("write_file", args)) == "file_exists"
        assert ts.execute_tool("write_file", {**args, "overwrite": True})["success"]
