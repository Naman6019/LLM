# Demo video script (target 2:30)

Record the terminal (Windows Terminal, large font). Run from the project folder with the venv active
and an API key in `.env`.

| Time | Show | Say |
|---|---|---|
| 0:00 | `ls resumes` / folder view | "8 dummy resumes in PDF, DOCX and TXT. The brief wants an LLM that can read, list, search and write files through tool calling." |
| 0:15 | Open `fs_tools.py` briefly, scroll the 4 functions; `tool_schemas.py` spec | "Part A is four plain Python tools. Each returns a structured result with an error envelope, and every path is sandboxed. `tool_schemas.py` describes them to the model as JSON Schema." |
| 0:40 | `pytest` (or the last line: `144 passed`) | "144 tests cover the tools, the validation, and the exact wire format for the providers, with no API calls." |
| 0:55 | `python llm_file_assistant.py --list-providers`, then `python llm_file_assistant.py` | "Part B: the agent loop. Five providers (Claude, OpenAI, Gemini, OpenRouter, Ollama); I'm using <whichever you record with> here." |
| 1:05 | `Read all resumes in the resumes folder` | Point at the trace: `list_files`, then `read_file` x8. "The model chose these calls itself; I only asked in English." |
| 1:35 | `Find resumes mentioning Python experience` | "It lists the folder, then issues the searches in parallel. Note it separates real experience from 'basic Python' and an intro course." |
| 2:00 | `Create a summary file for resume_john_doe.pdf`, then `type output\john_doe_summary.md` | "`read_file`, then `write_file` creates the file under `output/`." |
| 2:15 | Re-run the same request | "Second time, `write_file` returns `file_exists`. The model reads the error and picks a new filename." |
| 2:25 | `Read ../../secrets.txt` | "Path traversal is blocked by the sandbox and the model reports it." |

Tips: use `/reset` between takes; pass `--provider` to show both vendors if time allows.
Delete generated files in `output/` before recording so the overwrite demo starts clean.
