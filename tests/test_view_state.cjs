const { test } = require('node:test');
const assert = require('node:assert/strict');
const viewState = require('../ui/view-state.js');

test('Explore view state round-trips scope and graph focus', () => {
  const encoded = viewState.write(new URL('https://psychedelicskg.com/?utm_source=test&data-source=local'), {
    mode: 'overview',
    view: 'safety_adverse_event',
    papers: 'reviews',
    access: 'all',
    from: '2010',
    to: '2025',
    graphSelection: { kind: 'edge', compound: 'Psilocybin', target: 'Anxiety' },
  });
  assert.equal(encoded.searchParams.get('v'), '1');
  assert.equal(encoded.searchParams.get('mode'), 'explore');
  assert.equal(encoded.searchParams.has('utm_source'), true);
  assert.equal(encoded.searchParams.has('data-source'), true);
  const decoded = viewState.read(encoded.searchParams);
  assert.equal(decoded.mode, 'overview');
  assert.equal(decoded.view, 'safety_adverse_event');
  assert.deepEqual(decoded.graphSelection, { kind: 'edge', compound: 'Psilocybin', target: 'Anxiety' });
  assert.deepEqual(decoded.warnings, []);
});

test('Analyze view state round-trips chart and focused-network state', () => {
  const encoded = viewState.write(new URL('https://psychedelicskg.com/'), {
    mode: 'analysis',
    section: 'compound',
    focus: 'psilocybin',
    scopeArea: 'condition_indication',
    papers: 'primary',
    access: 'open',
    coverage: { axes: ['outcome', 'followup'], queries: ['', 'long'], cell: ['Depression', 'Long'] },
    result: { type: 'compounds', leftKey: 'psilocybin', rightKey: 'lsd' },
    networkOrder: 'relationships',
    relationship: 'author',
    focusTimelineView: 'compounds',
    momentum: 7,
    publicationMode: 'mix',
    publicationCompound: 'psilocybin',
    publicationArea: 'condition_indication',
  });
  const decoded = viewState.read(encoded);
  assert.equal(decoded.mode, 'analysis');
  assert.equal(decoded.section, 'compound');
  assert.deepEqual(decoded.result, { type: 'compounds', leftKey: 'psilocybin', rightKey: 'lsd' });
  assert.equal(decoded.networkOrder, 'relationships');
  assert.equal(decoded.focusTimelineView, 'compounds');
  assert.equal(decoded.momentum, 7);
  assert.equal(decoded.publicationMode, 'mix');
  assert.deepEqual(decoded.coverage.cell, ['Depression', 'Long']);
});

test('view state rejects malformed and oversized values without throwing', () => {
  const decoded = viewState.read(new URLSearchParams({
    v: '999', mode: 'explore', papers: 'secrets', access: 'private',
    graph: 'edge', compound: 'Psilocybin', result: '{nope', momentum: '100',
  }));
  assert.equal(decoded.mode, 'overview');
  assert.equal(decoded.papers, '');
  assert.equal(decoded.graphSelection, null);
  assert.equal(decoded.result, null);
  assert.ok(decoded.warnings.includes('unsupported-version'));
  assert.ok(decoded.warnings.includes('graph'));
  assert.ok(decoded.warnings.includes('result'));
});

test('unversioned legacy mode=explore continues to open Analyze', () => {
  assert.equal(viewState.read(new URLSearchParams('mode=explore')).mode, 'analysis');
  assert.equal(viewState.read(new URLSearchParams('v=1&mode=explore')).mode, 'overview');
});

test('canonical writing clears retired view parameters', () => {
  const encoded = viewState.write(new URL('https://example.test/?task=evidence&research=x&compare=y&lens=journal'), {
    mode: 'analysis', section: 'all',
  });
  for (const key of ['task', 'research', 'compare', 'lens']) assert.equal(encoded.searchParams.has(key), false);
});
