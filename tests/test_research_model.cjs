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

test('coverage links validate distinct axes and bound category searches and selections', () => {
  const context = workspaceContext();
  context.input = { axes: ['population', 'population'], queries: ['x'.repeat(500), ''], cell: ['a', 'b'], filters: { design: 'RCT' }, task: 'compare' };
  const state = JSON.parse(vm.runInContext('JSON.stringify(researchValidateState(input))', context));
  assert.deepEqual(state.axes, ['population', 'design']);
  assert.equal(state.queries[0].length, 200);
  assert.deepEqual(state.cell, ['a', 'b']);
  assert.equal(state.filters, undefined);
  assert.equal(state.task, undefined);
  context.input = { axes: ['__proto__', 'design'], cell: [5, null] };
  assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(researchValidateState(input))', context)), { axes: ['population', 'design'], queries: ['', ''], cell: null });
});

test('copyable view URLs round-trip scope, axes, category searches and cell selection', () => {
  const context = workspaceContext();
  Object.assign(context, { explorerMode: 'analysis', yearMinFilter: { value: '1932' }, yearMaxFilter: { value: '2026' }, yearFilterState: {}, currentYearFilterKey: () => 'analysis:research' });
  context.url = new URL('https://example.test/?mode=analysis&section=compound&focus=psilocybin&scope-area=condition_indication&papers=reviews&task=evidence');
  context.state = { axes: ['outcome', 'followup'], queries: ['depression', 'long'], cell: ['Depression', 'Long'] };
  vm.runInContext('researchApplyState(state); researchUrlState(url); researchApplyState({}); researchReadUrl(url.searchParams)', context);
  assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(researchCaptureState())', context)), context.state);
  assert.equal(context.url.searchParams.get('focus'), 'psilocybin');
  assert.equal(context.url.searchParams.get('papers'), 'reviews');
  assert.equal(context.url.searchParams.has('task'), false);
  assert.equal(context.yearFilterState['analysis:research'].min, '1932');
  context.url.searchParams.delete('coverage');
  context.url.searchParams.set('research', JSON.stringify({ filters: { design: 'RCT' }, compare: [{ kind: 'compound', key: 'LSD' }] }));
  vm.runInContext('researchReadUrl(url.searchParams); researchUrlState(url)', context);
  assert.equal(context.url.searchParams.has('research'), false);
  assert.equal(context.url.searchParams.has('coverage'), false);
  context.explorerMode = 'overview';
  vm.runInContext('researchUrlState(url)', context);
  assert.equal(context.url.searchParams.has('from'), false);
});

test('category searches expose smaller groups without filtering or recounting the overview', () => {
  const context = workspaceContext();
  context.PKGResearch = research;
  context.rows = Array.from({ length: 30 }, (_, i) => finding(String(i), { population: [`Population ${String(i).padStart(2, '0')}`], design: ['RCT'] }));
  const before = vm.runInContext('researchCoverageView(rows)', context);
  assert.equal(before.rows.length, 18);
  vm.runInContext('researchCategoryQueries = ["population 29", "rct"]', context);
  const after = vm.runInContext('researchCoverageView(rows)', context);
  assert.deepEqual(Array.from(after.rows), ['Population 29']);
  assert.equal(after.matrix, before.matrix);
  assert.equal(after.matrix.cells.size, 30);
  vm.runInContext('researchCategoryQueries = ["", ""]; researchCoverageCell = ["Population 29", "RCT"]', context);
  assert.ok(vm.runInContext('researchCoverageView(rows).rows.includes("Population 29")', context));
  vm.runInContext('researchCategoryQueries = ["does not exist", ""]', context);
  assert.equal(vm.runInContext('researchCoverageView(rows).rows.length', context), 0);
});

test('coverage cell drill-down opens only the matching reports through the existing findings view', () => {
  const context = workspaceContext();
  let opened = null;
  Object.assign(context, { PKGResearch: research, renderExplorerSelectionDetail: (title, claims) => { opened = { title, claims }; } });
  context.document.querySelector = () => null;
  context.rows = [
    finding('a', { population: ['Human'], design: ['RCT'] }, { claim: { id: 'a1' } }),
    finding('a', { population: ['Human'], design: ['RCT'] }, { claim: { id: 'a2' } }),
    finding('b', { population: ['Mouse'], design: ['RCT'] }, { claim: { id: 'b' } }),
  ];
  vm.runInContext('researchCoverageRows = rows; researchCoverageCell = ["Human", "RCT"]; researchOpenCoverageCell()', context);
  assert.deepEqual(Array.from(opened.claims, claim => claim.id), ['a1', 'a2']);
  assert.equal(opened.title, 'Human · RCT');
  vm.runInContext('researchScopeChanged()', context);
  assert.equal(vm.runInContext('researchCoverageCell', context), null);
});

test('coverage respects paper type, year, access, area and entity scope on the actual findings', () => {
  const context = workspaceContext();
  const claims = [
    { id: 'primary', type: 'primary', study_year: '2020', area: 'clinical', focus: true, full: true },
    { id: 'meta', type: 'meta_analyses', study_year: '2020', area: 'clinical', focus: true, full: true },
    { id: 'review', type: 'reviews', study_year: '2020', area: 'clinical', focus: true, full: true },
    { id: 'other finding', type: 'reviews', study_year: '2020', area: 'brain', focus: true, full: true },
    { id: 'old', type: 'reviews', study_year: '1950', area: 'clinical', focus: true, full: true },
    { id: 'abstract', type: 'reviews', study_year: '2020', area: 'clinical', focus: true, full: false },
    { id: 'other entity', type: 'reviews', study_year: '2020', area: 'clinical', focus: false, full: true },
  ];
  Object.assign(context, {
    claimStores: { normalized: { bySource: { all: claims } } }, yearMinFilter: { value: '2000' }, yearMaxFilter: { value: '2026' },
    evidenceView: 'all', accessView: 'open', parseYearValue: Number,
    isHiddenMainGraphItem: () => false, isMainGraphAdmitted: () => true, isOpenAccessClaim: claim => claim.full,
    isSecondaryLiteratureClaim: claim => claim.type !== 'primary', isMetaAnalysisClaim: claim => claim.type === 'meta_analyses', isReviewLiteratureClaim: claim => claim.type === 'reviews',
    analysisClaimsWithinScope: rows => rows.filter(claim => claim.area === 'clinical'), analysisClaimsWithCurrentEntity: rows => rows,
    analysisClaimsForFocusedEntity: rows => rows.filter(claim => claim.focus), researchRow: claim => claim,
  });
  assert.deepEqual(Array.from(vm.runInContext('researchBaseRows()', context), claim => claim.id), ['primary', 'meta', 'review']);
  for (const type of ['primary', 'meta_analyses', 'reviews']) {
    context.evidenceView = type;
    assert.equal(vm.runInContext('researchBaseRows().length', context), 1);
  }
});

test('Analyze date controls retain their range across narrower paper types and empty periods', () => {
  const context = workspaceContext();
  Object.assign(context, { explorerMode: "analysis", yearMinFilter: {}, yearMaxFilter: {}, yearFilterState: {}, currentYearFilterKey: () => "analysis:research" });
  const corpus = [{ study_year: '1932' }, { study_year: '2026' }];
  Object.assign(context, {
    claimStores: { normalized: { bySource: { all: corpus } } },
    isHiddenMainGraphItem: () => false, ANALYSIS_DEFAULT_START_YEAR: 2000,
    selectedClaims: [{ study_year: '2003' }, { study_year: '2024' }],
  });
  const app = fs.readFileSync(path.join(__dirname, '../ui/app.js'), 'utf8');
  for (const name of ['parseYearValue', 'yearBoundsFromClaims', 'defaultYearFilterRange', 'yearFilterBounds', 'syncYearFilterControls', 'activeYearRange', 'clampNumber']) {
    vm.runInContext(app.match(new RegExp(`function ${name}\\([^]*?\\n\\}`))[0], context);
  }
  context.yearFilterState['analysis:research'] = { min: '1932', max: '2026' };
  vm.runInContext('syncYearFilterControls(selectedClaims); activeYearRange(selectedClaims)', context);
  assert.equal(context.yearMinFilter.value, '1932');
  assert.equal(context.yearMaxFilter.value, '2026');
  context.yearFilterState['analysis:research'] = { min: '1932', max: '1950' };
  vm.runInContext('syncYearFilterControls(selectedClaims)', context);
  const range = JSON.parse(vm.runInContext('JSON.stringify(activeYearRange(selectedClaims))', context));
  assert.deepEqual(range, { constrained: true, min: 1932, max: 1950 });
  assert.equal(context.selectedClaims.filter(claim => Number(claim.study_year) >= range.min && Number(claim.study_year) <= range.max).length, 0);
  vm.runInContext('syncYearFilterControls([])', context);
  assert.equal(context.yearMinFilter.value, '1932');
  assert.equal(context.yearMaxFilter.value, '1950');
  assert.equal(context.yearMinFilter.disabled, false);
  // Explore continues using the bounds of its own dataset.
  context.explorerMode = 'overview';
  vm.runInContext('syncYearFilterControls(selectedClaims, true)', context);
  assert.equal(context.yearMinFilter.value, '2003');
  assert.equal(context.yearMaxFilter.value, '2024');
});
