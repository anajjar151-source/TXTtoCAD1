/**
 * Injection molding: a moulded part cooling in its mould from the melt until it can be ejected, and how it warps.
 * It opens on the time to the ejection temperature (the last to cool reads hottest, where it sinks), with the
 * scrubber over the temperature and the warp drawn larger than life; Play runs the cooling. Its findings (sink,
 * walls, warp) are its verdict; it marks nothing on the part, as the study names no faces.
 */
import { fieldAndDeformation } from "../controls.js";
import { planned, playSeries } from "./stub.js";
import { fieldAndTime } from "./thermal_transient.js";

export { PLAY } from "./stub.js";

/** The field and the time scrubber, then the warp's deformation. */
export function fieldTimeAndWarp(result) {
  return [...fieldAndTime(result), fieldAndDeformation(result)[1]];
}

export default planned({
  name: "molding", tier: 3, word: "Injection molding", noun: "this moulding", limitWord: "Starts packed",
  checks: [],
  defaultControls: fieldTimeAndWarp,
  routine: playSeries,
  markers: [],
});
