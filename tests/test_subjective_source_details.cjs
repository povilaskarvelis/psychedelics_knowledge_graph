const {test}=require('node:test');
const assert=require('node:assert/strict');
const {analysisContext}=require('./helpers/analysis_context.cjs');

test('Subjective details retain the joint construct, measure, outcome relationship and value',()=>{
  const {context,execute}=analysisContext();
  context.claim={kg_domain:'subjective_experience',entity_label:'Positive affect',
    subjective_construct:'Positive affect; Negative affect',instrument_or_measure:'PANAS < follow-up',
    setting_or_context:'Monitored session',relationship_to_outcome:'Negative affect did not predict outcome',statistic_or_value:'r = 0.25; p = 0.04'};
  const html=execute('subjectiveObservationLinesHtml(claim)');
  for(const text of ['Positive affect; Negative affect','PANAS &lt; follow-up','Monitored session',
    'Negative affect did not predict outcome','r = 0.25; p = 0.04']) assert.ok(html.includes(text));
});
test('Missing subjective assertions and other domains do not acquire lines',()=>{
  const {execute}=analysisContext();
  assert.equal(execute('subjectiveObservationLinesHtml({kg_domain:"subjective_experience"})'),'');
  assert.equal(execute('subjectiveObservationLinesHtml({kg_domain:"cognitive_behavioral",statistic_or_value:"5"})'),'');
});
test('Subjective reported zero is retained',()=>{
  const {execute}=analysisContext();
  assert.match(execute('subjectiveObservationLinesHtml({kg_domain:"subjective_experience",statistic_or_value:0})'),/Reported value.*0/);
});
