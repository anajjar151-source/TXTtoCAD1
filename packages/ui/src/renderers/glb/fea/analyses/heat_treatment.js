/**
 * Heat treatment: a steel part quench hardened. It opens on the hardness as quenched (soft spots read
 * cold) at the moment of the largest temperature spread, with the scrubber over the temperature, the
 * distortion drawn by the deformation control, and Play runs the quench. Its findings (soft spots,
 * the quench's stress against the steel's hot strength, sharp edges and thick-to-thin sections) are
 * its verdict; it marks nothing on the part, as the whole part is quenched.
 */
import { planned, playSeries } from "./stub.js";

export { PLAY } from "./stub.js";

export default planned({
  name: "heat_treatment", tier: 3, word: "Heat treatment", noun: "this quench", limitWord: "Thermal only",
  checks: [],
  routine: playSeries,
  markers: [],
});
