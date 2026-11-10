import { C, TERM } from "../theme";
import type { Take, ToolCallEvent, ToolResultEvent } from "../data/types";

export type Seg = {
  text: string;
  color?: string;
  bold?: boolean;
  italic?: boolean;
};

export type TermLine = {
  id: string;
  segs: Seg[];
  /** Frame (relative to the scene) at which the line starts to appear. */
  appear: number;
  /** For the typed prompt line: how many frames the typing takes. */
  typingFrames?: number;
  /** Length of the typed prefix (e.g. "you> ") that is shown immediately. */
  typedPrefix?: number;
  /** Show a blinking cursor after the typed text until the next line appears. */
  cursor?: boolean;
  isError?: boolean;
};

export type TakeTimeline = {
  lines: TermLine[];
  /** Frame at which the final answer starts to be shown. */
  answerStart: number;
  answerFrames: number;
  /** True if the captured run is too long for the scene length at the minimum pacing. */
  overflow: boolean;
};

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Hard-wrap a run of segments to `cols` columns, indenting continuation lines. */
export function wrapSegs(segs: Seg[], cols: number, indent: number): Seg[][] {
  const rows: Seg[][] = [];
  let row: Seg[] = [];
  let width = 0;
  const pad = " ".repeat(indent);

  const push = (text: string, seg: Omit<Seg, "text">) => {
    if (!text) return;
    const last = row[row.length - 1];
    if (last && last.color === seg.color && last.bold === seg.bold && last.italic === seg.italic) {
      last.text += text;
    } else row.push({ ...seg, text });
    width += text.length;
  };
  const breakRow = () => {
    rows.push(row);
    row = [];
    width = 0;
    if (indent) push(pad, {});
  };

  for (const seg of segs) {
    // split into words, keeping whitespace so spacing is preserved
    for (const word of seg.text.split(/(?<= )/)) {
      let w = word;
      while (width + w.length > cols && width > indent) {
        if (w.length <= cols - indent && width > indent) {
          breakRow();
          break;
        }
        const room = cols - width;
        push(w.slice(0, room), seg);
        w = w.slice(room);
        breakRow();
      }
      push(w, seg);
    }
  }
  if (row.length) rows.push(row);
  return rows;
}

const callSegs = (c: ToolCallEvent): Seg[] => [
  { text: "  > ", color: C.dim },
  { text: c.name, color: C.cyan, bold: true },
  { text: `(${c.args_text})`, color: C.dim },
];

const resultSegs = (r: ToolResultEvent): Seg[] => [
  { text: "    <- ", color: C.dim },
  r.ok
    ? { text: "ok ", color: C.green, bold: true }
    : { text: "error ", color: C.red, bold: true },
  { text: r.summary, color: r.ok ? C.dim : C.orange },
];

/**
 * Lay the captured run out on a timeline that fits `durationFrames`.
 *
 *   [lead] type the prompt -> [steps: call + result ...] -> [answer streams in] -> [hold]
 *
 * Only the pacing is decided here; every line of text comes from the recorded run.
 */
export function buildTimeline(
  take: Take,
  durationFrames: number,
  fps: number,
  /** Optional pins (in frames) so the replay lines up with the narration. */
  beats?: { stepsAt?: number; answerAt?: number },
): TakeTimeline {
  const lines: TermLine[] = [];
  const lead = Math.round(0.5 * fps);
  const typingFrames = Math.min(Math.round(2.4 * fps), take.query.length * 2);

  // Long prompts wrap onto several rows; each row is typed in turn.
  const promptRows = wrapSegs(
    [
      { text: "you> ", bold: true, color: C.text },
      { text: take.query, color: C.text },
    ],
    TERM.cols,
    5,
  );
  const promptChars = promptRows.reduce((n, r) => n + r.reduce((m, s) => m + s.text.length, 0), 0);
  let typedAt = lead;
  promptRows.forEach((segs, i) => {
    const chars = segs.reduce((n, s) => n + s.text.length, 0);
    const frames = Math.max(4, Math.round((typingFrames * chars) / promptChars));
    lines.push({ id: `prompt-${i}`, segs, appear: typedAt, typingFrames: frames, typedPrefix: 5, cursor: true });
    typedAt += frames;
  });

  const cursor = lead + typingFrames + Math.round(0.45 * fps);

  type Item =
    | { kind: "note"; text: string }
    | { kind: "pair"; call: ToolCallEvent; result: ToolResultEvent | null };
  const items: Item[] = [];
  const events = take.events;
  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    if (e.type === "assistant_text") items.push({ kind: "note", text: e.text });
    else if (e.type === "tool_call") {
      const next = events[i + 1];
      const result = next && next.type === "tool_result" ? next : null;
      items.push({ kind: "pair", call: e, result });
      if (result) i += 1;
    }
  }

  const tail = Math.round(2 * fps);
  const answerUnits = Math.max(1, take.answer.split(/\n+/).length);
  let answerFrames = clamp(answerUnits * 9, 3 * fps, 8 * fps);
  const stepsStart = Math.max(cursor, beats?.stepsAt ?? 0);
  let overflow = false;
  let perStep: number;
  let answerStart: number;

  if (beats?.answerAt !== undefined) {
    // Pinned to the narration: the steps fill the time before the answer is due to appear.
    answerStart = beats.answerAt;
    const budget = answerStart - Math.round(0.3 * fps) - stepsStart;
    perStep = items.length ? budget / items.length : 0;
    if (items.length && perStep < 6) overflow = true;
    perStep = clamp(perStep, 6, 90); // slower, more spread-out steps are fine when pinned to the narration
    // The answer streams in over at most 4.5 s, then stays on screen until the scene ends.
    answerFrames = clamp(durationFrames - answerStart - Math.round(0.8 * fps), 2 * fps, 4.5 * fps);
  } else {
    let budget = durationFrames - stepsStart - answerFrames - tail;
    perStep = items.length ? budget / items.length : 0;
    if (items.length && perStep < 8) {
      // Squeeze the answer window before giving up on pacing.
      answerFrames = Math.max(Math.round(2 * fps), answerFrames - (8 * items.length - budget));
      budget = durationFrames - stepsStart - answerFrames - tail;
      perStep = budget / items.length;
      if (perStep < 6) {
        overflow = true;
        perStep = 6;
      }
    }
    perStep = clamp(perStep, 6, 36);
    answerStart = Math.round(stepsStart + items.length * perStep + 0.3 * fps);
  }

  const wrapCols = TERM.cols;
  let n = 0;
  for (const item of items) {
    const at = Math.round(stepsStart + n * perStep);
    if (item.kind === "note") {
      wrapSegs([{ text: item.text, color: C.dim, italic: true }], wrapCols, 0).forEach((segs, k) =>
        lines.push({ id: `note-${n}-${k}`, segs, appear: at }),
      );
    } else {
      wrapSegs(callSegs(item.call), wrapCols, 6).forEach((segs, k) =>
        lines.push({ id: `call-${n}-${k}`, segs, appear: at }),
      );
      if (item.result) {
        const resAt = at + Math.round(clamp(perStep * 0.6, 4, 12));
        wrapSegs(resultSegs(item.result), wrapCols, 7).forEach((segs, k) =>
          lines.push({ id: `res-${n}-${k}`, segs, appear: resAt, isError: !item.result!.ok }),
        );
      }
    }
    n += 1;
  }

  return { lines, answerStart, answerFrames, overflow };
}
