/**
 * Casting: a casting freezing in its mould, from the pour to solid. It opens on the time to solid (the
 * last to freeze reads hottest, where shrinkage collects), with the scrubber over temperature and liquid
 * fraction, and Play runs the freeze. Its findings (hot spots, low Niyama, a section that freezes before
 * the mould fills) are its verdict; it marks nothing on the part, as its feeders are faces of the casting.
 */
import { planned, playSeries } from "./stub.js";
import { fieldAndTime } from "./thermal_transient.js";

export { PLAY } from "./stub.js";

export default planned({
  name: "casting", tier: 3, word: "Casting", noun: "this casting", limitWord: "Starts full",
  checks: [],
  defaultControls: fieldAndTime,
  routine: playSeries,
  markers: [],
});
