import { AbsoluteFill } from "remotion";
import { C } from "../theme";

/** Dark canvas with a soft top-left glow. Static: keeps every frame cheap to render. */
export const Background: React.FC = () => (
  <AbsoluteFill
    style={{
      backgroundColor: C.bg,
      backgroundImage: `radial-gradient(1200px 700px at 12% -10%, rgba(88,166,255,0.13), transparent 60%),
                        radial-gradient(900px 600px at 100% 110%, rgba(188,140,255,0.10), transparent 60%)`,
    }}
  />
);
