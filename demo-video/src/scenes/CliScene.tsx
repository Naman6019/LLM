import { useMemo } from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { Chapter } from "../components/Chapter";
import { Trace, Window } from "../components/Terminal";
import { demo } from "../data";
import type { TermLine } from "../lib/timeline";
import { C } from "../theme";

const KEY = 34;
const MODEL = 20;
const NAME = 12;

export const CliScene: React.FC = () => {
  const frame = useCurrentFrame();

  const lines = useMemo<TermLine[]>(() => {
    const out: TermLine[] = [];
    const prompt = (id: string, cmd: string, appear: number, typing: number): TermLine => ({
      id,
      segs: [{ text: "$ ", color: C.green, bold: true }, { text: cmd }],
      appear,
      typingFrames: typing,
      typedPrefix: 2,
      cursor: true,
    });

    out.push(prompt("p1", "python llm_file_assistant.py --list-providers", 10, 60));

    // A plain-text table: monospaced alignment, no box-drawing glyphs.
    const row = (a: string, b: string, c: string) => `${a.padEnd(NAME)}${b.padEnd(KEY)}${c.padEnd(MODEL)}`;
    const table = [
      { text: row("provider", "API key variable", "default model"), color: C.cyan, bold: true },
      { text: row("-".repeat(NAME - 2), "-".repeat(KEY - 2), "-".repeat(MODEL - 2)), color: C.faint },
      ...demo.providers.map((p) => ({ text: row(p.name, p.key, p.default_model), color: C.text, bold: false })),
    ];
    table.forEach((t, i) => out.push({ id: `t${i}`, segs: [{ text: t.text, color: t.color, bold: t.bold }], appear: 80 + i * 6 }));

    const afterTable = 80 + table.length * 6 + 36;
    out.push(prompt("p2", "python llm_file_assistant.py", afterTable, 56));
    const bannerAt = afterTable + 56 + 14;
    out.push({
      id: "banner",
      segs: [
        { text: "LLM File Assistant", bold: true },
        { text: " - provider=" },
        { text: demo.meta.provider, color: C.cyan },
        { text: " model=" },
        { text: demo.meta.model, color: C.cyan },
        { text: " root=" },
        { text: ".../LLM", color: C.dim },
      ],
      appear: bannerAt,
    });
    out.push({
      id: "help",
      segs: [{ text: "Commands: /tools  list available tools   /reset  clear conversation   /help   /exit", color: C.dim }],
      appear: bannerAt + 8,
    });
    out.push({ id: "you", segs: [{ text: "you> ", bold: true }], appear: bannerAt + 18, typingFrames: 1, typedPrefix: 5, cursor: true });
    return out;
  }, []);

  return (
    <AbsoluteFill>
      <Background />
      <Chapter tag="PART B" title="Pick any provider" />
      <div style={{ position: "absolute", left: 100, top: 128 }}>
        <Window title="terminal" width={1720} height={836}>
          <Trace lines={lines} frame={frame} height={836 - 54} />
        </Window>
      </div>
    </AbsoluteFill>
  );
};
