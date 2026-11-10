import React, { useMemo } from "react";
import { Easing, interpolate } from "remotion";
import { Window } from "./Terminal";
import { highlightJson, highlightPython } from "../lib/syntax";
import { C, FONT_MONO } from "../theme";

export type Highlight = {
  /** 1-based first and last line to focus. */
  from: number;
  to: number;
  /** Frames (local to the window) at which the highlight fades in and out. */
  start: number;
  end: number;
  label?: string;
};

const env = (frame: number, h: Highlight) => {
  const fade = Math.min(10, (h.end - h.start) / 3); // short highlights get shorter fades
  return interpolate(frame, [h.start, h.start + fade, h.end - fade, h.end], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
};

/** The label of the highlight that is currently most visible (shown below the window, never over code). */
export const activeLabel = (
  frame: number,
  highlights: Highlight[],
): { label: string; amount: number } | null => {
  let best: { label: string; amount: number } | null = null;
  for (const h of highlights) {
    const amount = env(frame, h);
    if (h.label && amount > 0 && (!best || amount > best.amount)) best = { label: h.label, amount };
  }
  return best;
};

/** Editor-style window: syntax highlighting, line numbers, and animated "look here" highlights. */
export const CodeWindow: React.FC<{
  filename: string;
  code: string;
  language: "python" | "json";
  frame: number;
  width: number;
  height: number;
  fontSize?: number;
  highlights?: Highlight[];
}> = ({ filename, code, language, frame, width, height, fontSize = 24, highlights = [] }) => {
  const lh = Math.round(fontSize * 1.62);
  const tokens = useMemo(
    () => (language === "python" ? highlightPython(code) : highlightJson(code)),
    [code, language],
  );
  const envs = highlights.map((h) => env(frame, h));
  const anyActive = Math.max(0, ...envs);
  const pad = 26;
  const gutter = 74;

  return (
    <Window title={filename} width={width} height={height}>
      <div style={{ position: "absolute", inset: 0, padding: `${pad}px 0`, fontFamily: FONT_MONO, fontSize }}>
        {/* highlight bands */}
        {highlights.map((h, i) => (
          <React.Fragment key={i}>
            <div
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                top: pad + (h.from - 1) * lh - 3,
                height: (h.to - h.from + 1) * lh + 6,
                background: "rgba(88,166,255,0.13)",
                borderLeft: `5px solid ${C.cyan}`,
                opacity: envs[i],
              }}
            />
          </React.Fragment>
        ))}

        {/* code */}
        {tokens.map((line, i) => {
          const n = i + 1;
          const focus = Math.max(0, ...highlights.map((h, k) => (n >= h.from && n <= h.to ? envs[k] : 0)));
          const opacity = 1 - 0.58 * Math.max(0, anyActive - focus);
          return (
            <div key={i} style={{ height: lh, lineHeight: `${lh}px`, whiteSpace: "pre", display: "flex", opacity }}>
              <span style={{ width: gutter, paddingRight: 22, textAlign: "right", color: C.faint, flex: "none" }}>{n}</span>
              <span>
                {line.length === 0 ? " " : null}
                {line.map((t, k) => (
                  <span key={k} style={{ color: t.color, fontWeight: t.bold ? 700 : 400, fontStyle: t.italic ? "italic" : "normal" }}>
                    {t.text}
                  </span>
                ))}
              </span>
            </div>
          );
        })}
      </div>
    </Window>
  );
};
