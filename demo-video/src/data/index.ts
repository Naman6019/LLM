import raw from "./demo-data.json";
import type { DemoData, Take, TakeId } from "./types";

/** Real data captured by scripts/capture_demo_data.py (see README). */
export const demo = raw as unknown as DemoData;

export const getTake = (id: TakeId): Take | undefined =>
  demo.takes.find((t) => t.id === id);

/** "2026-11-10T18:20:19+00:00" -> "10 Nov 2026" */
export const capturedOn = (): string => {
  const d = new Date(demo.meta.captured_at);
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
};
