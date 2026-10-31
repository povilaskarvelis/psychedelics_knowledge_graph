const {test}=require('node:test');
const assert=require('node:assert/strict');
const {analysisContext}=require('./helpers/analysis_context.cjs');

function fixture(){return {paper_assessment_route:'secondary_literature',source_family:'secondary_literature',
  source_type:'guideline',paper_type:'guideline',kg_entity_kind:'recommendation_topic',
  publication_type:'Meta-analysis',recommendation_statement:'Do not use routinely. '+ 'The evidence remains uncertain and context dependent. '.repeat(12)+'Only after further evaluation.',
  recommendation_type:'eligibility_or_selection',recommendation_strength:'conditional',direction_or_tone:'recommends_against',
  population_or_system:'Participants < 18',rationale_or_evidence_basis:'Insufficient evidence < no demonstrated effect'};}

test('Guidance stays in secondary literature with its source badge and entire qualified statement',()=>{
  const {context,execute}=analysisContext();context.claim=fixture();
  assert.equal(execute('isRecommendationClaim(claim)'),true);
  assert.equal(execute('isReviewLiteratureClaim(claim)'),true);
  assert.equal(execute('isMetaAnalysisClaim(claim)'),false);
  assert.equal(execute('literatureTypeLabel(claim)'),'Guideline');
  assert.equal(execute('literatureMainFindingLabel(claim)'),'Recommendation');
  assert.equal(execute('claimMainFindingText(claim)'),context.claim.recommendation_statement);
  context.claim.source_type=context.claim.paper_type='consensus_statement';
  assert.equal(execute('literatureTypeLabel(claim)'),'Consensus statement');
});
test('Recommendation card retains strength, against-use position, population and rationale safely',()=>{
  const {context,execute}=analysisContext();context.claim=fixture();
  const html=execute('recommendationLinesHtml(claim)');
  for(const text of ['Eligibility Or Selection','Conditional','Recommends Against','Participants &lt; 18',
    'Insufficient evidence &lt; no demonstrated effect']) assert.ok(html.includes(text),text);
});
test('Missing recommendation semantics and primary effects do not acquire guidance lines',()=>{
  const {context,execute}=analysisContext();
  context.claim={paper_assessment_route:'secondary_literature',source_type:'guideline',recommendation_strength:'not_reported'};
  assert.equal(execute('recommendationLinesHtml(claim)'),'');
  context.claim={...fixture(),paper_assessment_route:'primary_study',source_family:'primary_study',source_type:'primary',paper_type:'primary',kg_entity_kind:'condition_indication'};
  assert.equal(execute('recommendationLinesHtml(claim)'),'');
});
