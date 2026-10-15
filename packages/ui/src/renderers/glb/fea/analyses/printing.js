/**
 * 3D printing: a part built band by band, each band's inherent strain shrinking it on the part below, then let go of
 * its plate. It opens on its last frame (off the plate), coloured by the residual stress and deformed by the
 * distortion; the scrubber, called Build, steps through the bands ("Band 3/12 · 7.5 mm"), and Play builds it. Its
 * findings (the warp, the distortion, the residual stress, the recoater, the bed's pull) are its verdict; it marks
 * nothing on the part, as its plate is the part's own lowest face.
 */
import { seriesControls } from "../controls.js";
import { planned, playSeries } from "./stub.js";

export { PLAY } from "./stub.js";

/** What you see's controls: the series' own (the scrubber, the field, the deformation), the scrubber called Build. */
export function buildControls(result) {
  return seriesControls(result).map((control) => (control.id === "frame" ? { ...control, label: "Build" } : control));
}

export default planned({
  name: "printing", tier: 3, word: "3D printing", noun: "this print", limitWord: "Lumped layers",
  checks: [],
  defaultControls: buildControls,
  routine: playSeries,
  markers: [],
});
