"""tool_schemas -- provider-neutral tool definitions + a safe dispatcher.

``TOOL_SPECS`` is the single source of truth for what the LLM is told about each tool
(name, description, JSON Schema).  ``anthropic_tools()`` / ``openai_tools()`` project it
into each vendor's wire format, and ``execute_tool()`` is the one place where model-
supplied arguments are validated and routed to ``fs_tools``.

Everything the model sends is untrusted input: unknown tools, missing/extra/ill-typed
arguments all produce a normal error result (never an exception) that the model can read
and correct on its next turn.
"""

from __future__ import annotations

from typing import Any, Callable

import fs_tools

# --------------------------------------------------------------------------- #
# Specs
# --------------------------------------------------------------------------- #

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "list_files",
        "description": (
            "List the files in a directory with metadata (name, relative path, size in bytes, "
            "modified date, extension). Non-recursive. Use this first to discover which resumes "
            "exist before reading them. Optionally filter by file extension."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory relative to the project root, e.g. 'resumes' or 'output'.",
                },
                "extension": {
                    "type": "string",
                    "description": "Optional extension filter, with or without the dot: 'pdf', '.docx', '.txt'. Case-insensitive.",
                },
            },
            "required": ["directory"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read a resume file (PDF, DOCX or TXT) and return its extracted text plus metadata "
            "(format, size, modified date, word count, page count for PDFs). Very long documents "
            "are truncated; check metadata.truncated."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path relative to the project root, e.g. 'resumes/resume_john_doe.pdf'.",
                },
                "max_chars": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional cap on returned characters (default 20000).",
                },
            },
            "required": ["filepath"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_in_file",
        "description": (
            "Search ONE file (PDF, DOCX or TXT) for a keyword, case-insensitively, and return each "
            "match with its line number and surrounding context. total_matches == 0 means the "
            "keyword is absent. To search many resumes, call this once per file (calls can be made in parallel)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path relative to the project root."},
                "keyword": {"type": "string", "description": "Literal text to find (not a regex), e.g. 'Python'."},
                "context_chars": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Characters of context on each side of a match (default 80).",
                },
                "max_matches": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Maximum matches to return (default 20); total_matches still reports the true count.",
                },
                "whole_word": {
                    "type": "boolean",
                    "description": "Match whole words only, so 'Java' does not match 'JavaScript' (default false).",
                },
            },
            "required": ["filepath", "keyword"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write text to a file, creating parent directories if needed. Only .txt, .md, .json, .csv "
            "and .log are allowed. Refuses to overwrite an existing file unless overwrite=true, so pick a "
            "new filename unless the user explicitly asked to replace one. Save generated output (summaries, "
            "reports) under 'output/'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Destination relative to the project root, e.g. 'output/john_doe_summary.md'.",
                },
                "content": {"type": "string", "description": "The full text to write."},
                "overwrite": {
                    "type": "boolean",
                    "description": "Replace the file if it exists (default false).",
                },
            },
            "required": ["filepath", "content"],
            "additionalProperties": False,
        },
    },
]

_SPEC_BY_NAME: dict[str, dict[str, Any]] = {spec["name"]: spec for spec in TOOL_SPECS}


# --------------------------------------------------------------------------- #
# Vendor projections
# --------------------------------------------------------------------------- #

def anthropic_tools() -> list[dict[str, Any]]:
    """Tool definitions in the Anthropic Messages API format."""
    return [
        {"name": s["name"], "description": s["description"], "input_schema": s["parameters"]}
        for s in TOOL_SPECS
    ]


def openai_tools(strip_additional_properties: bool = False) -> list[dict[str, Any]]:
    """Tool definitions in the OpenAI Chat Completions function-calling format.

    ``strip_additional_properties`` removes the advisory ``additionalProperties`` keyword for
    backends that only accept a restricted JSON-Schema subset (used for Gemini).  Nothing is
    lost: ``execute_tool`` rejects unknown arguments regardless of what the model was told.
    """
    def parameters(schema: dict[str, Any]) -> dict[str, Any]:
        if not strip_additional_properties:
            return schema
        return {k: v for k, v in schema.items() if k != "additionalProperties"}

    return [
        {
            "type": "function",
            "function": {"name": s["name"], "description": s["description"], "parameters": parameters(s["parameters"])},
        }
        for s in TOOL_SPECS
    ]


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

def _list_files_tool(directory: str, extension: str | None = None) -> dict[str, Any]:
    """Adapter: fs_tools.list_files returns a bare list, tool results are always dicts."""
    files = fs_tools.list_files(directory, extension)
    result: dict[str, Any] = {"success": True, "directory": directory, "count": len(files), "files": files}
    if not files and extension and extension.strip():
        # A silent empty list invites the model to conclude "nothing there". Say what IS there so
        # it can fix the filter (the usual mistake: several extensions in one string).
        present = fs_tools.list_files(directory)
        if present:
            kinds = sorted({f["extension"] or "(none)" for f in present})
            result["note"] = (
                f"No files matched extension '{extension}', but the directory has {len(present)} file(s) "
                f"with extensions: {', '.join(kinds)}. The filter accepts ONE extension (e.g. 'pdf'); "
                "omit it to list everything."
            )
    return result


_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "list_files": fs_tools.safe_tool(_list_files_tool),
    "read_file": fs_tools.read_file,
    "search_in_file": fs_tools.search_in_file,
    "write_file": fs_tools.write_file,
}

_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "boolean": (bool,),
}


def _validate(spec: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    """Return a human-readable problem with ``arguments`` or None if they are fine."""
    schema = spec["parameters"]
    props = schema["properties"]
    missing = [k for k in schema.get("required", []) if k not in arguments]
    if missing:
        return f"Missing required argument(s): {', '.join(missing)}."
    unknown = [k for k in arguments if k not in props]
    if unknown:
        return f"Unknown argument(s): {', '.join(unknown)}. Valid: {', '.join(props)}."
    for key, value in arguments.items():
        expected = props[key]["type"]
        ok = isinstance(value, _JSON_TYPES[expected])
        if expected == "integer" and isinstance(value, bool):  # bool is an int subclass in Python
            ok = False
        if not ok:
            return f"Argument '{key}' must be of type {expected}, got {type(value).__name__}."
    return None


def execute_tool(name: str, arguments: Any) -> dict[str, Any]:
    """Validate and run one tool call. Always returns a result dict; never raises."""
    spec = _SPEC_BY_NAME.get(name)
    if spec is None:
        return _bad_call("unknown_tool", f"Unknown tool '{name}'. Available: {', '.join(_SPEC_BY_NAME)}.")
    if not isinstance(arguments, dict):
        return _bad_call("invalid_argument", "Tool arguments must be a JSON object.")
    problem = _validate(spec, arguments)
    if problem:
        return _bad_call("invalid_argument", problem)
    return _REGISTRY[name](**arguments)


def _bad_call(error_type: str, message: str) -> dict[str, Any]:
    return {"success": False, "error": {"type": error_type, "message": message}}
