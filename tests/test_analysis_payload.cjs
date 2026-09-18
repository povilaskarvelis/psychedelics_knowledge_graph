const { test } = require('node:test');
const assert = require('node:assert/strict');
const codec = require('../ui/analysis-payload.js');
const fixture = () => ({ schema_version: 'psychedelics_kg_analysis_bootstrap_v1', row_count: 3,
  fields: ['paper', 'category'], values: [null, 'a', 'b', 'RCT'], columns: [[[1, 2], [2, 1]], [[3, 1], [0, 2]]] });

test('run-length columns decode losslessly across batch boundaries with stable detail identifiers', () => {
  const batches = [...codec.batches(fixture(), 2)];
  assert.deepEqual(batches.map(batch => batch.length), [2, 1]);
  assert.deepEqual(batches.flat().map(row => ({ ...row })), [
    { paper: 'a', category: 'RCT', __analysis_row: 0 },
    { paper: 'a', __analysis_row: 1 }, { paper: 'b', __analysis_row: 2 },
  ]);
});
test('truncated, corrupt, or ambiguous data fails before any partial charts can render', () => {
  for (const mutate of [p => p.columns[0].pop(), p => p.columns[0][0][1] = 0,
    p => p.columns[0][0][0] = 100, p => p.fields[1] = 'paper', p => p.row_count = 1.5,
    p => p.fields[0] = '__analysis_row']) {
    const payload = fixture(); mutate(payload);
    assert.throws(() => [...codec.batches(payload)]);
  }
});
