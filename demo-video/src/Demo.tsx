import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { AbsoluteFill } from "remotion";
import { CliScene } from "./scenes/CliScene";
import { OutroScene } from "./scenes/OutroScene";
import { TestsScene } from "./scenes/TestsScene";
import { TitleScene } from "./scenes/TitleScene";
import { ToolsScene } from "./scenes/ToolsScene";
import {
  FindPythonScene,
  OverwriteScene,
  ReadAllScene,
  SandboxScene,
  SummaryScene,
} from "./scenes/TakeScenes";
import { SCENE_ORDER, TRANSITION_FRAMES, sceneFrames, type SceneKey } from "./timing";
import { Voiceover } from "./Voiceover";

/** One component per scene, keyed by the names in timing.ts. */
export const SCENES: Record<SceneKey, React.FC> = {
  title: TitleScene,
  tools: ToolsScene,
  tests: TestsScene,
  cli: CliScene,
  readAll: ReadAllScene,
  findPython: FindPythonScene,
  summary: SummaryScene,
  overwrite: OverwriteScene,
  sandbox: SandboxScene,
  outro: OutroScene,
};

export const Demo: React.FC = () => (
  <AbsoluteFill>
    <TransitionSeries>
      {SCENE_ORDER.flatMap((key, i) => {
        const Scene = SCENES[key];
        const sequence = (
          <TransitionSeries.Sequence key={key} name={key} durationInFrames={sceneFrames(key)}>
            <Scene />
          </TransitionSeries.Sequence>
        );
        return i === 0
          ? [sequence]
          : [
              <TransitionSeries.Transition
                key={`${key}-transition`}
                presentation={fade()}
                timing={linearTiming({ durationInFrames: TRANSITION_FRAMES })}
              />,
              sequence,
            ];
      })}
    </TransitionSeries>
    <Voiceover />
  </AbsoluteFill>
);
