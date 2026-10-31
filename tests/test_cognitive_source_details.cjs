const {test}=require('node:test');
const assert=require('node:assert/strict');
const {analysisContext}=require('./helpers/analysis_context.cjs');
test('Cognitive details keep the task, context, reported construct and numeric value',()=>{
 const {context,execute}=analysisContext();
 context.claim={kg_domain:'cognitive_behavioral',entity_label:'Verbal memory',construct_or_behavior:'Delayed verbal recall',
 task_or_measure:'Delayed recall T-score < baseline',behavioral_context:'Ketamine versus ECT',statistic_or_value:'Ketamine −0.9±1.1; ECT −9.7±1.2'};
 const html=execute('cognitiveObservationLinesHtml(claim)');
 assert.match(html,/Delayed verbal recall/);assert.match(html,/Delayed recall T-score &lt; baseline/);
 assert.match(html,/Ketamine versus ECT/);assert.match(html,/−0.9±1.1/);assert.match(html,/−9.7±1.2/);
});
test('Missing cognitive assertions and other domains do not acquire detail fields',()=>{
 const {execute}=analysisContext();
 assert.equal(execute('cognitiveObservationLinesHtml({kg_domain:"cognitive_behavioral"})'),'');
 assert.equal(execute('cognitiveObservationLinesHtml({kg_domain:"clinical_outcome",statistic_or_value:"5"})'),'');
});

test('A reported zero is preserved',()=>{
 const {execute}=analysisContext();
 assert.match(execute('cognitiveObservationLinesHtml({kg_domain:"cognitive_behavioral",statistic_or_value:0})'),/Reported value.*0/);
});
