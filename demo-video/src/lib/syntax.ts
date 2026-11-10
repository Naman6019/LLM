import { C } from "../theme";

export type Tok = { text: string; color: string; bold?: boolean; italic?: boolean };

const PY_KEYWORDS = new Set([
  "def", "return", "if", "else", "elif", "not", "raise", "from", "import", "class", "try",
  "except", "finally", "for", "in", "with", "as", "and", "or", "is", "None", "True", "False",
  "lambda", "yield", "pass", "while", "assert", "await", "async",
]);

const DEFAULT = C.text;

/** Tiny Python highlighter: enough for readable code on a video, not a full lexer. */
export function highlightPython(code: string): Tok[][] {
  const out: Tok[][] = [];
  let inDoc = false;

  for (const line of code.split("\n")) {
    const toks: Tok[] = [];
    let i = 0;

    if (inDoc) {
      const end = line.indexOf('"""');
      if (end === -1) {
        out.push([{ text: line, color: C.comment, italic: true }]);
        continue;
      }
      toks.push({ text: line.slice(0, end + 3), color: C.comment, italic: true });
      i = end + 3;
      inDoc = false;
    }

    let prevWord = "";
    while (i < line.length) {
      const rest = line.slice(i);
      let m: RegExpMatchArray | null;

      if (rest.startsWith('"""')) {
        const close = rest.indexOf('"""', 3);
        if (close === -1) {
          toks.push({ text: rest, color: C.comment, italic: true });
          inDoc = true;
          i = line.length;
        } else {
          toks.push({ text: rest.slice(0, close + 3), color: C.comment, italic: true });
          i += close + 3;
        }
      } else if (rest.startsWith("#")) {
        toks.push({ text: rest, color: C.comment, italic: true });
        i = line.length;
      } else if ((m = rest.match(/^(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/))) {
        toks.push({ text: m[0], color: C.str });
        i += m[0].length;
      } else if ((m = rest.match(/^@\w+/))) {
        toks.push({ text: m[0], color: C.decorator });
        i += m[0].length;
      } else if ((m = rest.match(/^\d+(?:\.\d+)?/))) {
        toks.push({ text: m[0], color: C.num });
        i += m[0].length;
      } else if ((m = rest.match(/^[A-Za-z_]\w*/))) {
        const word = m[0];
        const isCall = rest[word.length] === "(";
        let color: string = DEFAULT;
        let bold = false;
        if (PY_KEYWORDS.has(word)) color = C.keyword;
        else if (prevWord === "def") {
          color = C.fn;
          bold = true;
        } else if (isCall) color = C.fn;
        toks.push({ text: word, color, bold });
        prevWord = word;
        i += word.length;
        continue;
      } else {
        toks.push({ text: rest[0], color: DEFAULT });
        i += 1;
      }
      if (!/^\s/.test(rest)) prevWord = "";
    }
    out.push(toks);
  }
  return out;
}

/** JSON highlighter (keys vs string values vs literals). */
export function highlightJson(code: string): Tok[][] {
  return code.split("\n").map((line) => {
    const toks: Tok[] = [];
    // The string alternative tolerates a missing closing quote (lines we truncated for display).
    const re = /("(?:[^"\\]|\\.)*"?)(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?)|([^"\w-]+|[\w-]+)/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(line)) !== null) {
      if (m[1] !== undefined) {
        toks.push({ text: m[1], color: m[2] ? C.num : C.str });
        if (m[2]) toks.push({ text: m[2], color: DEFAULT });
      } else if (m[3] !== undefined) toks.push({ text: m[3], color: C.keyword });
      else if (m[4] !== undefined) toks.push({ text: m[4], color: C.num });
      else toks.push({ text: m[5], color: DEFAULT });
    }
    return toks;
  });
}

/**
 * Condense "decorator + signature + long docstring + body" to "decorator + signature + one-line
 * docstring", so four tools fit on one screen.
 */
export function condenseTool(source: string): string {
  const lines = source.split("\n");
  const docStart = lines.findIndex((l) => l.trim().startsWith('"""'));
  if (docStart === -1) return source;
  const first = lines[docStart].trim().replace(/^"""/, "").replace(/"""$/, "").trim();
  const summary =
    first || (lines[docStart + 1] ?? "").trim().replace(/"""$/, "").trim();
  return [...lines.slice(0, docStart), `    """${summary}"""`].join("\n");
}

/** 1-based line numbers (from, to) of the first block that contains `needle`. */
export function findLine(code: string, needle: string): number | null {
  const idx = code.split("\n").findIndex((l) => l.includes(needle));
  return idx === -1 ? null : idx + 1;
}
