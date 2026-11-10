import { Composition, Folder } from "remotion";
import { Demo, SCENES } from "./Demo";
import { FPS, HEIGHT, SCENE_ORDER, TOTAL_FRAMES, WIDTH, sceneFrames } from "./timing";

export const RemotionRoot: React.FC = () => (
  <>
    {/* The finished video: all scenes joined with cross-fades (+ voiceover, once you add it). */}
    <Composition id="Demo" component={Demo} width={WIDTH} height={HEIGHT} fps={FPS} durationInFrames={TOTAL_FRAMES} />

    {/* Each scene on its own, for previewing and timing the voiceover scene by scene. */}
    <Folder name="Scenes">
      {SCENE_ORDER.map((key) => (
        <Composition
          key={key}
          id={key}
          component={SCENES[key]}
          width={WIDTH}
          height={HEIGHT}
          fps={FPS}
          durationInFrames={sceneFrames(key)}
        />
      ))}
    </Folder>
  </>
);
