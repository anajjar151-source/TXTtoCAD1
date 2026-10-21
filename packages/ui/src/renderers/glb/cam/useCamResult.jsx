import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { readFileView } from "../../kit/shell/fileView.js";
import { ViewerHostContext } from "../../../host/context.js";
import { carriesCamJob } from "./detect.js";

/**
 * What GlbRenderer needs to show a CAM result (`cadgen cam plan`): the result's own viewer, loaded as its own chunk
 * (`camView.jsx`), the job read from the file, what the view shows of its paths, stock, fixtures and tool, the
 * routines that run the cut, and Job, a section of the file sidebar whose rows are Quick Edit's chips. A GLB that is
 * not a result gets nulls throughout.
 *
 * `useCamResult` runs before the shell is made (what the shell is given), `useCamChrome` after it (the sidebar
 * section, the chips and the viewport overlay, which read the shell).
 */

const EMPTY = Object.freeze([]);
// What a CAM result's Show rows keep in the file's view, written against the result's schema.
const CAM_SIGNATURE = "cam:1";
const NO_CAM_CHOICE = Object.freeze({ result: null, id: "" });

// The CAM result viewer (`camView.jsx`), once a result has loaded it, for every result after it.
let camView = null;
/** Loads the CAM result viewer: its own chunk, which a plain GLB never fetches. */
export const loadCamView = () => import("../camView.jsx").then((module) => { camView = module; return module; });

/**
 * The CAM result viewer for a scene that carries a job (`kit`), loaded the first time one does; `pending` while it
 * loads. A plain GLB's `kit` is null, and so is a result's should the chunk fail to load: it is then drawn as a plain GLB.
 */
export function useCamView(root) {
  const wanted = useMemo(() => carriesCamJob(root), [root]);
  const [kit, setKit] = useState(camView);
  useEffect(() => {
    if (!wanted || kit) return undefined;
    let live = true;
    loadCamView().then((module) => { if (live) setKit(module); }, () => { if (live) setKit(false); });
    return () => { live = false; };
  }, [wanted, kit]);
  return { kit: wanted && kit ? kit : null, pending: wanted && kit === null };
}

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
const systemReducesMotion = () => typeof window !== "undefined" && window.matchMedia?.(REDUCED_MOTION_QUERY)?.matches === true;

/** Whether motion is reduced: the app's own setting (the host's `reducedMotion`) or the system's `prefers-reduced-motion`. */
export function useReducedMotion() {
  const app = useContext(ViewerHostContext)?.environment?.reducedMotion === true;
  const [system, setSystem] = useState(systemReducesMotion);
  useEffect(() => {
    const query = typeof window !== "undefined" ? window.matchMedia?.(REDUCED_MOTION_QUERY) : null;
    if (!query?.addEventListener) return undefined;
    const change = () => setSystem(query.matches === true);
    query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);
  return app || system;
}

/**
 * A CAM result's state, before the shell: `cam` (the job; null for any other GLB), its routines (`ownClips`), the
 * renderer's slice of the file's view (`rendererState`: the Show rows and the hidden operations; null for any other
 * GLB), the row chosen in Job (`choice`) and what Quick Edit carries for it (`references`).
 * `shellRef` is the renderer's, filled once the shell exists: its frames and its view saves.
 */
export function useCamResult({ cv, scene, view, shellRef }) {
  // A CAM result carries its job in the file: its verdict, setups and operations (Job), its toolpaths and its
  // simulated stock. What the view shows of it is this renderer's one slice of the file's view.
  const root = scene?.document?.scene || null;
  const cam = useMemo(() => (cv && root ? cv.readCamJob(root) : null), [cv, root]);
  const scheme = view.appearance?.colorScheme === "dark" ? "dark" : "light";
  const meshes = useMemo(() => (cam ? cv.camSceneMeshes(root) : null), [cam, root]);
  const pathKinds = useMemo(() => (cam ? cv.camPathKinds(root) : null), [cam, root]);
  const colours = useMemo(() => (cam ? cv.camOpColours(cam, scheme) : null), [cam, scheme]);
  const [stored] = useState(() => view.state);
  const [edited, setEdited] = useState(null);
  const shown = useMemo(() => (cam ? { ...cv.CAM_SHOWN, ...(readFileView(stored, { cam: CAM_SIGNATURE }).renderer.cam || {}), ...(edited || {}) } : null),
    [cam, stored, edited]);
  const shownRef = useRef(shown);
  shownRef.current = shown;
  const rendererState = useMemo(() => (cam ? { signatures: { cam: CAM_SIGNATURE }, read: () => ({ cam: shownRef.current }) } : null), [cam]);
  const show = useCallback((patch) => {
    setEdited((current) => ({ ...(current || {}), ...patch }));
    shellRef.current?.scheduleStateSave();
  }, [shellRef]);
  // The operations put away by their eyes in Job, kept with the Show rows in the file's view.
  const hidden = useMemo(() => (cam ? cv.camHidden(cam, shown) : null), [cv, cam, shown]);
  const toggleHidden = useCallback((index) => show({ hidden: cv.toggleCamHidden(shownRef.current, index) }), [cv, show]);
  const gates = useMemo(() => (cam ? cv.camGates({ job: cam, meshes, paths: pathKinds, shown }) : null), [cv, cam, meshes, pathKinds, shown]);
  const toggleGate = useCallback((id, on) => show({ [id]: on }), [show]);

  // A row of Job chosen (an operation, a setup, a tool, an error): its paths isolated, and its faces and sentence for Quick Edit.
  const [chosenRow, setChosenRow] = useState(NO_CAM_CHOICE);
  const choices = useMemo(() => (cam ? cv.camChoices(cam) : null), [cam]);
  const choice = cam && chosenRow.result === cam ? choices.get(chosenRow.id) || null : null;
  const clearChoice = useCallback(() => setChosenRow((current) => (current.id ? NO_CAM_CHOICE : current)), []);
  const chooseRow = useCallback((id) => setChosenRow((current) => (current.result === cam && current.id === id ? NO_CAM_CHOICE : { result: cam, id })), [cam]);
  const isolate = useMemo(() => (choice ? new Set(choice.ops) : null), [choice]);
  // The part the job was planned from, the file a choice's references name.
  const source = useMemo(() => (cam ? cv.camSourcePath(view.file.path, cam.document) : ""), [cam, view.file.path]);
  const references = useMemo(() => (cam ? cv.camReferences(source, choice) : EMPTY), [cam, source, choice]);

  // The toolpaths and the tool, once the viewport has drawn them (`CamPaths`); the moment a Simulate clip plays.
  const camRef = useRef(null);
  const momentRef = useRef(null);
  const paintRef = useRef(null);
  // The readout at the view's foot (`CamReadout`), written as the clip plays; the routine's speed and whether motion is reduced.
  const readoutRef = useRef(null);
  const speedRef = useRef(1);
  const reducedMotion = useReducedMotion();
  paintRef.current = () => {
    if (!cam) return;
    const moment = momentRef.current;
    const painted = cv.paintCam({ controller: camRef.current, meshes, job: cam, shown, isolate, moment });
    readoutRef.current?.(moment ? cv.camReadoutWords(cam, moment, { op: painted.place?.op ?? null, speed: speedRef.current, reducedMotion }) : null);
    if (painted.changed) shellRef.current?.requestRender();
  };
  const paint = useCallback(() => paintRef.current?.(), []);
  useEffect(() => { paint(); }, [cam, shown, isolate, paint]);
  // Simulate, and one per setup, among the file's routines (the file sidebar's Animation section): the paths drawn up
  // to the moment and the tool on them; with motion reduced, one operation a second.
  const ownClips = useMemo(() => (cam ? cv.camClips(cam, (moment) => { momentRef.current = moment; paint(); }, { reducedMotion }) : EMPTY),
    [cam, paint, reducedMotion]);
  return {
    cv, cam, root, scheme, colours, choice, chooseRow, clearChoice, hidden, toggleHidden, gates, toggleGate, references, ownClips,
    rendererState, refs: { camRef, readoutRef, speedRef }, paint,
  };
}

/**
 * A CAM result's chrome, after the shell, or null for any other GLB: Job, its file sidebar section (`sidebar`); the
 * chosen row as Quick Edit's chip (`chips`, with `references`); and what is drawn over the viewport (`overlay`): the
 * toolpaths, the tool and the fixtures, and the readout while a routine plays.
 */
export function useCamChrome({ result, scene, animation }) {
  const { cv, cam, root, scheme, colours, choice, chooseRow, clearChoice, hidden, toggleHidden, gates, toggleGate, references, refs, paint } = result;
  refs.speedRef.current = animation?.speed || 1;
  // A new routine speed says so in the readout at once, paused or not.
  useEffect(() => { paint(); }, [animation?.speed, paint]);
  const chips = useMemo(() => (cam ? cv.camChips(choice, references, { colours, onRemove: clearChoice }) : EMPTY),
    [cv, cam, choice, references, colours, clearChoice]);
  if (!cam) return null;
  return {
    sidebar: <cv.CamJobPanel job={cam} colours={colours} chosen={choice?.id || ""} onChoose={chooseRow}
      hidden={hidden} onToggleHidden={toggleHidden} gates={gates} onToggleGate={toggleGate} />,
    references, chips,
    overlay: (viewport) => <>
      <cv.CamPaths runtimeRef={viewport.runtimeRef} viewerReadyTick={viewport.viewerReadyTick} root={root}
        cadRoot={scene.object3D} job={cam} scheme={scheme} controllerRef={refs.camRef} onChange={paint} />
      <cv.CamReadout readoutRef={refs.readoutRef} />
    </>,
  };
}
