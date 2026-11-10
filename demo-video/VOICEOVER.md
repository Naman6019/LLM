# Voiceover script

Draft narration for each scene, written against what the video shows. Times and word budgets come
from `npm run timing` (about 2.5 words per second); re-run it after you change `src/timing.ts`.

Current length: **2:28**, about 370 words in total.

| # | Scene | Starts | Length | Words |
|---|---|---|---|---|
| 1 | `title` | 0:00 | 9.6 s | ~24 |
| 2 | `tools` | 0:09.6 | 23.6 s | ~59 |
| 3 | `tests` | 0:33.2 | 11.6 s | ~29 |
| 4 | `cli` | 0:44.8 | 9.6 s | ~24 |
| 5 | `readAll` | 0:54.4 | 25.6 s | ~64 |
| 6 | `findPython` | 1:20.0 | 23.6 s | ~59 |
| 7 | `summary` | 1:43.6 | 15.6 s | ~39 |
| 8 | `overwrite` | 1:59.2 | 11.6 s | ~29 |
| 9 | `sandbox` | 2:10.8 | 9.6 s | ~24 |
| 10 | `outro` | 2:20.4 | 8.0 s | ~20 |

> The terminal scenes replay a **real run** captured in `src/data/demo-data.json` (model, answers and
> tool calls are not invented). If you re-capture, the answers will differ a little, so check that the
> lines below still describe what appears on screen, especially scene 6.

---

### 1. title (~24 words)
This is an LLM-powered file system assistant: four file tools, plus an agent that lets a model call
them on these eight resumes.

*On screen: title, the real `resumes/` listing (3 PDF, 3 DOCX, 2 TXT).*

### 2. tools (~59 words)
Part A is `fs_tools`: `read_file`, `list_files`, `write_file` and `search_in_file`. Each returns a
structured result, and failures come back as data the model can read. Every path is resolved inside
the project folder, so the model can't wander outside it. And each tool is described once, as a JSON
Schema, which the model's arguments are checked against.

*On screen, in three beats: the four function signatures (highlighted one at a time), the `_resolve`
sandbox check, the JSON Schema with the `required` line highlighted.*

### 3. tests (~29 words)
The whole thing is covered by a hundred and forty-seven tests. They run offline: the LLM clients are
replaced by scripted fakes, so no API key is needed.

*On screen: `pytest` output and the pass count. If you re-run the capture and the count changes,
say the new number (it is read from the capture automatically).*

### 4. cli (~24 words)
Part B is the assistant. It supports five providers: Anthropic, OpenAI, Gemini, OpenRouter and
Ollama. For this demo I'm using a hosted model through Ollama.

*On screen: `--list-providers`, then the assistant starting up.*

### 5. readAll (~64 words)
First request: read all the resumes in the resumes folder. I didn't tell it which tools to use. It
called `list_files` once, then `read_file` on every resume. Each result goes back to the model, and
it answers with a summary table of the eight candidates. This loop is the same for every provider.

*On screen: the typed request, the tool calls and results streaming in, then the answer table.*

### 6. findPython (~59 words)
Next: find resumes mentioning Python experience. It lists the folder, then searches all eight files
in one round of parallel calls. Then it ranks what it found: real experience first, passing mentions
after, and the one resume that never mentions Python. Everything it says comes from those tool
results.

*On screen: eight `search_in_file` calls with match counts, then the ranked answer.*

### 7. summary (~39 words)
Now: create a summary file for `resume_john_doe.pdf`. The model reads the PDF, then calls
`write_file`, which creates the file in the output folder. On the right is what it actually wrote.

*On screen: the calls, the model's answer, and the written file's contents.*

### 8. overwrite (~29 words)
Ask for the same thing again, and the file already exists. `write_file` refuses to overwrite by
default and returns an error. The model reads it, and picks a new filename.

*On screen: the red `file_exists` error, then a second `write_file` that succeeds.*

### 9. sandbox (~24 words)
Finally, the sandbox. I explicitly ask the model to read a file outside the project. The tool
refuses, and the model reports exactly what it returned.

*On screen: `read_file` on `../../secrets.txt`, the `outside_sandbox` error.*

### 10. outro (~20 words)
That's the whole loop: a request, a model, a validated tool call, and sandboxed file access. The
code and the tests are on GitHub.

*On screen: the architecture strip and the repository URL.*

---

## Recording tips

- Record in a quiet room, one scene at a time if you like; pause briefly before each line.
- Read at a relaxed pace; if you run long, lengthen that scene in `src/timing.ts` rather than rushing.
- Two ways to put the audio in (see the comments in `src/timing.ts`):
  - one file for the whole video: save it as `public/voiceover.mp3` and set `VOICEOVER_FILE`;
  - one file per scene: save as `public/vo/<scene>.mp3` and list them in `SCENE_VOICEOVERS`. Each
    clip then starts exactly when its scene does.
- Scrub in Studio (`npm run dev`) to check the words line up with the visuals, then render.
