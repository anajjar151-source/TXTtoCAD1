/**
 * Sheet metal (estimate), Tier 2: every bend of a bent sheet off the press brake, by hand formulas. It opens on each
 * bend's springback, drawn true to scale as the part comes off the brake (each bend opened by its springback, the
 * flats past it turned with it, out from the held flat), with the outer strain over its limit as the other field.
 * Spring back plays the release: the displacement from none to the springback, raised where it moves too little to
 * see. Its findings (a bend that may crack, springback past the tolerance, a missing relief) are its verdict; it marks
 * nothing on the part.
 */
import { fieldAndDeformation } from "../controls.js";
import { planned } from "./stub.js";

/** Spring back: the part released from the press brake, from its CAD shape to its shape off the brake (GlbRenderer
 * plays it as a load ramp). */
export const SPRING_BACK = Object.freeze({ id: "fea:spring-back", label: "Spring back", kind: "load_ramp" });

export default planned({
  name: "sheet_metal", tier: 2, word: "Sheet metal", noun: "this bend", estimate: true,
  checks: [],
  defaultControls: fieldAndDeformation,
  routine: () => SPRING_BACK,
  markers: [],
});
