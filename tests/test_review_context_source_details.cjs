const {test}=require('node:test');
const assert=require('node:assert/strict');
const {analysisContext}=require('./helpers/analysis_context.cjs');
function review(){return {paper_assessment_route:'secondary_literature',source_type:'narrative_review',
  kg_domain:'intervention_context',review_context_component:'Clinical trials with blinded control conditions',
  review_context_summary:'The review discusses context. '+ 'Effects cannot be isolated from the treatment package. '.repeat(12)+'Comparative benefit was not established.',
  review_context_limitations:'Limited evidence < no independent component evaluation'};}

test('Review context summary retains its entire qualification',()=>{
  const {context,execute}=analysisContext();context.claim=review();
  assert.equal(execute('isReviewContextClaim(claim)'),true);
  assert.equal(execute('claimMainFindingText(claim)'),context.claim.review_context_summary);
});
test('Reviewed context and source limitations are visible and escaped',()=>{
  const {context,execute}=analysisContext();context.claim=review();
  const html=execute('reviewContextLinesHtml(claim)');
  assert.ok(html.includes(context.claim.review_context_component));
  assert.ok(html.includes('Limited evidence &lt; no independent component evaluation'));
});
test('Other source types and absent limitations do not acquire review assertions',()=>{
  const {context,execute}=analysisContext();context.claim={...review(),paper_assessment_route:'primary_study',source_type:'primary'};
  assert.equal(execute('reviewContextLinesHtml(claim)'),'');
  context.claim={...review(),review_context_limitations:'not_reported'};
  assert.ok(!execute('reviewContextLinesHtml(claim)').includes('Source limitations'));
  assert.equal(execute('reviewContextLinesHtml({kg_domain:"intervention_context"})'),'');
});
