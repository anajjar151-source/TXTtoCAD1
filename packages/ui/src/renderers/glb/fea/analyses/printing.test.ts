import { describe, expect, it } from 'vitest';
import { ANALYSES } from './index.js';
import printing, { PLAY, buildControls } from './printing.js';

// A print as cadgen writes one: two bands, then off the plate, the last frame the default; it deforms.
const result = {
  fields: [{ attribute: '_von_mises', name: 'residual stress (von Mises)' }, { attribute: '_displacement', name: 'distortion' },
    { attribute: '_printed', name: 'printed so far' }],
  deformationScale: 10,
  series: { kind: 'time', unit: '', default: 2, frames: [
    { value: 1, label: 'Band 1/2 · 3 mm', attributes: {} }, { value: 2, label: 'Band 2/2 · 6 mm', attributes: {} },
    { value: 3, label: 'Off the plate', attributes: {} }] },
  mesh: { geometry: { getAttribute: (name: string) => (name === '_displacement' ? { itemSize: 3 } : null) } },
};

describe('printing', () => {
  it('is registered, tier 3, judged by its findings alone, and plays its build', () => {
    expect(ANALYSES.printing).toBe(printing);
    expect(printing).toMatchObject({ name: 'printing', tier: 3, word: '3D printing', noun: 'this print', checks: [] });
    expect(printing.routine(result)).toBe(PLAY);
  });

  it('scrubs its bands under the word Build, opening off the plate, then the field and the deformation', () => {
    const [build, field, deformation] = buildControls(result);
    expect(build).toMatchObject({ id: 'frame', label: 'Build', min: 1, max: 3, defaultValue: 3,
      frameLabels: ['Band 1/2 · 3 mm', 'Band 2/2 · 6 mm', 'Off the plate'] });
    expect(field.id).toBe('field');
    expect(deformation.id).toBe('deformation');
  });
});
