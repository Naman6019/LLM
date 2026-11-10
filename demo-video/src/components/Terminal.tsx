import React from "react";
import { interpolate } from "remotion";
import { C, FONT_MONO, FONT_SANS, TERM } from "../theme";
import type { Seg, TermLine } from "../lib/timeline";

/** macOS-ish window chrome. `children` fill the body. */
export const Window: React.FC<{
  title: string;
  width: number;
  height: number;
  children: React.ReactNode;
  accent?: string;
}> = ({ title, width, height, children, accent }) => (
  <div
    style={{
      width,
      height,
      borderRadius: 16,
      overflow: "hidden",
      background: "#0d1117",
      border: `1px solid ${accent ?? C.border}`,
      boxShadow: "0 30px 80px rgba(0,0,0,0.55)",
      display: "flex",
      flexDirection: "column",
    }}
  >
    <div
      style={{
        height: 54,
        flex: "none",
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "0 22px",
        background: C.panel,
        borderBottom: `1px solid ${C.border}`,
        fontFamily: FONT_SANS,
      }}
    >
      {["#ff5f56", "#ffbd2e", "#27c93f"].map((c) => (
        <span key={c} style={{ width: 15, height: 15, borderRadius: 99, background: c }} />
      ))}
      <span style={{ marginLeft: 18, color: C.dim, fontSize: 21, fontWeight: 600 }}>{title}</span>
    </div>
    <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>{children}</div>
  </div>
);

const sliceSegs = (segs: Seg[], chars: number): Seg[] => {
  const out: Seg[] = [];
  let left = chars;
  for (const s of segs) {
    if (left <= 0) break;
    out.push({ ...s, text: s.text.slice(0, left) });
    left -= s.text.length;
  }
  return out;
};

const SegSpans: React.FC<{ segs: Seg[] }> = ({ segs }) => (
  <>
    {segs.map((s, i) => (
      <span
        key={i}
        style={{
          color: s.color ?? C.text,
          fontWeight: s.bold ? 700 : 400,
          fontStyle: s.italic ? "italic" : "normal",
        }}
      >
        {s.text}
      </span>
    ))}
  </>
);

/** Terminal body: timed lines that scroll so the newest line stays visible. */
export const Trace: React.FC<{
  lines: TermLine[];
  frame: number;
  /** Height of the body area in px (drives how many rows are visible). */
  height: number;
}> = ({ lines, frame, height }) => {
  const pad = 22;
  const rows = Math.max(1, Math.floor((height - 2 * pad) / TERM.lineHeight));

  // Fractional number of lines revealed so far -> smooth scrolling.
  let revealed = 0;
  for (const l of lines) {
    revealed += interpolate(frame, [l.appear, l.appear + 5], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  }
  const scroll = Math.max(0, revealed - rows) * TERM.lineHeight;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        padding: `${pad}px 34px`,
        fontFamily: FONT_MONO,
        fontSize: TERM.fontSize,
        maskImage: scroll > 0 ? "linear-gradient(to bottom, transparent 0px, #000 34px)" : undefined,
      }}
    >
      <div style={{ translate: `0px ${-scroll}px` }}>
        {lines.map((l, idx) => {
          const p = interpolate(frame, [l.appear, l.appear + 5], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          if (p <= 0) return <div key={l.id} style={{ height: TERM.lineHeight }} />;

          let segs = l.segs;
          let typing = false;
          if (l.typingFrames !== undefined) {
            const total = l.segs.reduce((n, s) => n + s.text.length, 0);
            const prefix = l.typedPrefix ?? 0;
            const t = interpolate(frame, [l.appear, l.appear + l.typingFrames], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            segs = sliceSegs(l.segs, prefix + Math.floor(t * (total - prefix)));
          }
          typing = !!l.cursor && frame < (lines[idx + 1]?.appear ?? Infinity);
          const cursorOn = typing && Math.floor(frame / 15) % 2 === 0;

          return (
            <div
              key={l.id}
              style={{
                height: TERM.lineHeight,
                lineHeight: `${TERM.lineHeight}px`,
                whiteSpace: "pre",
                opacity: p,
                margin: l.isError ? "0 -34px" : undefined,
                padding: l.isError ? "0 34px" : undefined,
                background: l.isError ? "rgba(248,81,73,0.11)" : undefined,
                borderLeft: l.isError ? `4px solid ${C.red}` : undefined,
                boxSizing: "border-box",
              }}
            >
              <SegSpans segs={segs} />
              {typing && (
                <span
                  style={{
                    display: "inline-block",
                    width: TERM.charWidth,
                    height: TERM.fontSize,
                    marginLeft: 2,
                    translate: "0px 5px",
                    background: C.text,
                    opacity: cursorOn ? 0.85 : 0,
                  }}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
