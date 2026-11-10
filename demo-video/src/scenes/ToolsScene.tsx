import { useMemo } from "react";
import { AbsoluteFill, Easing, Sequence, interpolate, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { Chapter } from "../components/Chapter";
import { CodeWindow, activeLabel, type Highlight } from "../components/CodeWindow";
import { demo } from "../data";
import { condenseTool, findLine } from "../lib/syntax";
import { C, FONT_SANS } from "../theme";
import { FPS, beats, sceneFrames } from "../timing";

const X = 100;
const W = 1720;
const TOP = 128;
const H = 836;

/** Cross-fade wrapper for one sub-view of the scene. */
const Fade: React.FC<{ frames: number; children: React.ReactNode }> = ({ frames, children }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 12, frames - 12, frames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

/** Code window + the line below it: a dim caption, replaced by the active highlight's label. */
const CodeView: React.FC<{
  frames: number;
  caption: string;
  filename: string;
  code: string;
  language: "python" | "json";
  fontSize: number;
  highlights: Highlight[];
}> = ({ frames, caption, filename, code, language, fontSize, highlights }) => {
  const frame = useCurrentFrame();
  const active = activeLabel(frame, highlights);
  const intro = interpolate(frame, [6, 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  return (
    <Fade frames={frames}>
      <div style={{ position: "absolute", left: X, top: TOP }}>
        <CodeWindow filename={filename} language={language} code={code} frame={frame} width={W} height={H} fontSize={fontSize} highlights={highlights} />
      </div>
      <div style={{ position: "absolute", left: X, right: X, bottom: 24, height: 60, fontFamily: FONT_SANS }}>
        <div style={{ position: "absolute", fontSize: 30, color: C.dim, opacity: intro * (1 - (active?.amount ?? 0)) }}>{caption}</div>
        {active && (
          <div style={{ position: "absolute", fontSize: 40, fontWeight: 600, color: C.cyan, opacity: active.amount, translate: `0px ${(1 - active.amount) * 12}px` }}>
            {active.label}
          </div>
        )}
      </div>
    </Fade>
  );
};

/**
 * Abbreviated rendering of the real JSON Schema for search_in_file: same keys and values, with
 * each property on one line and long descriptions shortened. (The full schema lives in tool_schemas.py.)
 */
const abbreviateSchema = (json: string): string => {
  const q = (v: unknown) => JSON.stringify(v);
  const short = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 3)}...` : s);
  const spec = JSON.parse(json) as {
    name: string;
    description: string;
    parameters: { properties: Record<string, Record<string, unknown>>; required: string[] };
  };
  const entries = Object.entries(spec.parameters.properties);
  const props = entries.map(([key, def], i) => {
    const body = Object.entries(def)
      .map(([k, v]) => `${q(k)}: ${typeof v === "string" ? q(short(v, 38)) : q(v)}`)
      .join(", ");
    return `      ${q(key)}: { ${body} }${i < entries.length - 1 ? "," : ""}`;
  });
  return [
    "{",
    `  "name": ${q(spec.name)},`,
    `  "description": ${q(short(spec.description, 92))},`,
    '  "parameters": {',
    '    "type": "object",',
    '    "properties": {',
    ...props,
    "    },",
    `    "required": ${q(spec.parameters.required)},`,
    '    "additionalProperties": false',
    "  }",
    "}",
  ].join("\n");
};

export const ToolsScene: React.FC = () => {
  const total = sceneFrames("tools");
  // Three sub-views share the scene: the four tools, the sandbox, and the schema sent to the model.
  const bt = beats("tools");
  // With a recording, the views switch where the narrator moves from the tools to the sandbox to the schema.
  const a = bt ? Math.round(bt.sandboxAt * FPS) : Math.round(total * 0.42);
  const b = bt ? Math.round((bt.schemaAt - bt.sandboxAt) * FPS) : Math.round(total * 0.31);
  const c = total - a - b;

  const toolsCode = useMemo(
    () => ["read_file", "list_files", "write_file", "search_in_file"].map((n) => condenseTool(demo.code.tools[n])).join("\n\n"),
    [],
  );
  const toolHighlights = useMemo<Highlight[]>(() => {
    const spec: [string, string][] = [
      ["def read_file", "read_file: PDF, DOCX or TXT in, text and metadata out"],
      ["def list_files", "list_files: names, sizes and dates, filter by extension"],
      ["def write_file", "write_file: atomic, creates folders, won't overwrite by default"],
      ["def search_in_file", "search_in_file: case-insensitive, with surrounding context"],
    ];
    // With a recording, step through the tools at the pace the narrator names them (overlapping a little).
    const per = bt ? 0.6 * FPS : (a - 36) / spec.length;
    const len = bt ? 0.85 * FPS : per;
    const first = bt ? bt.namesAt * FPS : 18;
    const lines = toolsCode.split("\n");
    return spec.flatMap(([needle, label], i) => {
      const from = findLine(toolsCode, needle);
      if (!from) return [];
      let to = from; // search_in_file's signature spans several lines: extend to the closing "):" line
      while (to < lines.length && !/\)\s*(->.*)?:\s*$/.test(lines[to - 1])) to += 1;
      return [{ from, to, start: first + i * per, end: first + i * per + len, label }];
    });
  }, [toolsCode, a, bt]);

  const resolveHighlight = useMemo<Highlight[]>(() => {
    const from = findLine(demo.code.resolve, "try:");
    const to = findLine(demo.code.resolve, "from None");
    return from && to
      ? [{ from, to, start: 24, end: b - 14, label: "A path that escapes the project folder is rejected" }]
      : [];
  }, [b]);

  const schemaCode = useMemo(() => abbreviateSchema(demo.code.schema), []);
  const schemaHighlight = useMemo<Highlight[]>(() => {
    const from = findLine(schemaCode, '"required"');
    return from
      ? [{ from, to: from, start: 45, end: c - 12, label: "The model must supply the required arguments; anything else is rejected" }]
      : [];
  }, [schemaCode, c]);

  return (
    <AbsoluteFill>
      <Background />
      <Chapter tag="PART A" title="Four tools, sandboxed" />

      <Sequence  durationInFrames={a} premountFor={30}>
        <CodeView
          frames={a}
          caption={`fs_tools.py  ·  ${demo.code.loc["fs_tools.py"]} lines  ·  every tool returns a structured result, errors included`}
          filename="fs_tools.py"
          code={toolsCode}
          language="python"
          fontSize={23}
          highlights={toolHighlights}
        />
      </Sequence>

      <Sequence from={a} durationInFrames={b} premountFor={30}>
        <CodeView
          frames={b}
          caption="The model picks the paths, but it can only touch files inside the project folder"
          filename="fs_tools.py  ·  _resolve()"
          code={demo.code.resolve}
          language="python"
          fontSize={24}
          highlights={resolveHighlight}
        />
      </Sequence>

      <Sequence from={a + b} durationInFrames={c} premountFor={30}>
        <CodeView
          frames={c}
          caption="Each tool is described once, as JSON Schema, and the model's arguments are validated against it"
          filename="tool_schemas.py  ·  JSON Schema sent to the model (abbreviated)"
          code={schemaCode}
          language="json"
          fontSize={23}
          highlights={schemaHighlight}
        />
      </Sequence>
    </AbsoluteFill>
  );
};
