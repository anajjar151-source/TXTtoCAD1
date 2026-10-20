import SelectFilterMenu from "../select/SelectFilterMenu.jsx";
import { modeGlyphIcon } from "../select/modeGlyphs.jsx";
import { MEASURE_SNAP_KINDS } from "./measureFilter.js";

// Each kind's glyph, Select's own: a point in a ring for Vertices, the cube with an edge or a face drawn solid.
const GLYPHS = Object.freeze({ vertex: "points", edge: "edges", face: "faces" });
const KINDS = MEASURE_SNAP_KINDS.map(kind => ({ ...kind, icon: modeGlyphIcon(GLYPHS[kind.id]) }));

/**
 * Measure's selection filter: the chevron after its button on the strip, Select's own menu
 * (`SelectFilterMenu.jsx`) with what Measure snaps to (`measureFilter.js`): Select all, then
 * Vertices, Edges and Faces.
 *
 * @param {{ value: readonly string[], onChange(filter: readonly string[]): void, disabled?: boolean }} props
 */
export default function MeasureFilterMenu({ value, onChange, disabled = false }) {
  return <SelectFilterMenu value={value} onChange={onChange} kinds={KINDS} disabled={disabled} name="measure" triggerName="Measure filter" />;
}
