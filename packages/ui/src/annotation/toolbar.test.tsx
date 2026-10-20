import React from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { useAnnotationSession } from './session.js';
import { ANNOTATION_COLORS, AnnotationToolbar, annotationColors } from './toolbar.jsx';
import { SUB_TOOLBAR_WIDTH_CLASS } from '../renderers/kit/tools/SubToolbar.jsx';

afterEach(cleanup);

let session: ReturnType<typeof useAnnotationSession>;
const history = { canUndo: false, canRedo: false, undo() {}, redo() {} };
function Panel({ colorScheme = 'light' }: { colorScheme?: 'light' | 'dark' }) {
  session = useAnnotationSession(true);
  return <AnnotationToolbar annotation={session} history={history} colorScheme={colorScheme} />;
}

it("Annotate's controls, three rows parted by rules at the sub-toolbars' one width: what draws, what is drawn next as dropdowns, placement among them, then the eraser, Clear, Undo and Redo", async () => {
  render(<Panel />);
  const row = screen.getByRole('toolbar', { name: 'Annotation controls' });
  const label = (element: Element) => element.getAttribute('role') === 'separator' ? '|' : element.getAttribute('aria-label');
  // Each row its own group, one over the other, a thin rule between them, whatever the view's width.
  expect([...row.children].map(label)).toEqual(['Annotation tools', '|', 'Annotation style', '|', 'Erase and history']);
  expect(row.className.split(/\s+/)).toEqual(expect.arrayContaining(['flex-col', ...SUB_TOOLBAR_WIDTH_CLASS.split(/\s+/)]));
  expect(within(screen.getByRole('group', { name: 'Annotation tools' })).getAllByRole('button').map(button => button.getAttribute('aria-label')))
    .toEqual(['Pen', 'Line', 'Arrow', 'Rectangle', 'Ellipse', 'Text']);
  expect(within(screen.getByRole('group', { name: 'Erase and history' })).getAllByRole('button').map(button => button.getAttribute('aria-label')))
    .toEqual(['Eraser', 'Clear annotations', 'Undo', 'Redo']);
  const settings = screen.getByRole('group', { name: 'Annotation style' });
  expect(within(settings).getAllByRole('button').map(button => button.getAttribute('aria-label')))
    .toEqual(['Color', 'Stroke width', 'Line style', 'Placement']);
  expect(session.placement).toBe('surface');
  fireEvent.pointerDown(within(settings).getByRole('button', { name: 'Placement' }), { button: 0, ctrlKey: false });
  const menu = await screen.findByRole('menu', { name: 'Placement' });
  expect(within(menu).getAllByRole('menuitemradio').map(item => [item.getAttribute('aria-label'), item.getAttribute('aria-checked')]))
    .toEqual([['On surface', 'true'], ['On plane', 'false']]);
  fireEvent.click(within(menu).getByRole('menuitemradio', { name: 'On plane' }));
  expect(session.placement).toBe('plane');
});

it('Stroke width and Line style are menus as the strip\'s are: headed with their name, a row per choice, glyph and name, the current one checked', async () => {
  render(<Panel />);
  const choices = async (name: string) => {
    fireEvent.pointerDown(screen.getByRole('button', { name }), { button: 0, ctrlKey: false });
    const menu = await screen.findByRole('menu', { name });
    return { menu, heading: menu.querySelector('[data-slot=dropdown-menu-label]')?.textContent, items: within(menu).getAllByRole('menuitemradio').map(item =>
      [item.getAttribute('aria-label'), item.getAttribute('data-style-option'), item.getAttribute('aria-checked'), item.textContent]) };
  };
  const width = await choices('Stroke width');
  expect(width.heading).toBe('Stroke width');
  expect(width.items).toEqual([['Thin', '1', 'false', 'Thin'], ['Medium', '2', 'true', 'Medium'], ['Bold', '4', 'false', 'Bold']]);
  fireEvent.click(within(width.menu).getByRole('menuitemradio', { name: 'Bold' }));
  expect(session.strokeWidth).toBe(4);
  const dash = await choices('Line style');
  expect(dash.heading).toBe('Line style');
  expect(dash.items).toEqual([['Solid', 'solid', 'true', 'Solid'], ['Dashed', 'dashed', 'false', 'Dashed'], ['Dotted', 'dotted', 'false', 'Dotted']]);
  fireEvent.click(within(dash.menu).getByRole('menuitemradio', { name: 'Dashed' }));
  expect(session.strokeStyle).toBe('dashed');
});

it('the colours are the neons and the one neutral that reads against the viewer: white in dark mode, black in light', () => {
  const labels = (scheme: 'light' | 'dark') => annotationColors(scheme).map(option => option.label);
  const neons = ANNOTATION_COLORS.slice(0, 7).map(option => option.label);
  expect([labels('dark'), labels('light')]).toEqual([[...neons, 'White'], [...neons, 'Black']]);
});

it('Color is a grid of the scheme\'s swatches, the current one marked, then a custom colour from the system picker', async () => {
  render(<Panel colorScheme="dark" />);
  const open = async () => {
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Color' }), { button: 0, ctrlKey: false });
    return screen.findByRole('menu', { name: 'Color' });
  };
  let menu = await open();
  expect(menu.querySelector('[data-slot=dropdown-menu-label]')?.textContent).toBe('Color');
  const neons = ANNOTATION_COLORS.slice(0, 7).map(option => option.label);
  expect(within(menu).getAllByRole('menuitem').map(item => item.getAttribute('aria-label'))).toEqual([...neons, 'White', 'Custom color']);
  expect([...menu.querySelectorAll('[data-checked]')].map(item => item.getAttribute('aria-label'))).toEqual(['Neon red']);
  fireEvent.click(within(menu).getByRole('menuitem', { name: 'Neon green' }));
  expect(session.color).toBe('#39ff14');
  menu = await open();
  expect([...menu.querySelectorAll('[data-checked]')].map(item => item.getAttribute('aria-label'))).toEqual(['Neon green']);
  // The picker's colour is taken as it closes.
  const picker = document.querySelector<HTMLInputElement>('input[type=color][data-color-picker]')!;
  picker.value = '#123456';
  fireEvent.change(picker);
  expect(session.color).toBe('#123456');
});
