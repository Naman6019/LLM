import { getTake } from "../data";
import { beats, sceneFrames } from "../timing";
import { TakeScene } from "./TakeScene";

export const ReadAllScene: React.FC = () => (
  <TakeScene take={getTake("read-all")} durationFrames={sceneFrames("readAll")} tag="PART B" title="Read all resumes" pins={beats("readAll")} />
);

export const FindPythonScene: React.FC = () => (
  <TakeScene take={getTake("find-python")} durationFrames={sceneFrames("findPython")} tag="PART B" title="Find Python experience" pins={beats("findPython")} />
);

export const SummaryScene: React.FC = () => (
  <TakeScene take={getTake("summary")} durationFrames={sceneFrames("summary")} tag="PART B" title="Write a summary file" showFile pins={beats("summary")} />
);

export const OverwriteScene: React.FC = () => (
  <TakeScene take={getTake("summary-again")} durationFrames={sceneFrames("overwrite")} tag="SAFETY" title="Overwrite protection" pins={beats("overwrite")} />
);

export const SandboxScene: React.FC = () => (
  <TakeScene take={getTake("sandbox")} durationFrames={sceneFrames("sandbox")} tag="SAFETY" title="Sandbox" pins={beats("sandbox")} />
);
