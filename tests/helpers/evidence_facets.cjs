const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Load the actual browser labelers without booting the graph or fetching data.
function facetContext(source = fs.readFileSync(path.join(__dirname, '../../ui/app.js'), 'utf8')) {
  const context = vm.createContext({});
  const constants = [
    'EMPTY_FIELD_VALUES', 'STUDY_DESIGN_CATEGORY_LABELS', 'STUDY_DESIGN_ORDER',
    'POPULATION_MODEL_CATEGORY_LABELS', 'POPULATION_MODEL_ORDER',
    'CLINICAL_COMPARATOR_LABEL_ALIASES', 'CLINICAL_COMPARATOR_ORDER',
    'CLINICAL_FOLLOW_UP_WINDOW_ORDER', 'FOLLOW_UP_NUMBER_WORDS',
    'ASSAY_FAMILY_DISPLAY_LABELS', 'MECHANISTIC_ASSAY_FAMILY_ORDER',
    'EXPERIMENTAL_SYSTEM_ORDER',
  ];
  for (const name of constants) {
    const declaration = source.match(new RegExp(`^const ${name} = [\\s\\S]*?;\\n`, 'm'));
    if (!declaration) throw new Error(`Missing constant: ${name}`);
    vm.runInContext(declaration[0], context);
  }
  const functions = [
    'normalizeValue', 'cleanDisplayText', 'meaningfulText', 'controlledCategoryLabel',
    'labelFromSlug', 'displayFieldLabel', 'populationModelFacetLabel',
    'studyDesignLabel', 'studyDesignFacetLabel', 'clinicalComparatorDisplayLabel',
    'clinicalComparatorFacetLabel', 'followUpTextFromClaim', 'followUpDurationDays',
    'followUpWindowFromDays', 'clinicalFollowUpWindowFacetLabel', 'assayFamilyText',
    'assayFamilyFromText', 'mechanisticAssayFamilyFacetLabel',
    'analysisExperimentalSystemFacetLabel', 'fieldValueForClaim',
    'renderExperimentalSystemChart', 'summarizeFacetEvidence', 'preferredFacetLabel', 'facetLabelCaseScore',
  ];
  for (const name of functions) {
    const declaration = source.match(new RegExp(`^function ${name}\\([\\s\\S]*?^}`, 'm'));
    if (!declaration) throw new Error(`Missing function: ${name}`);
    vm.runInContext(declaration[0], context);
  }
  vm.runInContext('for (const label of MECHANISTIC_ASSAY_FAMILY_ORDER) ASSAY_FAMILY_DISPLAY_LABELS[normalizeValue(label)] = label;', context);
  return context;
}

module.exports = { facetContext };
