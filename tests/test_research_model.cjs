const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const research = require('../ui/research-model.js');

const finding = (paperKey, fields = {}, extra = {}) => ({
  paperKey, fields, year: 2024, title: paperKey, sample: null,
  search: 'depression symptom severity', signature: JSON.stringify(fields), ...extra,
});

test('evidence filters must match the same finding, not different findings from one paper', () => {
  const rows = [
    finding('a', { design: ['RCT'], followup: ['Acute'], outcome: ['Depression'] }),
    finding('a', { design: ['Observational'], followup: ['Long'], outcome: ['Safety'] }),
    finding('b', { design: ['RCT'], followup: ['Long'], outcome: ['Depression'] }),
  ];
  assert.deepEqual(research.filter(rows, { design: 'RCT', followup: 'Long' }).map(row => row.paperKey), ['b']);
});

test('missing metadata is separate from explicit no-comparator or absence categories', () => {
  const missing = finding('a');
  const absent = finding('b', { comparator: ['No comparator'] });
  assert.deepEqual(research.filter([missing, absent], { comparator: research.MISSING }), [missing]);
  assert.deepEqual(research.filter([missing, absent], { comparator: 'No comparator' }), [absent]);
});

test('sample thresholds neither sum findings nor admit unknown sample sizes', () => {
  const rows = [finding('a', {}, { sample: 20 }), finding('a', {}, { sample: 20 }), finding('b'), finding('c', {}, { sample: 100 })];
  assert.deepEqual(research.filter(rows, { minSample: '30' }).map(row => row.paperKey), ['c']);
});

test('publication profiles count a paper once per category, with overlapping categories retained', () => {
  const rows = [finding('a', { area: ['Clinical', 'Brain'] }), finding('a', { area: ['Brain'] }), finding('b', { area: ['Clinical'] }), finding('c')];
  assert.deepEqual(research.distribution(rows, 'area'), [
    { label: 'Clinical', count: 2 }, { label: 'Brain', count: 1 }, { label: research.MISSING, count: 1 },
  ]);
  assert.equal(research.papers(rows).length, 3);
});

test('coverage captures co-measurement across findings without multiplying publication counts', () => {
  const rows = [
    finding('a', { outcome: ['Depression'], followup: ['Acute'] }),
    finding('a', { outcome: ['Brain'], followup: ['Long'] }),
    finding('a', { outcome: ['Brain'], followup: ['Long'] }),
    finding('b', { outcome: ['Depression'], followup: ['Acute'] }),
  ];
  const matrix = research.coverage(rows, 'outcome', 'followup');
  assert.deepEqual([...matrix.cells.get(JSON.stringify(['Depression', 'Long']))], ['a']);
  assert.equal(matrix.cells.get(JSON.stringify(['Depression', 'Acute'])).size, 2);
  assert.equal(research.matchingCell(rows, 'outcome', 'followup', 'Depression', 'Long').length, 3);
  assert.deepEqual(research.matchingCell(rows, 'outcome', 'followup', 'Brain', 'Missing category'), []);
});

test('snapshot comparisons ignore row order and separate new, changed and removed reports', () => {
  const a = finding('a', {}, { signature: 'original effect estimate' });
  const b = finding('b');
  const before = research.snapshot([a, b]);
  assert.deepEqual(research.changes(before, research.snapshot([b, a])), { added: [], changed: [], removed: [] });
  const after = research.snapshot([{ ...a, signature: 'corrected effect estimate' }, finding('c')]);
  assert.deepEqual(research.changes(before, after), { added: ['c'], changed: ['a'], removed: ['b'] });
});

test('publication identity remains safe for unusual source keys', () => {
  const before = research.snapshot([finding('__proto__'), finding('constructor')]);
  assert.equal(Object.keys(before).length, 2);
  assert.deepEqual(research.changes(before, before), { added: [], changed: [], removed: [] });
});

function workspaceContext() {
  const context = vm.createContext({
    document: { addEventListener() {}, getElementById() { return null; } },
    ANALYSIS_SECTIONS: new Set(['all', 'compound', 'author', 'journal']),
    ENTITY_CATEGORY_OPTIONS: [{ key: 'condition_indication', label: 'Conditions' }],
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../ui/research-analysis.js'), 'utf8'), context);
  return context;
}

test('shared and locally saved question state is bounded and validated before use', () => {
  const context = workspaceContext();
  context.input = {
    task: 'invalid', lens: 'missing', area: 'unrecognized', access: 'anything',
    filters: { design: 'RCT', arbitrary: 'drop', minSample: '-12', query: 'x'.repeat(5000) },
    compare: Array.from({ length: 8 }, (_, index) => ({ kind: 'compound', key: String(index), label: 'Compound' })),
    axes: ['bogus', 'outcome'],
  };
  const state = JSON.parse(vm.runInContext('JSON.stringify(researchValidateState(input))', context));
  assert.equal(state.task, 'landscape');
  assert.equal(state.lens, 'all');
  assert.equal(state.area, '');
  assert.equal(state.access, 'all');
  assert.equal(state.filters.design, 'RCT');
  assert.equal(state.filters.query.length, 1000);
  assert.equal(state.filters.minSample, undefined);
  assert.equal(state.filters.arbitrary, undefined);
  assert.equal(state.compare.length, 4);
  assert.deepEqual(state.axes, ['population', 'design']);
});

test('empty evidence is a legitimate empty result, never a fallback to the full corpus', () => {
  assert.deepEqual(research.filter([], { design: 'RCT' }), []);
  assert.deepEqual(research.papers([]), []);
  assert.equal(research.coverage([], 'design', 'outcome').cells.size, 0);
  assert.deepEqual(research.snapshot([]), {});
});

test('saved coverage selections and pinned date scopes survive state restoration', () => {
  const context = workspaceContext();
  Object.assign(context, { yearFilterState: {}, currentYearFilterKey: () => 'analysis:research' });
  context.input = {
    task: 'evidence', lens: 'compound', focus: { key: 'psilocybin', label: 'Psilocybin' },
    min: '2010', max: '2020', axes: ['outcome', 'followup'], cell: ['Depression', 'Long'],
    compare: [{ kind: 'set', key: 'all', label: 'Earlier trials', filters: { design: 'RCT' },
      scope: { min: '2000', max: '2010', area: 'condition_indication', evidence: 'primary' },
      coverage: { axes: ['outcome', 'followup'], cell: ['Depression', 'Long'] } }],
  };
  vm.runInContext('researchApplyState(input)', context);
  assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(researchCoverageCell)', context)), ['Depression', 'Long']);
  assert.equal(context.yearFilterState['analysis:research'].min, '2010');
  const pinned = JSON.parse(vm.runInContext('JSON.stringify(researchCompare[0])', context));
  assert.equal(pinned.scope.min, '2000');
  assert.equal(pinned.filters.design, 'RCT');
  assert.deepEqual(pinned.coverage.cell, ['Depression', 'Long']);
  vm.runInContext('researchApplyState({...input, task: "compare"})', context);
  assert.equal(context.explorerLens, 'all');
  assert.equal(context.explorerFocus, null);
});

test('pinned comparisons apply their own dates, type and report coverage before counting', () => {
  const context = workspaceContext();
  Object.assign(context, {
    PKGResearch: research, EXPLORER_ENTITY_LENSES: new Set(['compound', 'author', 'journal']),
    isOpenAccessClaim: claim => claim.fullText,
  });
  context.rows = [
    finding('a', { design: ['RCT'], outcome: ['Depression'], followup: ['Acute'], paperType: ['Primary studies'] }, { year: 2015, claim: { fullText: true } }),
    finding('a', { design: ['RCT'], outcome: ['Brain'], followup: ['Long'], paperType: ['Primary studies'] }, { year: 2015, claim: { fullText: true } }),
    finding('b', { design: ['RCT'], outcome: ['Depression'], followup: ['Long'], paperType: ['Primary studies'] }, { year: 2024, claim: { fullText: true } }),
    finding('c', { design: ['RCT'], outcome: ['Depression'], followup: ['Long'], paperType: ['Reviews'] }, { year: 2015, claim: { fullText: true } }),
  ];
  context.candidate = { kind: 'set', filters: { design: 'RCT' }, scope: { min: '2010', max: '2020', evidence: 'primary', access: 'open' }, coverage: { axes: ['outcome', 'followup'], cell: ['Depression', 'Long'] } };
  assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(researchCandidateRows(rows, candidate).map(row => row.paperKey))', context)), ['a', 'a']);
});
