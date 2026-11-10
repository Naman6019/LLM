# Demo video (Remotion)

A 2.5-minute demo video for the LLM file system assistant, built with [Remotion](https://www.remotion.dev):
code, terminals and the answers are rendered from React components, with a voiceover fitted to the recorded clips.

## What you are looking at

The terminal scenes are a **replay of a real run, not a screen recording.** The assistant was run
against a real model (see the status line at the bottom of each scene: model, endpoint, tool-call
count, time, capture date), every tool call, tool result and answer was recorded, and the video plays
that recording back with timing and styling added. Nothing in those scenes is written by hand.

Everything else (the code, the test output, the provider list, the resume listing) is also read from the
repository at capture time, not typed in.

If you would rather show the live CLI, record it with a screen recorder instead; `../DEMO_SCRIPT.md`
has that plan.

## Quick start

Requires Node 20.19+ / 22.13+ (22.18+ for `npm run timing`).

```bash
cd demo-video
npm install
npm run dev          # opens Remotion Studio; pick "Demo" or any scene under "Scenes"
```

| Command | What it does |
|---|---|
| `npm run dev` | Remotion Studio: preview, scrub, play |
| `npm run timing` | Prints each scene's start/end time and a voiceover word budget |
| `npm run render` | Renders `out/demo.mp4` (1920x1080, 30 fps) |
| `npm run lint` | ESLint + `tsc` |

## The voiceover

**The narration is not part of this repository.** Without recordings the video renders silently at the
default scene lengths (about 2:28). To make your own narrated version, record the clips and follow the steps
below. Narration drafts are in [`VOICEOVER.md`](VOICEOVER.md). The video is then fitted to the **recorded** clips:

1. Put one recording per scene in `vo-source/` (git-ignored), named after the scene: `title`, `tools`,
   `tests`, `cli`, `readAll`, `findPython`, `summary`, `overwrite`, `sandbox`, `outro`
   (`.mp4`, `.m4a`, `.mp3`, `.wav` all work; a video track is ignored).
2. Run the preparation script from the repository root (needs a full `ffmpeg` on PATH):

   ```bash
   .venv\Scripts\python demo-video\scripts\prepare_voiceover.py     # Windows
   .venv/bin/python demo-video/scripts/prepare_voiceover.py           # macOS / Linux
   ```

   For each clip it finds where the speech starts and ends, trims the silence around it (0.45 s lead-in,
   0.5 s tail), normalises the loudness to -16 LUFS (two-pass, so the ten clips sit at the same level),
   and writes `public/vo/<scene>.m4a` plus `src/voiceoverClips.ts` (generated; do not edit).
3. Every scene's length now follows its clip (narration plus a 0.8 s hold), and each clip starts exactly
   when its scene starts. `npm run timing` prints the resulting times.

Your originals are never modified. Re-run the script after re-recording any clip.

**Beats.** A few on-screen moments are pinned to what the narrator says at that point: when the pass
count appears, when each tool is highlighted, when the model's answer or an error shows up, when the
architecture boxes appear. They live in `BEATS` in `src/timing.ts` as seconds from the scene start, were
read off the recorded clips (the pauses between sentences), and are only valid for those recordings.
After re-recording, scrub the scene in Studio next to the audio and adjust them.

## Re-capturing the real run

Needs the project's Python environment (see the main README) and a configured provider. With an
Ollama cloud key in `.env`, from the repository root:

```bash
# Windows
.venv\Scripts\python demo-video\scripts\capture_demo_data.py --provider ollama --model kimi-k2.6
# macOS / Linux
.venv/bin/python demo-video/scripts/capture_demo_data.py --provider ollama --model kimi-k2.6
```

This writes `src/data/demo-data.json`. Notes:

- It runs the **real agent** for five requests, runs the test suite, and extracts the code shown on screen.
- Each request is retried (up to 6 times) until it demonstrates what its scene is about, for example
  the overwrite scene must really contain a `file_exists` error. That selects among real runs; it
  never edits one. Models are non-deterministic, so answers change between captures.
- `output/` must be empty before running (the script deletes generated files and leaves it empty again).
- `--only summary-again,sandbox` re-captures just those takes; `--skip-pytest` reuses the test output.
- Re-check `VOICEOVER.md` afterwards: the answers are different text each time.

The sandbox request is phrased to ask for the tool call explicitly ("Call read_file with filepath
../../secrets.txt..."). A capable model given just "read ../../secrets.txt" tends to refuse on its
own without calling the tool, which would not show the sandbox doing its job.

## Structure

```
src/
  Root.tsx            registers the "Demo" composition and one composition per scene
  Demo.tsx            joins the scenes with cross-fades (+ the voiceover)
  timing.ts           scene lengths (from the voiceover), transitions, BEATS   <- retime here
  voiceoverClips.ts   generated by scripts/prepare_voiceover.py (do not edit)
  theme.ts            colours and fonts
  scenes/             one file per scene (TakeScene.tsx replays any captured run)
  components/         Terminal, CodeWindow, Markdown, Panel, ...
  lib/                timeline (pacing), markdown parser, syntax highlighter
  data/demo-data.json the captured run + code + test output
scripts/
  capture_demo_data.py   records the real run
  prepare_voiceover.py   trims + normalises the voiceover clips, writes voiceoverClips.ts
  timing-table.ts        prints scene times (npm run timing)
```

## Notes

- Terminal and code text is sized for a 1080p screen. Long model answers scroll as they stream in;
  the answer panel is sized to its content so error lines in the trace stay visible.
- The captured answers are shown as the model wrote them, including its Markdown formatting.
- Remotion is free for individuals and teams of up to 3; see <https://www.remotion.pro/license>.
