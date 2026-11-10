import React, { useMemo } from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Background } from "../components/Background";
import { Chapter } from "../components/Chapter";
import { Markdown } from "../components/Markdown";
import { Panel } from "../components/Panel";
import { Trace, Window } from "../components/Terminal";
import { capturedOn, demo } from "../data";
import type { Take } from "../data/types";
import { estimateHeight, parseMarkdown } from "../lib/markdown";
import { buildTimeline } from "../lib/timeline";
import { C, FONT_SANS } from "../theme";

const X = 100;
const W = 1720;
const TOP = 128;
const H = 836;
const GAP = 20;
/** The answer panel is sized to its content, within these bounds; the terminal gets the rest. */
const MIN_LOWER = 232;
const MAX_LOWER = 600;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** One-line, factual description of the recorded run (all numbers come from the capture). */
const RunStrip: React.FC<{ take: Take }> = ({ take }) => {
  const calls = take.events.filter((e) => e.type === "tool_call").length;
  const errors = take.events.filter((e) => e.type === "tool_result" && !e.ok).length;
  const bits = [
    "Replay of a real run",
    `${demo.meta.model} via ${demo.meta.endpoint}`,
    `${calls} tool call${calls === 1 ? "" : "s"}${errors ? ` (${errors} returned an error)` : ""}`,
    `${take.iterations} model round trips`,
    `${take.elapsed_seconds}s`,
    `captured ${capturedOn()}`,
  ];
  return (
    <div
      style={{
        position: "absolute",
        left: X,
        right: X,
        bottom: 30,
        fontFamily: FONT_SANS,
        fontSize: 22,
        color: C.dim,
        display: "flex",
        gap: 14,
        alignItems: "center",
      }}
    >
      <span style={{ width: 10, height: 10, borderRadius: 99, background: C.green }} />
      {bits.join("  ·  ")}
    </div>
  );
};

export const TakeScene: React.FC<{
  take: Take | undefined;
  durationFrames: number;
  tag: string;
  title: string;
  /** Show the file the model wrote next to its answer (summary scene). */
  showFile?: boolean;
  /** Moments (seconds from scene start) pinned to the narration; see BEATS in timing.ts. */
  pins?: { stepsAt?: number; answerAt?: number; fileAt?: number };
}> = ({ take, durationFrames, tag, title, showFile, pins }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const timeline = useMemo(
    () =>
      take
        ? buildTimeline(take, durationFrames, fps, {
            stepsAt: pins?.stepsAt !== undefined ? Math.round(pins.stepsAt * fps) : undefined,
            answerAt: pins?.answerAt !== undefined ? Math.round(pins.answerAt * fps) : undefined,
          })
        : null,
    [take, durationFrames, fps, pins?.stepsAt, pins?.answerAt],
  );

  const file = showFile ? take?.written_file : undefined;
  const answerWidth = file ? 700 : W;
  const answerFont = file ? 23 : 24;
  const lowerHeight = useMemo(() => {
    if (!take) return MIN_LOWER;
    const own = estimateHeight(parseMarkdown(take.answer), answerWidth - 64, answerFont);
    const fileHeight = file ? estimateHeight(parseMarkdown(file.content), W - answerWidth - GAP - 64, 22) : 0;
    return clamp(Math.max(own, fileHeight) + 64, MIN_LOWER, MAX_LOWER);
  }, [take, file, answerWidth, answerFont]);

  if (!take || !timeline) {
    return (
      <AbsoluteFill>
        <Background />
        <Chapter tag={tag} title={title} />
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: C.red, fontFamily: FONT_SANS, fontSize: 40 }}>
          No captured run for this scene. Run scripts/capture_demo_data.py.
        </div>
      </AbsoluteFill>
    );
  }
  if (timeline.overflow && frame === 0) {
    console.warn(`[${tag}] captured run is long for this scene; lengthen it in src/timing.ts`);
  }

  const { answerStart, answerFrames } = timeline;
  const split = interpolate(frame, [answerStart - 6, answerStart + 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const fileStart =
    pins?.fileAt !== undefined ? Math.round(pins.fileAt * fps) : answerStart + Math.round(answerFrames * 0.55);
  const smallTerm = H - GAP - lowerHeight;
  const termHeight = H + (smallTerm - H) * split;

  return (
    <AbsoluteFill>
      <Background />
      <Chapter tag={tag} title={title} />

      <div style={{ position: "absolute", left: X, top: TOP }}>
        <Window title={`llm_file_assistant.py  -  ${demo.meta.provider} / ${demo.meta.model}`} width={W} height={termHeight}>
          <Trace lines={timeline.lines} frame={frame} height={termHeight - 54} />
        </Window>
      </div>

      {split > 0 && (
        <div
          style={{
            position: "absolute",
            left: X,
            top: TOP + termHeight + GAP,
            display: "flex",
            gap: GAP,
            opacity: split,
          }}
        >
          <Panel title="assistant" width={answerWidth} height={lowerHeight}>
            <Markdown
              text={take.answer}
              frame={frame}
              start={answerStart}
              revealFrames={answerFrames}
              height={lowerHeight - 54}
              fontSize={answerFont}
            />
          </Panel>
          {file && (
            <Panel title={file.path} width={W - answerWidth - GAP} height={lowerHeight} color={C.cyan} mono>
              <Markdown
                text={file.content}
                frame={frame}
                start={fileStart}
                revealFrames={Math.max(30, Math.min(Math.round(answerFrames * 1.1), durationFrames - fileStart - Math.round(0.6 * fps)))}
                height={lowerHeight - 54}
                fontSize={22}
              />
            </Panel>
          )}
        </div>
      )}

      <RunStrip take={take} />
    </AbsoluteFill>
  );
};
