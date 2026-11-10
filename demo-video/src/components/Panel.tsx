import React from "react";
import { C, FONT_MONO, FONT_SANS } from "../theme";

/** Bordered card with a small title chip, used for the assistant's answer and file previews. */
export const Panel: React.FC<{
  title: string;
  width: number;
  height: number;
  color?: string;
  mono?: boolean;
  children: React.ReactNode;
}> = ({ title, width, height, color = C.green, mono, children }) => (
  <div
    style={{
      width,
      height,
      position: "relative",
      boxSizing: "border-box",
      borderRadius: 16,
      border: `2px solid ${color}`,
      background: "rgba(22,27,34,0.92)",
      boxShadow: "0 24px 60px rgba(0,0,0,0.45)",
      padding: "46px 30px 8px",
      overflow: "hidden",
    }}
  >
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        height: 38,
        display: "flex",
        alignItems: "center",
        padding: "0 22px",
        background: `${color}22`,
        borderBottom: `1px solid ${color}55`,
        color,
        fontFamily: mono ? FONT_MONO : FONT_SANS,
        fontSize: 20,
        fontWeight: 700,
        letterSpacing: mono ? 0 : 1.5,
        textTransform: mono ? "none" : "uppercase",
      }}
    >
      {title}
    </div>
    {children}
  </div>
);
