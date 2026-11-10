/** Shape of src/data/demo-data.json, written by scripts/capture_demo_data.py from a REAL run. */

export type AssistantTextEvent = { type: "assistant_text"; t: number; text: string };
export type ToolCallEvent = {
  type: "tool_call";
  t: number;
  name: string;
  args: Record<string, unknown>;
  /** The exact argument string the CLI trace prints. */
  args_text: string;
};
export type ToolResultEvent = {
  type: "tool_result";
  t: number;
  name: string;
  ok: boolean;
  /** The exact one-line summary the CLI trace prints. */
  summary: string;
  error_type: string | null;
};
export type TakeEvent = AssistantTextEvent | ToolCallEvent | ToolResultEvent;

export type Take = {
  id: string;
  label: string;
  query: string;
  events: TakeEvent[];
  answer: string;
  iterations: number;
  elapsed_seconds: number;
  attempt: number;
  accepted: boolean;
  written_file?: { path: string; content: string };
};

export type DemoData = {
  meta: {
    provider: string;
    model: string;
    endpoint: string;
    captured_at: string;
    repo: string;
  };
  resumes: { name: string; size_bytes: number; extension: string }[];
  providers: {
    name: string;
    description: string;
    key: string;
    model_env: string;
    default_model: string;
    ready: boolean;
  }[];
  pytest: { command: string; lines: string[]; summary: string; returncode: number };
  code: {
    tools: Record<string, string>;
    resolve: string;
    schema: string;
    loc: Record<string, number>;
  };
  takes: Take[];
};

export type TakeId =
  | "read-all"
  | "find-python"
  | "summary"
  | "summary-again"
  | "sandbox";
