import { useMemo } from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { Chapter } from "../components/Chapter";
import { Trace, Window } from "../components/Terminal";
import { demo } from "../data";
import type { Seg, TermLine } from "../lib/timeline";
import { C, FONT_SANS } from "../theme";
import { FPS, beats } from "../timing";

/** "......s...  [48%]" -> green dots, yellow skips, dim percentage. */
const pytestSegs = (line: string): Seg[] => {
  const m = line.match(/^([.sFEx]+)(\s*\[\s*\d+%\])?\s*$/);
  if (!m) return [{ text: line, color: C.dim }];
  const segs: Seg[] = [];
  for (const ch of m[1]) {
    const color = ch === "." ? C.green : ch === "s" ? C.yellow : C.red;
    const last = segs[segs.length - 1];
    if (last && last.color === color) last.text += ch;
    else segs.push({ text: ch, color });
  }
  if (m[2]) segs.push({ text: ` ${m[2].trim()}`, color: C.dim });
  return segs;
};

export const TestsScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { summary, lines } = demo.pytest;
  const passed = summary.match(/(\d+) passed/)?.[1] ?? "?";
  const skipped = summary.match(/(\d+) skipped/)?.[1];
  const seconds = summary.match(/in ([\d.]+)s/)?.[1];

  // With a recording, the run finishes and the count appears as the narrator says it.
  const bt = beats("tests");
  const termLines = useMemo<TermLine[]>(() => {
    const out: TermLine[] = [
      { id: "prompt", segs: [{ text: "$ ", color: C.green, bold: true }, { text: "pytest" }], appear: 14, typingFrames: 14, typedPrefix: 2, cursor: true },
    ];
    const dotLines = lines.filter((l) => /^[.sFEx]+/.test(l));
    const first = bt ? 0.9 * FPS : 46;
    const summaryAt = bt ? Math.round(bt.summaryAt * FPS) : 46 + dotLines.length * 50 + 10;
    const per = dotLines.length ? (summaryAt - 6 - first) / dotLines.length : 0;
    dotLines.forEach((l, i) =>
      out.push({
        id: `dots-${i}`,
        segs: pytestSegs(l),
        appear: Math.round(first + i * per),
        typingFrames: Math.max(8, Math.round(bt ? per * 0.95 : 48)),
      }),
    );
    out.push({
      id: "summary",
      segs: [{ text: summary.replace(/^=+\s*|\s*=+$/g, ""), color: C.green, bold: true }],
      appear: summaryAt,
    });
    return out;
  }, [lines, summary, bt]);

  const summaryAt = termLines[termLines.length - 1].appear;
  const noteAt = bt ? Math.round(bt.noteAt * FPS) : summaryAt + 10;
  const card = interpolate(frame, [summaryAt, summaryAt + 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <AbsoluteFill>
      <Background />
      <Chapter tag="TESTS" title="Verified, with no API key" />

      {/* pytest prints 72 dots + a percentage per row, so the terminal needs ~1320px */}
      <div style={{ position: "absolute", left: 100, top: 210 }}>
        <Window title="terminal" width={1330} height={440}>
          <Trace lines={termLines} frame={frame} height={440 - 54} />
        </Window>
      </div>

      <div
        style={{
          position: "absolute",
          left: 1450,
          top: 210,
          width: 370,
          height: 440,
          boxSizing: "border-box",
          borderRadius: 16,
          border: `2px solid ${C.green}`,
          background: "rgba(63,185,80,0.08)",
          fontFamily: FONT_SANS,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          opacity: card,
          scale: 0.94 + 0.06 * card,
        }}
      >
        <div style={{ fontSize: 170, fontWeight: 800, color: C.green, lineHeight: 1 }}>{passed}</div>
        <div style={{ fontSize: 44, fontWeight: 600, color: C.text, marginTop: 6 }}>tests passed</div>
        <div style={{ fontSize: 28, color: C.dim, marginTop: 16 }}>
          {skipped ? `${skipped} skipped  ·  ` : ""}
          {seconds ? `${seconds}s` : ""}
        </div>
      </div>

      <div style={{ position: "absolute", left: 100, right: 100, top: 730, fontFamily: FONT_SANS, fontSize: 38, color: C.dim, lineHeight: 1.45, opacity: interpolate(frame, [noteAt, noteAt + 20], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
        The tools, the argument validation and the provider wire formats are all tested{" "}
        <span style={{ color: C.text }}>offline</span>: the LLM clients are replaced by scripted fakes.
      </div>
    </AbsoluteFill>
  );
};
