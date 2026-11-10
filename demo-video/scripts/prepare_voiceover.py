"""Turn raw voiceover recordings into trimmed, level-matched clips the video can use.

For each scene it finds the recording (vo-source/<scene>.mp4|m4a|mp3|wav|mov|mkv), detects where the
speech starts and ends, trims the silence around it (keeping a short lead-in and tail), normalises the
loudness (two-pass EBU R128, -16 LUFS, which is typical for video), and writes public/vo/<scene>.m4a.
It also writes src/voiceoverClips.ts (generated data), which src/timing.ts reads to set every scene's length.

    python demo-video/scripts/prepare_voiceover.py

Needs `ffmpeg` on PATH (a full build: Remotion's bundled copy lacks some filters).
Originals are never modified. Re-run it any time you re-record a clip.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # demo-video/
SOURCE_DIR = ROOT / "vo-source"
OUT_DIR = ROOT / "public" / "vo"
DATA_FILE = ROOT / "src" / "voiceoverClips.ts"

SCENES = ["title", "tools", "tests", "cli", "readAll", "findPython", "summary", "overwrite", "sandbox", "outro"]
EXTENSIONS = (".mp4", ".m4a", ".mp3", ".wav", ".mov", ".mkv")

SILENCE_DB = "-38dB"      # below this counts as silence
MIN_SILENCE = 0.3         # seconds of silence that count as a pause
LEAD = 0.45               # seconds of lead-in kept before the first word
TAIL = 0.5                # seconds kept after the last word
TARGET_LUFS = -16.0


def run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg failed:\n{' '.join(cmd)}\n{proc.stderr[-1500:]}")
    return proc.stderr


def find_source(scene: str) -> Path | None:
    for ext in EXTENSIONS:
        candidate = SOURCE_DIR / f"{scene}{ext}"
        if candidate.exists():
            return candidate
    return None


def analyse(src: Path) -> dict:
    log = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-vn", "-af",
               f"silencedetect=n={SILENCE_DB}:d={MIN_SILENCE}", "-f", "null", "-"])
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", log)
    duration = int(dur[1]) * 3600 + int(dur[2]) * 60 + float(dur[3])
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    silences = [(st, ends[i] if i < len(ends) else duration) for i, st in enumerate(starts)]
    speech_start = silences[0][1] if silences and silences[0][0] < 0.05 else 0.0
    speech_end = silences[-1][0] if silences and silences[-1][1] >= duration - 0.05 else duration
    pauses = [(a, b) for a, b in silences if a >= speech_start and b <= speech_end + 0.01]
    return {"duration": duration, "speech_start": speech_start, "speech_end": speech_end, "pauses": pauses}


def loudness(src: Path, start: float, length: float) -> dict:
    log = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
               "-vn", "-af", f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    return json.loads(log[log.rindex("{"): log.rindex("}") + 1])


def main() -> int:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH. Install a full build (e.g. `winget install Gyan.FFmpeg`).")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data: dict[str, dict] = {}
    missing: list[str] = []

    for scene in SCENES:
        src = find_source(scene)
        if src is None:
            missing.append(scene)
            continue
        a = analyse(src)
        trim_start = max(0.0, a["speech_start"] - LEAD)
        trim_end = min(a["duration"], a["speech_end"] + TAIL)
        length = trim_end - trim_start
        m = loudness(src, trim_start, length)
        out = OUT_DIR / f"{scene}.m4a"
        norm = (f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
                f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
        fades = f"afade=t=in:st=0:d=0.04,afade=t=out:st={max(0.0, length - 0.3):.3f}:d=0.3"
        run(["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(src), "-ss", f"{trim_start:.3f}", "-t", f"{length:.3f}",
             "-vn", "-af", f"{norm},{fades}", "-ar", "48000", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
        data[scene] = {
            "file": f"vo/{scene}.m4a",
            "seconds": round(length, 2),
            # speech start/end and pauses, in seconds from the start of the trimmed clip (= scene start)
            "speechStart": round(a["speech_start"] - trim_start, 2),
            "speechEnd": round(a["speech_end"] - trim_start, 2),
            "pauses": [[round(p - trim_start, 2), round(q - trim_start, 2)] for p, q in a["pauses"]],
            "loudnessBefore": round(float(m["input_i"]), 1),
        }
        print(f"{scene:<11} {a['duration']:>6.2f}s -> {length:>6.2f}s   speech {data[scene]['speechStart']:.2f}-{data[scene]['speechEnd']:.2f}"
              f"   {m['input_i']} LUFS -> {TARGET_LUFS}")

    header = "// Generated by scripts/prepare_voiceover.py. Do not edit by hand; re-run the script after re-recording.\n"
    DATA_FILE.write_text(f"{header}export default {json.dumps(data, indent=2)};\n", encoding="utf-8", newline="\n")
    print(f"\nwrote {DATA_FILE.relative_to(ROOT)} ({len(data)} clips)")
    if missing:
        print(f"no recording found for: {', '.join(missing)} (those scenes keep their default length)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
