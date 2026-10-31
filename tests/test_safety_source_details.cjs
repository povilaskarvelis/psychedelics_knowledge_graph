const { test } = require('node:test');
const assert = require('node:assert/strict');
const { analysisContext } = require('./helpers/analysis_context.cjs');

test('Safety details preserve the exact event and distinguish severity, seriousness and zero rates', () => {
  const { context, execute } = analysisContext();
  context.claim = {
    entity_label: 'Adverse events', safety_event_or_measure: 'Transient dysgeusia < 1 hour',
    safety_category: 'General tolerability/adverse events', severity: 'severe',
    seriousness: 'not serious', frequency_or_rate: '3/24 events', discontinuation_or_withdrawal: 0,
  };
  const html = execute('safetyObservationLinesHtml(claim)');
  assert.match(html, /Transient dysgeusia &lt; 1 hour/);
  assert.match(html, /Severity.*severe/);
  assert.match(html, /Seriousness.*not serious/);
  assert.match(html, /Reported frequency\/rate.*3\/24 events/);
  assert.match(html, /Discontinuation\/withdrawal.*0/);
  assert.match(execute('rawSearchTextForClaim(claim)'), /transient dysgeusia/);
});

test('Legacy claims do not acquire Safety assertions or empty detail lines', () => {
  const { execute } = analysisContext();
  assert.equal(execute('safetyObservationLinesHtml({entity_label:"Nausea"})'), '');
});
