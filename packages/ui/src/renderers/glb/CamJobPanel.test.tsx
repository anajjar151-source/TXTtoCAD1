import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createPromptContext, formatPromptMessage } from '@text-to-cad/core/prompt';
import CamJobPanel, { camChoices } from '../../../dist/renderers/glb/CamJobPanel.js';
import * as THREE from 'three';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import { createGlbScene } from '@text-to-cad/core/lib/render/glbScene.js';
import { CAM_SHOWN, CamPaths, CamReadout, camChips, camGates, camHidden, camPathKinds, camReferences, paintCam, toggleCamHidden } from '../../../dist/renderers/glb/camView.js';
import { camOpColours } from '../../../dist/renderers/glb/cam/colours.js';
import { readCamJob } from '../../../dist/renderers/glb/cam/extras.js';
import { camSceneMeshes } from '../../../dist/renderers/glb/cam/playback.js';
import { camExtras, camScene } from './__tests__/camFile';

beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const job = () => readCamJob(camScene())!;

it('leads with the verdict and its errors, then each setup with its operations: word, tool, time', () => {
  const onChoose = vi.fn();
  const { container } = render(<CamJobPanel job={job()} colours={camOpColours(job())} chosen="" onChoose={onChoose} />);
  expect(screen.getByRole('region', { name: 'Job' })).toBeTruthy();
  const verdict = container.querySelector('[data-cam-verdict]')!;
  expect(verdict.getAttribute('data-cam-verdict')).toBe('fix');
  expect(verdict.querySelector('[data-cam-verdict-title]')!.textContent).toBe('1 to fix');
  // What the job takes, under the headline: its tool changes and the controller its G-code is for.
  expect(verdict.querySelector('[data-cam-summary]')!.textContent).toBe('1 tool change · grbl controller');
  expect(verdict.querySelector('[data-cam-verdict-caption]')!.textContent).toBe('G-code not written: fix 1 error first · 2 warnings');
  // Errors alone, in plain words, under the verdict; warnings go to the agent.
  expect([...verdict.querySelectorAll('[data-cam-finding]')].map((row) => row.textContent)).toEqual(['Tool too long for this pocket']);
  const rows = [...container.querySelectorAll('[data-cam-row]')].map((row) => [row.getAttribute('data-cam-row'), row.textContent]);
  expect(rows).toEqual([['setup:top', 'Top2 operations · 2 min'], ['op:0', 'Face6 mm flat · 30 s'], ['op:1', 'Pocket4 mm ball · 1 min'],
    // The tools after the operations, each with the speed and feed it runs at.
    ['tool:T1', 'T1 6 mm flat12,000 rpm · 1,440 mm/min'], ['tool:T3', 'T3 4 mm ball15,000 rpm · 900 mm/min']]);
  expect(container.querySelectorAll('[data-cam-swatch]')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button', { name: 'Select Pocket' }));
  expect(onChoose).toHaveBeenLastCalledWith('op:1');
  fireEvent.click(screen.getByRole('button', { name: 'Select Tool too long for this pocket' }));
  expect(onChoose).toHaveBeenLastCalledWith('finding:0');
});

it('says under the verdict what the plan assumed, one small line each with its reason on hover', () => {
  const extras = camExtras();
  extras.assumed = [{ key: 'machine.post', value: 'fanuc', why: 'no machine model or post given' }, { key: 'machine.max_rpm', value: 8000, why: 'a spindle limit' }];
  const assumed = readCamJob(camScene({ extras }))!;
  const { container } = render(<CamJobPanel job={assumed} colours={{}} chosen="" onChoose={() => {}} />);
  const lines = [...container.querySelectorAll('[data-cam-verdict] [data-cam-assumed] li')];
  expect(lines.map((line) => line.textContent)).toEqual(['Assumed machine.post fanuc', 'Assumed machine.max_rpm 8000']);
  expect(lines[0].getAttribute('title')).toBe('no machine model or post given');
  cleanup();
  const { container: plain } = render(<CamJobPanel job={job()} colours={{}} chosen="" onChoose={() => {}} />);
  expect(plain.querySelector('[data-cam-assumed]')).toBeNull();
});

it('marks the row chosen', () => {
  render(<CamJobPanel job={job()} colours={{}} chosen="op:0" onChoose={() => {}} />);
  expect(screen.getByRole('button', { name: 'Select Face' }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('button', { name: 'Select Pocket' }).getAttribute('aria-pressed')).toBe('false');
});

it('carries a row into Quick Edit: the part\'s faces with the operation\'s sentence, or the whole part', () => {
  const choices = camChoices(job());
  const pocket = camReferences('/work/part.step', choices.get('op:1'));
  expect(pocket).toEqual([{ resource: { kind: 'workspace-file', path: '/work/part.step' }, target: { kind: 'cad-selector', selectors: ['o1.f12', 'o1.f13'] },
    summary: 'Pocket #o1.f12 with T3 4 mm ball, 60 s' }]);
  const message = formatPromptMessage(createPromptContext([{ id: 'r', kind: 'reference', reference: pocket[0] }]));
  expect(message).toContain('Pocket #o1.f12 with T3 4 mm ball, 60 s · /work/part.step#o1.f12,o1.f13');
  expect(camReferences('/work/part.step', choices.get('op:0'))[0].target).toEqual({ kind: 'whole-resource' });
  expect(choices.get('setup:top')).toMatchObject({ label: 'Top setup', ops: [0, 1], faces: ['#o1.f12', '#o1.f13'], summary: 'Top setup: Face, Pocket, 2 min' });
  expect(choices.get('finding:0')).toMatchObject({ label: 'Tool too long for this pocket', ops: [1],
    summary: 'Tool too long for this pocket (Pocket #o1.f12 with T3 4 mm ball, 60 s)' });
  // A result with no part to name has no references; nothing chosen, none either.
  expect(camReferences('', choices.get('op:1'))).toEqual([]);
  expect(camReferences('/work/part.step', null)).toEqual([]);
});

it('shows a choice in Quick Edit as one chip named for its row, a face glyph in the operation\'s colour, its X letting go', () => {
  const choices = camChoices(job());
  const onRemove = vi.fn();
  const pocket = choices.get('op:1')!;
  const [chip] = camChips(pocket, camReferences('/work/part.step', pocket), { colours: { 1: '#123456' }, onRemove });
  expect(chip).toMatchObject({ key: 'cam:op:1', label: 'Pocket', glyph: 'face', glyphColor: '#123456', copy: '/work/part.step#o1.f12,o1.f13' });
  chip.onRemove();
  expect(onRemove).toHaveBeenCalled();
  // The card: the row's sentence, the part and how many faces.
  const { container } = render(<>{chip.card}</>);
  expect(container.querySelector('[data-cam-chip-summary]')!.textContent).toBe('Pocket #o1.f12 with T3 4 mm ball, 60 s');
  expect([...container.querySelectorAll('[data-info-row]')].map((row) => row.textContent)).toEqual(['Partpart.step', 'Faces2']);
  // A choice of the whole part reads as the part; a setup's glyph takes no one colour.
  const face = choices.get('op:0')!;
  expect(camChips(face, camReferences('/work/part.step', face), { colours: { 0: '#abcdef' } })[0]).toMatchObject({ label: 'Face', glyph: 'solid', glyphColor: '#abcdef' });
  const setup = choices.get('setup:top')!;
  expect(camChips(setup, camReferences('/work/part.step', setup), { colours: { 0: '#abcdef', 1: '#123456' } })[0])
    .not.toHaveProperty('glyphColor');
  // No chip without a reference, or with nothing chosen.
  expect(camChips(pocket, [])).toEqual([]);
  expect(camChips(null, camReferences('/work/part.step', pocket))).toEqual([]);
});

it('paints a choice as its operations isolated, and a moment as the tool on the path', () => {
  const root = camScene();
  const parsed = readCamJob(root)!;
  const paths = { update: vi.fn(() => true), toolAt: vi.fn(() => ({ point: [1, 2, 3], op: 1, setup: 'top' })) };
  const tool = { show: vi.fn(), hide: vi.fn() };
  const shown = { toolpaths: true, rapids: false, stock: false, part: true };
  paintCam({ controller: { paths, tool }, meshes: camSceneMeshes(root), job: parsed, shown, isolate: new Set([1]), moment: null });
  expect(paths.update).toHaveBeenLastCalledWith({ toolpaths: true, rapids: false, isolate: new Set([1]), hidden: null, time: null, setup: null });
  expect(tool.hide).toHaveBeenCalled();
  const painted = paintCam({ controller: { paths, tool }, meshes: camSceneMeshes(root), job: parsed, shown, isolate: null, moment: { t: 45, setup: null } });
  expect(painted).toEqual({ changed: true, place: { point: [1, 2, 3], op: 1, setup: 'top' } });
  // The tool as it reaches the moment: an operation's last moment leaves it on that operation.
  expect(paths.toolAt.mock.lastCall![0]).toBeCloseTo(45, 5);
  expect(paths.toolAt.mock.lastCall![0]).toBeLessThan(45);
  expect(tool.show).toHaveBeenLastCalledWith({ point: [1, 2, 3], op: 1, setup: 'top' });
});

it('puts away the operations hidden by their eyes, the tool when Display says, and shows the fixtures of the setup in view', () => {
  const root = camScene();
  const parsed = readCamJob(root)!;
  const paths = { update: vi.fn(() => true), toolAt: vi.fn(() => ({ point: [1, 2, 3], op: 1, setup: 'top' })) };
  const tool = { show: vi.fn(), hide: vi.fn() };
  const fixtures = { update: vi.fn(() => false) };
  const shown = { ...CAM_SHOWN, tool: false, fixtures: true, hidden: [0, 7] };
  const painted = paintCam({ controller: { paths, tool, fixtures }, meshes: camSceneMeshes(root), job: parsed, shown, isolate: null, moment: { t: 45, setup: null } });
  // An index the job does not have is dropped.
  expect(paths.update.mock.lastCall![0].hidden).toEqual(new Set([0]));
  // The tool gate off: the tool stays put away while the clip plays, and the readout still knows where it is.
  expect(tool.show).not.toHaveBeenCalled();
  expect(tool.hide).toHaveBeenCalled();
  expect(painted.place).toMatchObject({ op: 1 });
  // While playing, the fixtures of the setup under way; with a row chosen, its setups'; else the first setup's with any.
  expect(fixtures.update).toHaveBeenLastCalledWith({ shown: true, setups: new Set(['top']) });
  paintCam({ controller: { paths, tool, fixtures }, meshes: camSceneMeshes(root), job: parsed, shown: { ...shown, fixtures: false }, isolate: new Set([0]), moment: null });
  expect(fixtures.update).toHaveBeenLastCalledWith({ shown: false, setups: new Set(['top']) });
  paintCam({ controller: { paths, tool, fixtures }, meshes: camSceneMeshes(root), job: parsed, shown, isolate: null, moment: null });
  expect(fixtures.update).toHaveBeenLastCalledWith({ shown: true, setups: null });
  expect(camHidden(parsed, CAM_SHOWN)).toBeNull();
  expect(toggleCamHidden({ hidden: [1] }, 0)).toEqual([0, 1]);
  expect(toggleCamHidden({ hidden: [0, 1] }, 0)).toEqual([1]);
  expect(toggleCamHidden({}, 1)).toEqual([1]);
});

it('gives each operation a Hide/Reveal eye, kept on its row while the operation is hidden', () => {
  const onToggleHidden = vi.fn();
  const onChoose = vi.fn();
  const { container } = render(<CamJobPanel job={job()} colours={camOpColours(job())} chosen="" onChoose={onChoose}
    hidden={new Set([1])} onToggleHidden={onToggleHidden} />);
  fireEvent.click(screen.getByRole('button', { name: 'Hide Face' }));
  expect(onToggleHidden).toHaveBeenLastCalledWith(0);
  // The eye is not the row: it neither chooses nor isolates.
  expect(onChoose).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Reveal Pocket' })).toBeTruthy();
  expect(container.querySelector('[data-cam-row="op:1"]')!.hasAttribute('data-cam-hidden')).toBe(true);
  expect(container.querySelector('[data-cam-row="op:0"]')!.hasAttribute('data-cam-hidden')).toBe(false);
  // Setups and tools have no eye.
  expect(screen.queryByRole('button', { name: 'Hide Top' })).toBeNull();
  expect(screen.queryByRole('button', { name: /Hide T1/ })).toBeNull();
});

it('lists each tool with its speed and feed, a range where its operations differ, and carries it into Quick Edit', () => {
  const extras = camExtras() as any;
  extras.tools = [{ id: 'T3', number: 3, type: 'ball_endmill', diameter_mm: 4, plain: '4 mm ball end mill' },
    { id: 'T1', number: 1, type: 'flat_endmill', diameter_mm: 6 }, { id: 'T9', number: 9, type: 'drill', diameter_mm: 5 }];
  extras.setups[0].operations.push({ index: 2, op: 'contour', plain: 'Profile', tool: 'T1', tool_plain: '6 mm flat', rpm: 10000, feed_mm_min: 1440,
    time_s: 10, t0: 90, t1: 100, summary: 'Profile', faces: ['#o1.f2'], limits: [] });
  const parsed = readCamJob(camScene({ extras }))!;
  render(<CamJobPanel job={parsed} colours={{}} chosen="tool:T1" onChoose={() => {}} />);
  const tools = screen.getByRole('region', { name: 'Tools' });
  expect([...tools.querySelectorAll('[data-cam-row]')].map((row) => row.textContent)).toEqual([
    'T1 6 mm flat10,000–12,000 rpm · 1,440 mm/min', 'T3 4 mm ball end mill15,000 rpm · 900 mm/min', 'T9 5 mm drill']);
  expect(screen.getByRole('button', { name: 'Select T1 6 mm flat' }).getAttribute('aria-pressed')).toBe('true');
  const choices = camChoices(parsed);
  expect(choices.get('tool:T1')).toEqual({ id: 'tool:T1', label: 'T1 6 mm flat', ops: [0, 2], faces: ['#o1.f2'],
    summary: 'T1 6 mm flat at 10,000–12,000 rpm, 1,440 mm/min: Face, Profile' });
  expect(choices.get('tool:T9')).toMatchObject({ ops: [], summary: 'T9 5 mm drill, unused' });
  expect(camReferences('/work/part.step', choices.get('tool:T1'))[0]).toMatchObject({ target: { kind: 'cad-selector', selectors: ['o1.f2'] } });
});

it('says at the view\'s foot where a playing clip is, and is away while none plays', () => {
  const readoutRef: { current: any } = { current: null };
  const { container } = render(<CamReadout readoutRef={readoutRef} />);
  const box = container.querySelector('[data-cam-readout]') as HTMLElement;
  expect(box.style.display).toBe('none');
  expect(box.getAttribute('aria-hidden')).toBe('true');
  readoutRef.current({ operation: 'Pocket', time: '0:45 / 1:30', speed: '3× speed' });
  expect(box.style.display).toBe('');
  expect(box.textContent).toBe('Pocket0:45 / 1:303× speed');
  readoutRef.current(null);
  expect(box.style.display).toBe('none');
});

it('gates what the view shows of a result in Job\'s Show rows: toolpaths, rapids, stock and part, each only where the file has it', () => {
  const root = camScene();
  const gates = camGates({ job: job(), meshes: camSceneMeshes(root), paths: camPathKinds(root), shown: CAM_SHOWN });
  expect(gates.map((gate: any) => [gate.id, gate.title, gate.on])).toEqual([
    ['toolpaths', 'Toolpaths', true], ['rapids', 'Rapids', true], ['tool', 'Tool', true], ['stock', 'Stock', false], ['part', 'Part', true]]);
  expect(gates[0].hint).toBe('2 operations, each in its own colour');
  root.remove(...camSceneMeshes(root).stock.map((entry: any) => entry.object));
  expect(camGates({ job: job(), meshes: camSceneMeshes(root), paths: { feed: true, rapid: false }, shown: CAM_SHOWN })
    .map((gate: any) => gate.title)).toEqual(['Toolpaths', 'Tool', 'Part']);
  // Fixtures only where the file has a fixture box.
  const extras = camExtras() as any;
  extras.setups[0].fixtures = [{ name: 'vise jaw', min_mm: [-5, -10, -20], max_mm: [5, 10, 0] }];
  const fixtured = camGates({ job: readCamJob(camScene({ extras }))!, meshes: camSceneMeshes(root), paths: { feed: true, rapid: false },
    shown: { ...CAM_SHOWN, fixtures: false } });
  expect(fixtured.map((gate: any) => [gate.title, gate.on])).toEqual([['Toolpaths', true], ['Tool', true], ['Fixtures', false], ['Part', true]]);

  // In Job, under Show: each a row with its eye, which turns it on or off.
  const onToggleGate = vi.fn();
  const { container } = render(<CamJobPanel job={job()} colours={{}} chosen="" onChoose={() => {}} gates={fixtured} onToggleGate={onToggleGate} />);
  const show = screen.getByRole('region', { name: 'Show' });
  expect([...show.querySelectorAll('[data-cam-gate]')].map((row) => row.textContent)).toEqual(['Toolpaths', 'Tool', 'Fixtures', 'Part']);
  expect(container.querySelector('[data-cam-gate="fixtures"]')!.hasAttribute('data-cam-hidden')).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Reveal fixtures' }));
  expect(onToggleGate).toHaveBeenLastCalledWith('fixtures', true);
  fireEvent.click(screen.getByRole('button', { name: 'Hide toolpaths' }));
  expect(onToggleGate).toHaveBeenLastCalledWith('toolpaths', false);
});

it('hangs its drawing beside the scene, in the model group where the scene\'s root is: Preview\'s copy of the scene never has it', () => {
  const root = camScene();
  root.position.set(1, 2, 3);
  const scene = createGlbScene(THREE, { scene: root, clips: [], cadRootMatrix: new THREE.Matrix4().makeScale(1000, 1000, 1000).toArray(),
    animatedBounds: null, restBounds: null });
  const modelGroup = new THREE.Group();
  modelGroup.add(scene.object3D);
  const runtime = { THREE, modelGroup, LineSegments2, LineSegmentsGeometry, LineMaterial,
    registerScreenSpaceLineMaterial: vi.fn(), unregisterScreenSpaceLineMaterial: vi.fn() };
  const controllerRef: { current: any } = { current: null };
  const drawnUnder = (object: THREE.Object3D) => { const found: THREE.Object3D[] = []; object.traverse((child) => { if (child.userData.camDrawn) found.push(child); }); return found; };
  const { unmount } = render(<CamPaths runtimeRef={{ current: runtime }} viewerReadyTick={1} root={root} cadRoot={scene.object3D}
    job={readCamJob(root)} scheme="light" controllerRef={controllerRef} onChange={() => {}} />);
  expect(controllerRef.current?.paths.count).toBeGreaterThan(0);
  const holder = modelGroup.children.find((child) => child.name === 'cam-drawing')!;
  expect(holder).toBeTruthy();
  // Nothing of it in the scene: Select's picks, Clip's caps and Preview's sibling read the scene alone.
  expect(drawnUnder(scene.object3D)).toEqual([]);
  expect(drawnUnder(holder).some((child: any) => child.isLineSegments2)).toBe(true);
  // Drawn where the root is: the paths in the root's frame land where the file's own lines are.
  modelGroup.updateMatrixWorld(true);
  holder.matrixWorld.elements.forEach((value, index) => expect(value).toBeCloseTo(root.matrixWorld.elements[index], 6));
  const sibling = scene.createSibling();
  expect(drawnUnder(sibling.object3D)).toEqual([]);
  sibling.dispose();
  unmount();
  expect(controllerRef.current).toBeNull();
  expect(modelGroup.children.includes(holder)).toBe(false);
  scene.dispose();
});
