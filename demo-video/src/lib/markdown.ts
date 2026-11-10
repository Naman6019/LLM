/** A deliberately small Markdown parser: headings, paragraphs, lists, tables, quotes, code fences. */

export type Unit =
  | { kind: "heading"; level: number; text: string }
  | { kind: "para"; text: string }
  | { kind: "quote"; text: string }
  | { kind: "li"; marker: string; indent: number; text: string }
  | { kind: "hr" }
  | { kind: "code"; text: string }
  | { kind: "thead"; cells: string[]; weights: number[] }
  | { kind: "trow"; cells: string[]; weights: number[] };

const isTableRow = (l: string) => /^\s*\|.*\|\s*$/.test(l);
const isTableSep = (l: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);
const splitRow = (l: string) =>
  l
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());

export const plain = (s: string) => s.replace(/\*\*|__|`/g, "").replace(/\*(?=\S)|(?<=\S)\*/g, "");

export function parseMarkdown(src: string): Unit[] {
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const out: Unit[] = [];
  let para: string[] = [];
  const flush = () => {
    if (para.length) out.push({ kind: "para", text: para.join(" ").trim() });
    para = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (/^\s*```/.test(line)) {
      flush();
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !/^\s*```/.test(lines[i])) body.push(lines[i++]);
      out.push({ kind: "code", text: body.join("\n") });
      continue;
    }
    if (!line.trim()) {
      flush();
      continue;
    }
    if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      flush();
      const header = splitRow(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && isTableRow(lines[i])) rows.push(splitRow(lines[i++]));
      i -= 1;
      const weights = header.map((h, c) => {
        const longest = Math.max(plain(h).length, ...rows.map((r) => plain(r[c] ?? "").length));
        return Math.pow(Math.min(Math.max(longest, 8), 60), 0.8);
      });
      out.push({ kind: "thead", cells: header, weights });
      rows.forEach((r) => out.push({ kind: "trow", cells: r, weights }));
      continue;
    }
    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flush();
      out.push({ kind: "hr" });
      continue;
    }
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      flush();
      out.push({ kind: "heading", level: h[1].length, text: h[2].trim() });
      continue;
    }
    const li = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if (li) {
      flush();
      const ordered = /\d/.test(li[2]);
      out.push({
        kind: "li",
        marker: ordered ? li[2] : "•",
        indent: Math.floor(li[1].length / 2),
        text: li[3].trim(),
      });
      continue;
    }
    const q = line.match(/^\s*>\s?(.*)$/);
    if (q) {
      flush();
      out.push({ kind: "quote", text: q[1] });
      continue;
    }
    para.push(line.trim());
  }
  flush();
  return out;
}

/**
 * Rough rendered height (px) of `units` in a column `widthPx` wide, used to size the answer panel.
 * Deliberately an estimate: the panel scrolls if the real content turns out taller.
 */
export function estimateHeight(units: Unit[], widthPx: number, fontSize: number): number {
  const lineH = fontSize * 1.42;
  const cpl = Math.max(20, Math.floor(widthPx / (fontSize * 0.5)));
  let h = 0;
  for (const u of units) {
    switch (u.kind) {
      case "heading":
        h += fontSize * 1.25 * 1.42 + 14;
        break;
      case "para":
      case "quote":
        h += Math.ceil(plain(u.text).length / cpl) * lineH + 12;
        break;
      case "li":
        h += Math.ceil(plain(u.text).length / (cpl - 6 - u.indent * 6)) * lineH + 8;
        break;
      case "code":
        h += (u.text.split(/\r?\n/).length + Math.ceil(u.text.length / (cpl * 1.25))) * fontSize * 1.15 + 40;
        break;
      case "hr":
        h += 26;
        break;
      case "thead":
      case "trow": {
        const per = Math.max(10, Math.floor(cpl / u.cells.length));
        const rows = Math.max(...u.cells.map((c) => Math.ceil(plain(c).length / per)));
        h += rows * lineH * 0.9 + 15;
        break;
      }
    }
  }
  return Math.round(h);
}
