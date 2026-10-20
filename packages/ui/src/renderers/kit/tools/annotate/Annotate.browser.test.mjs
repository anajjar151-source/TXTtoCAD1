import assert from 'node:assert/strict';
import { test } from 'node:test';
import { runAnnotateScenario } from '../../../harness/annotateScenario.mjs';
import { serveStepHarness } from '../../../harness/stepScenario.mjs';

// Annotate under the frame that ships it: the STEP renderer, over the committed
// two-part fixture. It is a kit tool, so the scenario itself
// (`harness/annotateScenario.mjs`) knows nothing about STEP.

test('Annotate puts ink into the model that orbits with it, undoes, redoes, recolours and clears, stays when Annotate is left — where Select picks, haloes and deletes it — and goes when the model updates', async (t) => {
  const harness = await serveStepHarness(t);
  await runAnnotateScenario(await harness.open());
});


test('on a narrow view Annotate\'s controls are three rows from the left, and on a phone the menu of a chevron after its tile', async (t) => {
  const harness = await serveStepHarness(t);
  const { page, pane, errors } = await harness.open();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await pane.getByRole('button', { name: 'Annotate', exact: true }).click();
  const controls = pane.getByRole('toolbar', { name: 'Annotation controls', exact: true });
  for (const width of [960, 768]) {
    await page.setViewportSize({ width, height: 600 });
    await page.waitForFunction(() => {
      const buttons = [...document.querySelectorAll('[aria-label="Annotation controls"] button')].map(button => button.getBoundingClientRect().top);
      return buttons.length === 14 && buttons[10] > buttons[6] && buttons[6] > buttons[0];
    });
    const layout = await controls.evaluate(row => {
      const buttons = [...row.querySelectorAll('button')].map(button => button.getBoundingClientRect());
      return { count: buttons.length, top: buttons.map(box => box.top), x: buttons.map(box => box.left) };
    });
    assert.equal(layout.count, 14);
    const rows = [layout.top.slice(0, 6), layout.top.slice(6, 10), layout.top.slice(10)];
    assert.ok(rows.every(row => row.every(y => y === row[0])), `${width}px: six tools, four styles, then the eraser and three actions, a row each`);
    assert.ok(rows[0][0] < rows[1][0] && rows[1][0] < rows[2][0], `${width}px: the rows one over the other`);
    assert.deepEqual([layout.x[6], layout.x[10]], [layout.x[0], layout.x[0]], `${width}px: every row starts at the same left edge`);
  }
  // A phone: no row under the strip; the chevron after Annotate's tile holds its controls.
  await page.setViewportSize({ width: 390, height: 700 });
  await controls.waitFor({ state: 'detached' });
  await pane.getByRole('button', { name: 'Annotation settings', exact: true }).click();
  const menu = page.getByRole('menu', { name: 'Annotation settings', exact: true });
  await menu.getByRole('menuitemradio', { name: 'Rectangle', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[data-cad-toolbar] [aria-label="Annotate"] svg')?.getAttribute('class')?.includes('lucide-square'));
  assert.deepEqual(errors, []);
});
