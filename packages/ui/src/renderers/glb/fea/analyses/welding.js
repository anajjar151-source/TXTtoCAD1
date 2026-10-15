/**
 * Welding: the distortion and residual stress welds leave in the part they join. It opens on the residual stress,
 * deformed by the distortion (its rigid motion taken out), with the stress along the welds and the weld zones beside
 * it. Every weld acts at once, so it has no frames to play. Its findings (the distortion against the tolerance, each
 * joint's angular distortion, the bow, the stress along the welds) are its verdict; it marks nothing on the part, as
 * its welds run along the part's own edges.
 */
import { fieldAndDeformation } from "../controls.js";
import { planned } from "./stub.js";

export default planned({
  name: "welding", tier: 3, word: "Welding", noun: "these welds", limitWord: "All at once",
  checks: [],
  defaultControls: fieldAndDeformation,
  routine: () => null,
  markers: [],
});
