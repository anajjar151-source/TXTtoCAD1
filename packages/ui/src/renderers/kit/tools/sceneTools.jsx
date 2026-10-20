import { useRef, useState } from "react";
import { sceneFramingBounds } from "@text-to-cad/core/lib/viewer/sceneContract.js";
import { boundsInUnits } from "@text-to-cad/core/lib/viewer/sceneUnits.js";
import { useModelTools } from "./model-effects/ModelTools.jsx";
import { useMeasureSession } from "./measure/useMeasureSession.js";
import { useQuickEditMeasurements } from "./measure/measurementChips.jsx";
import { measureSelectHandlers } from "./measure/measureSelection.js";
import { MeasureIcon, SCENE_MEASURE_TOOL, SceneMeasureOverlay } from "./measure/SceneMeasure.jsx";
import MeasureFilterMenu from "./measure/MeasureFilterMenu.jsx";
import { MEASURE_FILTER_DEFAULT } from "./measure/measureFilter.js";

// The tools a scene the kit draws offers, in two halves around the shell: what Quick Edit must know
// before the shell is made (the tool in hand, Measure's session), and the strip, the row under it
// and the layer over the view, made from the shell. Which of them a file has is its renderer's:
// Select is the renderer's own, Annotate the shell's, Measure where the file says its unit, and the
// model effects where its view's features offer them (`model-effects/ModelTools.jsx`).

/**
 * The first half: the tool in hand (never saved; a file opens in its default), and Measure's session
 * and Quick Edit's view of it where the file can be measured.
 *
 * @param {{ toolModes: ReturnType<typeof import("./toolModes.js").createToolModes>, previewing: boolean,
 *   fileKey: string, revision: string, measurable: boolean, resource: object }} options
 */
export function useSceneToolState({ toolModes, previewing, fileKey, revision, measurable, resource }) {
  const [mode, set] = useState(toolModes.defaultMode);
  // What Measure snaps to (`measure/measureFilter.js`): every kind when a file opens.
  const [measureFilter, setMeasureFilter] = useState(MEASURE_FILTER_DEFAULT);
  const measure = useMeasureSession({ fileKey, revision, picking: measurable && !previewing && mode === SCENE_MEASURE_TOOL });
  const measurements = useQuickEditMeasurements(measure);
  return { tool: { mode, set }, measure, measurements: measurable ? measurements : null, measuring: measurable && !previewing && mode === SCENE_MEASURE_TOOL,
    measureFilter: { value: measureFilter, set: setMeasureFilter } };
}

/**
 * The second half: the strip's tools after Select (Annotate, Measure, the model effects), the tool in
 * hand's row under the strip, Measure's layer over the view, and Select's press and hover on a
 * measurement.
 *
 * @param {{ shell: ReturnType<typeof import("../shell/useRendererShell.js").useRendererShell>, scene: object | null,
 *   features: import("@text-to-cad/core/common/viewSettings.js").ViewFeatures,
 *   state: ReturnType<typeof useSceneToolState>, measurable: boolean, clearParts?: () => void }} options
 *   `features`: the view's, as the shell was given them: a model effect is offered where they list it.
 */
export function useSceneTools({ shell, scene, features, state, measurable, clearParts = () => {} }) {
  const { measure, measuring, measureFilter } = state;
  const { view, store } = shell.viewSettings;
  // Clip's slider maps in the box the camera frames, in the file's unit, as `clip.at` is.
  const bounds = scene ? boundsInUnits(sceneFramingBounds(scene), scene.units) : null;
  const effects = useModelTools({ view, features, store, mesh: bounds ? { bounds } : null,
    disabled: shell.idle, selectedTool: shell.toolMode, onSelect: shell.selectTool });
  const tools = [
    { ...shell.tools.annotate, disabled: shell.idle },
    measurable ? shell.tools.own({ id: SCENE_MEASURE_TOOL, label: "Measure", icon: <MeasureIcon className="size-3.5" aria-hidden="true" />,
      // What it snaps to: its chevron's filter, whose change takes Measure up, as Select's does Select.
      menu: <MeasureFilterMenu value={measureFilter.value} disabled={shell.idle}
        onChange={value => { measureFilter.set(value); if (shell.toolMode !== SCENE_MEASURE_TOOL) shell.selectTool(SCENE_MEASURE_TOOL); }} />,
      onSelect: () => { if (shell.toolMode !== SCENE_MEASURE_TOOL) shell.selectTool(SCENE_MEASURE_TOOL); } }) : null,
    ...effects.tools
  ].filter(Boolean);
  // Measure has no row under the strip: its measurements are its own chips.
  const subToolbar = measuring ? null : effects.subToolbar;
  const runtime = useRef(null);
  const overlay = viewport => {
    runtime.current = viewport.runtimeRef;
    return measurable ? <SceneMeasureOverlay viewport={viewport} scene={scene} measure={measure} picking={measuring} preview={shell.previewing} snaps={measureFilter.value} /> : null;
  };
  const select = measureSelectHandlers(measure, () => runtime.current?.current, clearParts, { picks: measurable });
  return { tools, subToolbar, overlay, onSelectPress: select.press, onSelectHover: select.hover };
}

