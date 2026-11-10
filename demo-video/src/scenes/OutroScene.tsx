import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { Chapter } from "../components/Chapter";
import { demo } from "../data";
import { C, FONT_MONO, FONT_SANS } from "../theme";
import { FPS, beats } from "../timing";

const ease = Easing.bezier(0.16, 1, 0.3, 1);

const BOXES = [
  { title: "You", sub: "plain-English request", color: C.text, width: 230 },
  { title: "Agent loop", sub: "llm_file_assistant.py", color: C.cyan, width: 290 },
  { title: "LLM provider", sub: "Anthropic · OpenAI · Gemini · OpenRouter · Ollama", color: C.purple, width: 440 },
  { title: "Validate + dispatch", sub: "tool_schemas.py", color: C.orange, width: 290 },
  { title: "File tools", sub: "fs_tools.py, sandboxed", color: C.green, width: 250 },
] as const;

export const OutroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const passed = demo.pytest.summary.match(/(\d+) passed/)?.[1];
  const bt = beats("outro");
  const repoAt = bt ? Math.round(bt.repoAt * FPS) : 100;

  return (
    <AbsoluteFill>
      <Background />
      <Chapter tag="RECAP" title="How it fits together" />

      <div style={{ position: "absolute", left: 100, top: 250, width: 1720, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        {BOXES.map((b, i) => {
          const at = bt ? Math.round(bt.boxesAt[i] * FPS) : 14 + i * 16;
          const t = interpolate(frame, [at, at + 18], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
          return (
            <div key={b.title} style={{ display: "contents" }}>
              <div
                style={{
                  width: b.width,
                  height: 240,
                  boxSizing: "border-box",
                  borderRadius: 18,
                  border: `2px solid ${b.color}`,
                  background: C.panel,
                  padding: "26px 22px",
                  fontFamily: FONT_SANS,
                  opacity: t,
                  translate: `0px ${(1 - t) * 30}px`,
                  boxShadow: "0 20px 50px rgba(0,0,0,0.4)",
                }}
              >
                <div style={{ fontSize: 38, fontWeight: 800, color: b.color }}>{b.title}</div>
                <div style={{ fontSize: 25, color: C.dim, marginTop: 14, lineHeight: 1.35 }}>{b.sub}</div>
              </div>
              {i < BOXES.length - 1 && (
                <div style={{ fontFamily: FONT_MONO, fontSize: 40, color: C.faint, opacity: t }}>{">"}</div>
              )}
            </div>
          );
        })}
      </div>

      <div
        style={{
          position: "absolute",
          left: 100,
          right: 100,
          top: 640,
          textAlign: "center",
          fontFamily: FONT_SANS,
          opacity: interpolate(frame, [repoAt, repoAt + 28], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease }),
        }}
      >
        <div style={{ fontSize: 92, fontWeight: 800, color: C.text, fontFamily: FONT_MONO, letterSpacing: -1 }}>{demo.meta.repo}</div>
        <div style={{ fontSize: 38, color: C.dim, marginTop: 26 }}>
          {passed ? `${passed} tests  ·  ` : ""}
          {demo.providers.length} providers  ·  sandboxed file access
        </div>
      </div>
    </AbsoluteFill>
  );
};
