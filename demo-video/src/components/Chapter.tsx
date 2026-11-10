import { Easing, interpolate, useCurrentFrame } from "remotion";
import { C, FONT_SANS } from "../theme";

/** Small "PART A / PART B" pill at the top-left of a scene. */
export const Chapter: React.FC<{ tag: string; title: string }> = ({ tag, title }) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  return (
    <div
      style={{
        position: "absolute",
        left: 100,
        top: 44,
        display: "flex",
        alignItems: "center",
        gap: 18,
        fontFamily: FONT_SANS,
        opacity: t,
        translate: `0px ${(1 - t) * -14}px`,
      }}
    >
      <span
        style={{
          fontSize: 24,
          fontWeight: 800,
          letterSpacing: 3,
          color: C.bg,
          background: C.cyan,
          padding: "8px 18px",
          borderRadius: 999,
        }}
      >
        {tag}
      </span>
      <span style={{ fontSize: 40, fontWeight: 600, color: C.text }}>{title}</span>
    </div>
  );
};
