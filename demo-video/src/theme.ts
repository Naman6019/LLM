import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";

const inter = loadInter("normal", {
  weights: ["400", "600", "800"],
  subsets: ["latin"],
});
const mono = loadMono("normal", {
  weights: ["400", "700"],
  subsets: ["latin"],
});

export const FONT_SANS = inter.fontFamily;
export const FONT_MONO = mono.fontFamily;

/** GitHub-dark inspired palette. */
export const C = {
  bg: "#0b0f14",
  bgSoft: "#10161d",
  panel: "#161b22",
  panelAlt: "#1c232c",
  border: "#30363d",
  text: "#e6edf3",
  dim: "#8b949e",
  faint: "#586069",
  cyan: "#58a6ff",
  green: "#3fb950",
  red: "#f85149",
  yellow: "#d29922",
  purple: "#bc8cff",
  orange: "#ffa657",
  pink: "#ff7b72",
  blue: "#a5d6ff",
  // syntax
  keyword: "#ff7b72",
  fn: "#d2a8ff",
  str: "#a5d6ff",
  num: "#79c0ff",
  comment: "#8b949e",
  decorator: "#ffa657",
} as const;

/** File-type accent colours used for the resume listing. */
export const EXT_COLOR: Record<string, string> = {
  ".pdf": C.red,
  ".docx": C.cyan,
  ".txt": C.dim,
};

/** Terminal text metrics (JetBrains Mono advance width is 0.6em). */
export const TERM = {
  fontSize: 26,
  lineHeight: 38,
  charWidth: 26 * 0.6,
  cols: 100,
} as const;
