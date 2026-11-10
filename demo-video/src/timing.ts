/**
 * Timing for the whole video.
 *
 * Scene lengths come from your recorded voiceover (src/voiceoverClips.ts, written by
 * scripts/prepare_voiceover.py): each scene lasts as long as its narration plus a short hold. A scene
 * with no recording falls back to DEFAULT_SECONDS. The total length is derived (scenes are joined
 * with short cross-fades that overlap by TRANSITION_FRAMES), and every scene is also registered as
 * its own composition in Studio (folder "Scenes").
 */
import voiceover from "./voiceoverClips.ts";

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
export const TRANSITION_FRAMES = 12;

export const SCENE_ORDER = [
  "title", //      0. what this is + the resume corpus
  "tools", //      1. Part A: the four tools, the sandbox, the JSON Schema the model sees
  "tests", //      2. the test suite
  "cli", //        3. providers + starting the assistant
  "readAll", //    4. "Read all resumes in the resumes folder"
  "findPython", // 5. "Find resumes mentioning Python experience"
  "summary", //    6. "Create a summary file for resume_john_doe.pdf"
  "overwrite", //  7. the same request again: overwrite protection
  "sandbox", //    8. path traversal is blocked
  "outro", //      9. architecture + repo
] as const;

export type SceneKey = (typeof SCENE_ORDER)[number];

/** Lengths (seconds) used for a scene that has no voiceover clip yet. */
const DEFAULT_SECONDS: Record<SceneKey, number> = {
  title: 10,
  tools: 24,
  tests: 12,
  cli: 10,
  readAll: 26,
  findPython: 24,
  summary: 16,
  overwrite: 12,
  sandbox: 10,
  outro: 8,
};

/** Picture held after the last spoken word, before the cross-fade to the next scene. */
const HOLD_SECONDS = 0.8;
/** A scene never goes below this, even for a very short clip. */
const MIN_SECONDS = 5;

type Clip = { file: string; seconds: number; speechStart: number; speechEnd: number; pauses: [number, number][] };
const clips = voiceover as unknown as Partial<Record<SceneKey, Clip>>;

export const hasClip = (key: SceneKey): boolean => clips[key] !== undefined;

export const SCENE_SECONDS: Record<SceneKey, number> = Object.fromEntries(
  SCENE_ORDER.map((key) => {
    const clip = clips[key];
    return [key, clip ? Math.max(MIN_SECONDS, Math.round((clip.seconds + HOLD_SECONDS) * 10) / 10) : DEFAULT_SECONDS[key]];
  }),
) as Record<SceneKey, number>;

export const sceneFrames = (key: SceneKey): number => Math.round(SCENE_SECONDS[key] * FPS);

/** Sum of all scenes minus the cross-fade overlaps between them. */
export const TOTAL_FRAMES =
  SCENE_ORDER.reduce((sum, key) => sum + sceneFrames(key), 0) -
  TRANSITION_FRAMES * (SCENE_ORDER.length - 1);

/** Frame at which a scene starts on the main timeline (scenes overlap by TRANSITION_FRAMES). */
export const sceneStart = (key: SceneKey): number => {
  let frame = 0;
  for (const k of SCENE_ORDER) {
    if (k === key) return frame;
    frame += sceneFrames(k) - TRANSITION_FRAMES;
  }
  return frame;
};

/** One clip per scene, each starting exactly when its scene starts (from voiceoverClips.ts). */
export const SCENE_VOICEOVERS: Partial<Record<SceneKey, string>> = Object.fromEntries(
  SCENE_ORDER.flatMap((key) => (clips[key] ? [[key, clips[key].file]] : [])),
);

/** Optional single file for the whole video instead (saved as public/<name>), played from frame 0. */
export const VOICEOVER_FILE: string | null = null;

/**
 * Beats: moments inside a scene (seconds from the scene start) that line up with what the narrator
 * says. They were read off the recorded clips (the pauses between sentences) and only apply to those
 * recordings. If you re-record, re-check them: scrub the scene in Studio next to the audio.
 *
 *   stepsAt   when the first tool call appears (default: right after the request is typed)
 *   answerAt  when the model's final answer appears
 *   fileAt    when the written file's preview appears
 */
const BEATS = {
  // "Part A is fs_tools: read_file, list_files, write_file and search_in_file."
  // then "Every path is resolved inside the project folder..." / "And each tool is described once, as a JSON Schema..."
  tools: { namesAt: 0.9, sandboxAt: 7.2, schemaAt: 12.4 },
  // "...a hundred and forty-seven tests." / "They run offline: ..."
  tests: { summaryAt: 3.0, noteAt: 3.7 },
  // "...it answers with a summary table of the eight candidates."
  readAll: { answerAt: 12.8 },
  // "Then it ranks what it found: real experience first, passing mentions after..."
  findPython: { answerAt: 9.9 },
  // "...then calls write_file, which creates the file..." / "On the right is what it actually wrote."
  summary: { answerAt: 9.6, fileAt: 11.0 },
  // "write_file refuses to overwrite by default and returns an error." / "...picks a new filename."
  overwrite: { answerAt: 10.4 },
  // "The tool refuses, and the model reports exactly what it returned."
  sandbox: { stepsAt: 6.0, answerAt: 8.6 },
  // "a request, a model, a validated tool call, and sandboxed file access." / "The code and the tests are on GitHub."
  outro: { boxesAt: [1.6, 2.4, 3.0, 3.9, 5.6], repoAt: 8.0 },
} as const;

/** Beats for a scene, or undefined when the scene has no recording (the beats would not fit). */
export const beats = <K extends keyof typeof BEATS>(key: K): (typeof BEATS)[K] | undefined =>
  hasClip(key as SceneKey) ? BEATS[key] : undefined;
