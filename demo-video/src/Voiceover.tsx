import { Audio } from "@remotion/media";
import { Sequence, staticFile } from "remotion";
import { SCENE_ORDER, SCENE_VOICEOVERS, VOICEOVER_FILE, sceneStart } from "./timing";

/**
 * Plays the voiceover: one clip per scene (from src/voiceover.json), each starting when its scene
 * starts, and/or a single file for the whole video (VOICEOVER_FILE in src/timing.ts).
 */
export const Voiceover: React.FC = () => (
  <>
    {VOICEOVER_FILE ? <Audio src={staticFile(VOICEOVER_FILE)} /> : null}
    {SCENE_ORDER.map((key) => {
      const file = SCENE_VOICEOVERS[key];
      return file ? (
        <Sequence key={key} name={`voiceover-${key}`} from={sceneStart(key)} layout="none">
          <Audio src={staticFile(file)} />
        </Sequence>
      ) : null;
    })}
  </>
);
