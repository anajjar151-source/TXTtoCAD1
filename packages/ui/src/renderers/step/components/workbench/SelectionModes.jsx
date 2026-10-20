import { Pencil, Ruler } from 'lucide-react';
import { PositionIcon } from '../../../kit/tools/ChangedDot.jsx';
import { CONNECTED_SELECTION, SELECT_GEOMETRY, connectedSelectionApplies } from '../../workbench/selectionFilter.js';
import { DropdownMenuCheckboxItem } from '@text-to-cad/ui/primitives/dropdown-menu';
import SelectFilterMenu from "../../../kit/tools/select/SelectFilterMenu.jsx";
import { ToolModeIcon, modeGlyphIcon } from "../../../kit/tools/select/modeGlyphs.jsx";

/** The Select tool's button icon: the pointer, whatever it is filtered to pick. */
export function SelectIcon(props) {
  return <ToolModeIcon tool="select" mode="all" {...props} />;
}

/** The Measure tool's button icon: the ruler, whatever its filter snaps to. */
export function MeasureIcon(props) {
  return <ToolModeIcon tool="measure" mode="all" {...props} />;
}

const glyphIcon = modeGlyphIcon;
const lucideIcon = Icon => <Icon className="size-3.5" strokeWidth={2} aria-hidden="true" />;
// What else Select picks, beside the model's geometry: Position's knobs (where the file has joints
// to move), the annotations and measurements.
const SELECT_OVERLAYS = Object.freeze([
  { id: 'position', label: 'Position', icon: lucideIcon(PositionIcon) },
  { id: 'annotation', label: 'Annotations', icon: lucideIcon(Pencil) },
  { id: 'measurement', label: 'Measurement', icon: lucideIcon(Ruler) },
]);
// Each connected-selection option's glyph.
const GROUP_GLYPHS = Object.freeze({ tangentFaces: 'groupFaces', edgeChain: 'groupEdges' });
/** Every kind a STEP's Select can pick, ticked when a file opens: Parts too, which a part file's filter does not offer. */
export const STEP_SELECT_DEFAULT = Object.freeze([...SELECT_GEOMETRY, ...SELECT_OVERLAYS].map(kind => kind.id));

/**
 * A STEP's selection filter (`kit/tools/select/SelectFilterMenu.jsx`): Parts (only in an
 * assembly), Faces, Edges, Position (where the file has joints), Annotations and Measurement, each on
 * its own; then the connected-selection options that do something under it — Group faces while
 * Faces is ticked, Group edges while Edges is. An option that does nothing is not shown, and keeps
 * its choice for when it does.
 *
 * @param {{ value: readonly string[], onChange(filter: readonly string[]): void, assembly: boolean, posable: boolean,
 *   connected: { edgeChain: boolean, tangentFaces: boolean },
 *   onConnectedChange(id: "edgeChain" | "tangentFaces", checked: boolean): void, disabled?: boolean }} props
 */
export function SelectModeMenu({ value, onChange, assembly, posable, connected, onConnectedChange, disabled = false }) {
  const kinds = [
    ...SELECT_GEOMETRY.filter(item => assembly || !item.assemblyOnly).map(item => ({ id: item.id, label: item.label, icon: glyphIcon(item.id) })),
    ...SELECT_OVERLAYS.filter(kind => posable || kind.id !== 'position'),
  ];
  const options = CONNECTED_SELECTION.filter(option => connectedSelectionApplies(option.id, value));
  return <SelectFilterMenu value={value} onChange={onChange} kinds={kinds} disabled={disabled}>
    {options.length ? options.map(option => <DropdownMenuCheckboxItem key={option.id} checked={connected[option.id] === true}
      onSelect={event => event.preventDefault()} onCheckedChange={checked => onConnectedChange(option.id, checked === true)}>
      {glyphIcon(GROUP_GLYPHS[option.id])}{option.label}
    </DropdownMenuCheckboxItem>) : null}
  </SelectFilterMenu>;
}
