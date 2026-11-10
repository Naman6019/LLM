import React, { useLayoutEffect, useMemo, useRef, useState } from "react";
import { Easing, interpolate, useDelayRender } from "remotion";
import { C, FONT_MONO, FONT_SANS } from "../theme";
import { parseMarkdown, type Unit } from "../lib/markdown";

/** `**bold**`, `*italic*` and `` `code` `` inside a line of text. */
const Inline: React.FC<{ text: string; size: number }> = ({ text, size }) => {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g).filter(Boolean);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("**") && p.endsWith("**") && p.length > 4)
          return (
            <strong key={i} style={{ color: C.text, fontWeight: 800 }}>
              <Inline text={p.slice(2, -2)} size={size} />
            </strong>
          );
        if (p.startsWith("`") && p.endsWith("`") && p.length > 2)
          return (
            <code
              key={i}
              style={{
                fontFamily: FONT_MONO,
                fontSize: size * 0.88,
                color: C.orange,
                background: "rgba(110,118,129,0.22)",
                padding: "1px 7px",
                borderRadius: 6,
              }}
            >
              {p.slice(1, -1)}
            </code>
          );
        if (p.startsWith("*") && p.endsWith("*") && p.length > 2)
          return (
            <em key={i} style={{ color: C.blue }}>
              {p.slice(1, -1)}
            </em>
          );
        return <React.Fragment key={i}>{p}</React.Fragment>;
      })}
    </>
  );
};

const UnitView: React.FC<{ unit: Unit; size: number }> = ({ unit, size }) => {
  switch (unit.kind) {
    case "heading":
      return (
        <div style={{ fontSize: size * (unit.level <= 2 ? 1.25 : 1.1), fontWeight: 800, color: C.text, margin: "10px 0 4px" }}>
          <Inline text={unit.text} size={size} />
        </div>
      );
    case "para":
      return (
        <div style={{ margin: "6px 0" }}>
          <Inline text={unit.text} size={size} />
        </div>
      );
    case "quote":
      return (
        <div style={{ margin: "6px 0", paddingLeft: 18, borderLeft: `4px solid ${C.faint}`, color: C.dim }}>
          <Inline text={unit.text} size={size} />
        </div>
      );
    case "li":
      return (
        <div style={{ display: "flex", gap: 14, margin: "4px 0", paddingLeft: 12 + unit.indent * 34 }}>
          <span style={{ color: C.cyan, minWidth: 26, textAlign: "right" }}>{unit.marker}</span>
          <span>
            <Inline text={unit.text} size={size} />
          </span>
        </div>
      );
    case "hr":
      return <div style={{ height: 1, background: C.border, margin: "12px 0" }} />;
    case "code":
      return (
        <pre
          style={{
            margin: "8px 0",
            padding: "12px 18px",
            background: "#0d1117",
            border: `1px solid ${C.border}`,
            borderRadius: 10,
            fontFamily: FONT_MONO,
            fontSize: size * 0.8,
            color: C.blue,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {unit.text}
        </pre>
      );
    case "thead":
    case "trow": {
      const header = unit.kind === "thead";
      return (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: unit.weights.map((w) => `${w}fr`).join(" "),
            gap: 24,
            padding: "7px 14px",
            borderBottom: `1px solid ${header ? C.cyan : C.border}`,
            background: header ? "rgba(88,166,255,0.10)" : "transparent",
            fontSize: size * 0.9,
            fontWeight: header ? 800 : 400,
            color: header ? C.cyan : C.text,
          }}
        >
          {unit.cells.map((c, i) => (
            <div key={i}>
              <Inline text={c} size={size * 0.9} />
            </div>
          ))}
        </div>
      );
    }
  }
};

/**
 * Renders Markdown that "streams in" unit by unit (a paragraph, a list item, a table row...) and
 * scrolls so the newest unit is always visible, like the answer panel of the real CLI.
 */
export const Markdown: React.FC<{
  text: string;
  frame: number;
  /** Frame at which the first unit appears. */
  start: number;
  /** Frames over which all units are revealed. */
  revealFrames: number;
  height: number;
  fontSize?: number;
}> = ({ text, frame, start, revealFrames, height, fontSize = 25 }) => {
  const units = useMemo(() => parseMarkdown(text), [text]);
  const refs = useRef<(HTMLDivElement | null)[]>([]);
  const [bottoms, setBottoms] = useState<number[]>([]);
  const { delayRender, continueRender } = useDelayRender();
  const [handle] = useState(() => delayRender("Measuring markdown"));

  useLayoutEffect(() => {
    setBottoms(refs.current.map((el) => (el ? el.offsetTop + el.offsetHeight : 0)));
    continueRender(handle);
  }, [continueRender, handle, units]);

  const n = units.length;
  const step = n > 0 ? revealFrames / n : 0;
  const appear = units.map((_, i) => start + i * step);

  // Scroll just enough to keep the most recently revealed unit in view.
  const pad = 24;
  const scroll =
    bottoms.length === n && n > 1
      ? interpolate(
          frame,
          appear.map((a, i) => a + 10 + i * 0.001),
          bottoms.map((b) => Math.max(0, b + pad - height)),
          { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) },
        )
      : 0;

  return (
    <div style={{ height, overflow: "hidden", position: "relative", fontFamily: FONT_SANS, fontSize, lineHeight: 1.42, color: C.text }}>
      <div style={{ translate: `0px ${-scroll}px` }}>
        {units.map((u, i) => {
          const p = interpolate(frame, [appear[i], appear[i] + 9], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          return (
            <div
              key={i}
              ref={(el) => {
                refs.current[i] = el;
              }}
              style={{ opacity: p, translate: `0px ${(1 - p) * 10}px` }}
            >
              <UnitView unit={u} size={fontSize} />
            </div>
          );
        })}
      </div>
    </div>
  );
};
