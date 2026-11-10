/**
 * Prints when each scene starts and ends (mm:ss) plus a word budget for the voiceover.
 *
 *   npm run timing
 *
 * Reads src/timing.ts, so it stays correct after you retime scenes. Needs Node 22.18+ (runs
 * TypeScript directly).
 */
import { FPS, SCENE_ORDER, TOTAL_FRAMES, TRANSITION_FRAMES, sceneFrames } from "../src/timing.ts";

const WORDS_PER_SECOND = 2.5; // ~150 words/min, a comfortable narration pace

const mmss = (frames: number): string => {
  const s = frames / FPS;
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(1).padStart(4, "0")}`;
};

let start = 0;
const rows = SCENE_ORDER.map((key, i) => {
  const frames = sceneFrames(key);
  // Scenes overlap by TRANSITION_FRAMES (cross-fade); the visible "own" time is the span between
  // this scene's start and the next scene's start.
  const own = i < SCENE_ORDER.length - 1 ? frames - TRANSITION_FRAMES : frames;
  const row = { key, start, end: start + frames, seconds: own / FPS, words: Math.round((own / FPS) * WORDS_PER_SECOND) };
  start += own;
  return row;
});

console.log("scene".padEnd(12), "starts".padEnd(8), "ends".padEnd(8), "secs".padEnd(6), "~words");
console.log("-".repeat(46));
for (const r of rows) {
  console.log(r.key.padEnd(12), mmss(r.start).padEnd(8), mmss(r.end).padEnd(8), r.seconds.toFixed(1).padEnd(6), r.words);
}
console.log("-".repeat(46));
console.log(`total ${mmss(TOTAL_FRAMES)}  (${TOTAL_FRAMES} frames @ ${FPS} fps)  ~${Math.round((TOTAL_FRAMES / FPS) * WORDS_PER_SECOND)} words`);
