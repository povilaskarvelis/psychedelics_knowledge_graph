const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../ui/app.js'), 'utf8');

function contextFor(names, globals = {}) {
  const context = vm.createContext(globals);
  for (const name of names) {
    const match = source.match(new RegExp(`^(?:async )?function ${name}\\([\\s\\S]*?^}`, 'm'));
    assert.ok(match, name);
    vm.runInContext(match[0], context);
  }
  return context;
}

test('batched detail preparation preserves every admitted row and yields between batches', async () => {
  let yields = 0;
  const context = contextFor([
    'columnarBootstrapClaimsFromPayload', 'detailBootstrapClaimsFromPayload', 'prepareDetailBootstrapClaims',
  ], {
    routeNativeFindingForCurrentUi: raw => ({ ...raw, normalized: true }),
    isHiddenMainGraphItem: item => item.domain === 'hidden',
    routeNativeSourceKey: item => item.source,
    yieldForAnalysisInput: async () => { yields++; },
  });
  const payload = {
    fields: ['id', 'source', 'domain'], values: [null, 'primary', 'reviews', 'visible', 'hidden'],
    rows: Array.from({ length: 2500 }, (_, i) => {
      const id = 5 + i;
      return [id, i % 7 ? 1 : 2, i % 11 ? 3 : 4];
    }),
  };
  payload.values.push(...Array.from({ length: 2500 }, (_, i) => `finding-${i}`));
  const before = JSON.stringify(payload);
  const expected = context.detailBootstrapClaimsFromPayload(payload, 'primary');
  assert.deepEqual(await context.prepareDetailBootstrapClaims(payload, 'primary'), expected);
  assert.equal(yields, 2);
  assert.equal(JSON.stringify(payload), before);
  assert.equal((await context.prepareDetailBootstrapClaims({}, 'primary')).length, 0);
});

test('a failed detail preload is retryable and concurrent callers share its request', async () => {
  let requests = 0;
  const context = contextFor(['loadDetailBootstrapClaims'], {
    loadGraphPayloadConfig: async () => ({}), activeDetailBootstrapPath: () => 'primary.json',
    graphPayloadCandidates: () => ['primary.json'], detailBootstrapPayloadPromises: new Map(),
    fetchJsonFromCandidates: async () => {
      requests++;
      if (requests === 1) throw new Error('offline');
      return { data: ['ready'] };
    },
    prepareDetailBootstrapClaims: async data => data,
  });
  await assert.rejects(context.loadDetailBootstrapClaims('primary'), /offline/);
  const [first, second] = await Promise.all([
    context.loadDetailBootstrapClaims('primary'), context.loadDetailBootstrapClaims('primary'),
  ]);
  assert.deepEqual(first, ['ready']);
  assert.equal(first, second);
  assert.equal(requests, 2);
});

test('normalization can reuse a fresh decoded row without changing its result', () => {
  const context = contextFor([
    'routeNativeFindingForCurrentUi', 'routeNativeEntityLabel', 'routeNativeGraphEntityLabel',
    'routeNativeAccessLevel', 'routeNativePaperType', 'routeNativeSourceType',
    'routeNativeSourceKey', 'normalizeValue', 'cleanDisplayText',
  ], { isSecondarySourceKey: () => false });
  const raw = { domain: 'clinical_outcomes', entity_kind: 'condition_indication', entity_label: 'Depression',
    evidence_location: ' <b>Table 1</b> ', text_depth: 'full_text', paper_type: 'clinical_trial', custom: 'retained' };
  const before = { ...raw };
  const copied = context.routeNativeFindingForCurrentUi(raw);
  assert.deepEqual(raw, before);
  const reused = context.routeNativeFindingForCurrentUi(raw, { reuse: true });
  assert.equal(reused, raw);
  assert.equal(JSON.stringify(reused), JSON.stringify(copied));
});

test('Analyze uses compact data without loading or marking complete evidence sources', async () => {
  let fullLoads = 0;
  const requests = [];
  const context = contextFor(['analysisSourceClaims', 'analysisDataIsReady', 'loadAnalysisData'], {
    URL, window: { location: { href: 'https://example.test/' } },
    analysisDataBySource: null, analysisDataTask: null, analysisClaimsByStudyMemo: null,
    analysisPayloadsBySource: new Map(), normalizedSourceLoaded: { all: false },
    claimStores: { normalized: { bySource: {} } },
    loadGraphPayloadConfig: async () => ({ active_analysis_bootstraps: { primary: 'primary', meta_analyses: 'meta_analyses', reviews: 'reviews' } }),
    graphPayloadCandidates: (_config, path) => [path],
    fetchJsonFromCandidates: async ([source]) => {
      requests.push(source);
      return { url: source, data: { schema_version: 'psychedelics_kg_analysis_bootstrap_v1', source,
        row_count: 1, chunk_size: 512, detail_chunks: ['chunk.json'] } };
    },
    PKGAnalysisPayload: { *batches(data) { yield [{ source: data.source, __analysis_row: 0 }]; } },
    routeNativeFindingForCurrentUi: raw => raw, isHiddenMainGraphItem: () => false,
    routeNativeSourceKey: raw => raw.source, yieldForAnalysisInput: async () => {},
    loadNormalizedClaimSource: async () => { fullLoads++; },
  });
  await Promise.all([context.loadAnalysisData(), context.loadAnalysisData()]);
  assert.equal(requests.length, 3);
  assert.equal(fullLoads, 0);
  assert.equal(context.normalizedSourceLoaded.all, false);
  assert.equal(context.analysisSourceClaims().length, 3);
  assert.equal(context.analysisSourceClaims('primary')[0].__analysis_source, 'primary');
  assert.deepEqual(Object.keys(context.claimStores.normalized.bySource), []);
});

test('finding chunks deduplicate requests, cache results, and retry failures', async () => {
  let calls = 0;
  const context = contextFor(['loadAnalysisFinding'], {
    URL, analysisPayloadsBySource: new Map([['primary', { url: 'https://example.test/release/analysis.json', chunkSize: 512, chunks: ['chunk.json'] }]]),
    analysisDetailChunkTasks: new Map(), analysisDetailChunkCache: new Map(),
    analysisDetailWaiters: [], analysisDetailRequests: 0,
    fetchJsonFromCandidates: async ([url]) => {
      assert.equal(url, 'https://example.test/release/chunk.json');
      calls++;
      if (calls === 1) throw new Error('offline');
      return { data: { schema_version: 'psychedelics_kg_analysis_findings_v1', source: 'primary' } };
    },
    prepareDetailBootstrapClaims: async () => [{ __analysis_row: 0, support: 'Complete quotation' }, { __analysis_row: 1, support: 'Other quotation' }],
  });
  const claim = { __analysis_bootstrap: true, __analysis_source: 'primary', __analysis_row: 0 };
  await assert.rejects(context.loadAnalysisFinding(claim), /offline/);
  const [one, two] = await Promise.all([context.loadAnalysisFinding(claim), context.loadAnalysisFinding({ ...claim, __analysis_row: 1 })]);
  assert.equal(one.support, 'Complete quotation');
  assert.equal(two.support, 'Other quotation');
  assert.equal((await context.loadAnalysisFinding(claim)), one);
  assert.equal(calls, 2);
  assert.equal(context.analysisDetailRequests, 0);
});
