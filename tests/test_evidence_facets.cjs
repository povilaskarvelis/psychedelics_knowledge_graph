const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { facetContext } = require('./helpers/evidence_facets.cjs');
const research = require('../ui/research-model.js');
const facets = facetContext();

test('free-text study designs collapse into reusable groups without losing missingness', () => {
  for (const study_design of ['Comparative study (two treatment groups)', 'Comparative study: novel dosing protocol']) {
    assert.equal(facets.studyDesignFacetLabel({ study_design }), 'Comparative study');
  }
  assert.equal(facets.studyDesignFacetLabel({ study_design: 'Analytical method development and validation' }), 'Method development / validation');
  assert.equal(facets.studyDesignFacetLabel({ study_design: 'unrecognized protocol with unique apparatus' }), 'Other study designs');
  assert.equal(facets.studyDesignFacetLabel({}), '');
  assert.equal(facets.studyDesignFacetLabel({ study_design_category: 'other' }), 'Other study designs');
  assert.equal(facets.studyDesignFacetLabel({ study_design: 'RCT' }), 'RCT');
  assert.equal(facets.studyDesignFacetLabel({ study_design_category: 'phase_2_rct' }), 'RCT');
});

test('blinding, crossover and comparison alone do not imply randomized allocation', () => {
  for (const study_design of ['double-blind controlled trial', 'placebo-controlled crossover study']) {
    assert.equal(facets.studyDesignFacetLabel({ study_design, system: 'clinical' }), 'Controlled study (randomization unclear)');
  }
  assert.equal(facets.studyDesignFacetLabel({ study_design: 'Non-randomized controlled trial', system: 'clinical' }), 'Nonrandomized study');
  assert.equal(facets.studyDesignFacetLabel({ study_design: 'randomised placebo-controlled trial', system: 'clinical' }), 'RCT');
  assert.equal(facets.studyDesignFacetLabel({ study_design: 'Comparative study', study_title: 'Lessons from a randomized trial' }), 'Comparative study');
});

test('systems group specific cell preparations and retain mixed, unclear and missing values', () => {
  for (const system of ['HEK293T cells', 'Xenopus laevis oocytes', 'in_vitro']) {
    assert.equal(facets.analysisExperimentalSystemFacetLabel({ system }), 'In vitro');
  }
  assert.equal(facets.analysisExperimentalSystemFacetLabel({ system: 'ex_vivo' }), 'Ex vivo');
  assert.equal(facets.analysisExperimentalSystemFacetLabel({ system: 'computational model (Glide module)' }), 'Computational');
  assert.equal(facets.analysisExperimentalSystemFacetLabel({ system: 'in vivo and in vitro' }), 'Mixed systems');
  assert.equal(facets.analysisExperimentalSystemFacetLabel({ system: 'frontal cortex' }), 'Other / unspecified system');
  assert.equal(facets.analysisExperimentalSystemFacetLabel({}), '');
});

test('mixed populations remain distinct from unclassified populations', () => {
  assert.equal(facets.populationModelFacetLabel({ population: 'human participants and mice' }), 'Mixed populations / models');
  assert.equal(facets.populationModelFacetLabel({ population: 'unclassified model' }), 'Other');
  assert.equal(facets.populationModelFacetLabel({}), '');
});

test('unrecognized normalized metadata is grouped rather than displayed verbatim', () => {
  assert.equal(facets.clinicalComparatorFacetLabel({ comparator_normalized: 'active_treatment' }), 'Active treatment');
  assert.equal(facets.clinicalComparatorFacetLabel({ comparator_normalized: 'escitalopram 20 mg daily' }), 'Active treatment');
  assert.equal(facets.clinicalComparatorFacetLabel({ comparator_normalized: 'novel comparison procedure' }), 'Other');
  assert.equal(facets.clinicalFollowUpWindowFacetLabel({ follow_up_window_normalized: 'six weeks' }), 'Medium follow-up (1-3 months)');
  assert.equal(facets.clinicalFollowUpWindowFacetLabel({ follow_up_window_normalized: 'custom measurement schedule' }), 'Other / mixed follow-up');
  assert.equal(facets.mechanisticAssayFamilyFacetLabel({ assay_family_normalized: 'patch-clamp recordings using protocol X' }), 'Electrophysiology');
  assert.equal(facets.mechanisticAssayFamilyFacetLabel({ assay_family_normalized: 'custom experimental method' }), 'Other');
});

test('absence, inapplicability and missing metadata remain distinct', () => {
  assert.equal(facets.clinicalComparatorFacetLabel({ comparator: 'none' }), 'No comparator');
  assert.equal(facets.clinicalComparatorFacetLabel({ comparator: 'not_applicable' }), 'Not applicable');
  assert.equal(facets.clinicalComparatorFacetLabel({}), 'Not reported');
  assert.equal(facets.clinicalFollowUpWindowFacetLabel({ follow_up_duration: 'not_applicable' }), 'Not applicable');
  assert.equal(facets.clinicalFollowUpWindowFacetLabel({}), 'Follow-up not reported');
});

test('canonical comparator, follow-up and method groups are stable', () => {
  for (const [order, fn, key] of [
    ['CLINICAL_COMPARATOR_ORDER', 'clinicalComparatorFacetLabel', 'comparator_normalized'],
    ['CLINICAL_FOLLOW_UP_WINDOW_ORDER', 'clinicalFollowUpWindowFacetLabel', 'follow_up_window_normalized'],
    ['MECHANISTIC_ASSAY_FAMILY_ORDER', 'mechanisticAssayFamilyFacetLabel', 'assay_family_normalized'],
  ]) {
    for (const label of vm.runInContext(order, facets)) assert.equal(facets[fn]({ [key]: label }), label);
  }
});

test('Explore and coverage use the same system groups and deduplicate source papers', () => {
  const context = facetContext();
  Object.assign(context, {
    document: { addEventListener() {} }, ENTITY_CATEGORY_OPTIONS: [],
    isSecondaryLiteratureClaim: () => false, studyKey: (claim) => claim.paper,
    parseYearValue: () => 2024, outcomeScaleLabelsForClaim: () => [],
    brainMeasureFacetLabels: () => ['Functional connectivity'],
    analysisCompoundSubjectsForClaim: () => [],
    evidenceView: 'primary', currentDetailPanelProfile: () => ({ experimentalSystem: true }),
    renderFacetCompositionChart: (entries, title, filterField) => ({ entries, filterField }),
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../ui/research-analysis.js'), 'utf8'), context);
  const claims = [
    { paper: 'a', system: 'HEK293T cells', study_design: 'comparative study: protocol A' },
    { paper: 'a', system: 'in_vitro', study_design: 'comparative study: protocol B' },
    { paper: 'b', system: 'Xenopus oocytes', study_design: 'comparative study: protocol C' },
    { paper: 'c', system: 'in_vivo', study_design: 'comparative study: protocol D' },
  ];
  claims.forEach(claim => { claim.study_design_category = 'experimental_study'; });
  vm.runInContext('researchCoverageAxes = ["system", "design"]', context);
  const rows = claims.map(context.researchRow);
  vm.runInContext('researchCoverageAxes = ["assay", "design"]', context);
  const methodRow = context.researchRow({ paper: 'method', assay_family_normalized: 'fMRI' });
  assert.deepEqual(Array.from(methodRow.fields.assay), ['fMRI']);
  const chart = context.renderExperimentalSystemChart(claims);
  const matrix = research.coverage(rows, 'system', 'design');
  const cell = matrix.cells.get(JSON.stringify(['In vitro', 'Experimental study']));
  assert.equal(cell.size, 2);
  const matching = research.matchingCell(rows, 'system', 'design', 'In vitro', 'Experimental study');
  assert.deepEqual(new Set(matching.map(row => row.paperKey)), new Set(['a', 'b']));
  assert.equal(chart.entries.find(entry => entry.label === 'In vitro').studies, 2);
  for (const row of rows) assert.equal(context.fieldValueForClaim(row.claim, chart.filterField), row.fields.system[0]);
});
