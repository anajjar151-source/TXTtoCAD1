/**
 * Machining: a part under one milling or turning cut. It opens on the displacement under the cut (the
 * cutter is put where the cut faces give most, its force the Pushed row's arrow), with the stress and
 * the shape the part rings in at the cut beside it, and the Load ramp pushes the cut on. Its findings
 * (the deflection against the tolerance, the stress against yield, chatter at the spindle speed) are
 * its verdict, so it judges no check kinds of its own.
 */
import { fieldAndDeformation } from "../controls.js";
import { heldRows, madeOfRows, pushedRows } from "../setup.js";
import { LOAD_RAMP } from "./static.js";
import { planned } from "./stub.js";

export default planned({
  name: "machining", tier: 3, word: "Machining", noun: "this cut", limitWord: "Lite",
  checks: [],
  defaultControls: fieldAndDeformation,
  setupGroups: [heldRows, pushedRows, madeOfRows],
  routine: () => LOAD_RAMP,
  markers: ["load", "fixture"], displayTitle: "Clamps and the cut",
});
