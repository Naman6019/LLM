import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { Panel } from "../components/Panel";
import { demo } from "../data";
import { C, EXT_COLOR, FONT_MONO, FONT_SANS } from "../theme";

const ease = Easing.bezier(0.16, 1, 0.3, 1);

const kb = (bytes: number) => `${(bytes / 1024).toFixed(1)} KB`;

/** Fade + slide in, starting at `at` frames. */
const useReveal = (at: number, len = 22) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [at, at + len], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });
  return { opacity: t, translate: `0px ${(1 - t) * 26}px` } as const;
};

const Pill: React.FC<{ tag: string; text: string; color: string; at: number }> = ({ tag, text, color, at }) => (
  <div
    style={{
      ...useReveal(at),
      display: "flex",
      alignItems: "center",
      gap: 16,
      fontFamily: FONT_SANS,
      fontSize: 34,
      color: C.text,
    }}
  >
    <span style={{ background: color, color: C.bg, fontWeight: 800, letterSpacing: 2, fontSize: 24, padding: "7px 16px", borderRadius: 999 }}>{tag}</span>
    <span style={{ fontFamily: FONT_MONO, fontSize: 31 }}>{text}</span>
  </div>
);

export const TitleScene: React.FC = () => {
  const l1 = useReveal(6, 28);
  const l2 = useReveal(16, 28);
  const sub = useReveal(34);
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill>
      <Background />

      <div style={{ position: "absolute", left: 100, top: 190, width: 900, fontFamily: FONT_SANS }}>
        <div
          style={{
            ...l1,
            fontSize: 132,
            fontWeight: 800,
            lineHeight: 1.02,
            letterSpacing: -3,
            background: `linear-gradient(90deg, ${C.cyan}, ${C.purple})`,
            WebkitBackgroundClip: "text",
            backgroundClip: "text",
            color: "transparent",
          }}
        >
          LLM-Powered
        </div>
        <div style={{ ...l2, fontSize: 96, fontWeight: 800, lineHeight: 1.1, letterSpacing: -2, color: C.text }}>
          File System
          <br />
          Assistant
        </div>
        <div style={{ ...sub, marginTop: 40, fontSize: 46, lineHeight: 1.3, color: C.dim }}>
          An LLM that reads, searches and writes your files through tool calling.
        </div>
        <div style={{ marginTop: 52, display: "flex", flexDirection: "column", gap: 20 }}>
          <Pill tag="PART A" text="fs_tools.py" color={C.cyan} at={58} />
          <Pill tag="PART B" text="llm_file_assistant.py" color={C.green} at={70} />
        </div>
      </div>

      <div style={{ position: "absolute", left: 1040, top: 150, opacity: interpolate(frame, [26, 48], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
        <Panel title={`resumes/   ·   ${demo.resumes.length} files`} width={780} height={780} color={C.dim} mono>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingTop: 10 }}>
            {demo.resumes.map((r, i) => {
              const at = 52 + i * 7;
              const t = interpolate(frame, [at, at + 14], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
              const color = EXT_COLOR[r.extension] ?? C.dim;
              return (
                <div
                  key={r.name}
                  style={{
                    opacity: t,
                    translate: `${(1 - t) * 34}px 0px`,
                    display: "flex",
                    alignItems: "center",
                    gap: 18,
                    height: 76,
                    padding: "0 20px",
                    borderRadius: 12,
                    background: C.panelAlt,
                    fontFamily: FONT_MONO,
                    fontSize: 27,
                    color: C.text,
                  }}
                >
                  <span style={{ background: `${color}33`, color, fontWeight: 700, fontSize: 20, padding: "5px 11px", borderRadius: 8, minWidth: 76, textAlign: "center" }}>
                    {r.extension.replace(".", "").toUpperCase()}
                  </span>
                  <span style={{ flex: 1 }}>{r.name}</span>
                  <span style={{ color: C.dim, fontSize: 23 }}>{kb(r.size_bytes)}</span>
                </div>
              );
            })}
          </div>
        </Panel>
      </div>
    </AbsoluteFill>
  );
};
