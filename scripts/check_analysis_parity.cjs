/* Run against a generated local release: node scripts/check_analysis_parity.cjs RUN_DIR SOURCE_PATHS_JSON */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { analysisContext } = require('../tests/helpers/analysis_context.cjs');
const codec = require('../ui/analysis-payload.js');
const { context, execute } = analysisContext();
const run = process.argv[2];
if (!run || !process.argv[3]) throw new Error('Pass a release directory and a JSON mapping of source names to compact payload paths.');
const pointer = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const compactPaths = pointer.active_analysis_bootstraps || pointer;
let checked = 0;
for (const source of ['primary', 'meta_analyses', 'reviews']) {
  const full = JSON.parse(fs.readFileSync(path.join(run, `detail_bootstrap_${source}.json`), 'utf8'));
  const compact = JSON.parse(fs.readFileSync(compactPaths[source], 'utf8'));
  const raws = [...codec.batches(compact)].flat();
  assert.equal(raws.length, full.rows.length);
  for (let index = 0; index < full.rows.length; index++) {
    context.raw = Object.fromEntries(full.fields.map((field, i) => [field, full.values[full.rows[index][i]]]).filter(([,value]) => value !== null && value !== ''));
    context.small = raws[index];
    execute('var original = routeNativeFindingForCurrentUi(raw); var reduced = routeNativeFindingForCurrentUi(small);');
    for (const expression of [
      'researchRow(CLAIM)', 'authorRoleIdentity(CLAIM, "first")', 'authorRoleIdentity(CLAIM, "last")',
      'analysisCompoundSubjectsForClaim(CLAIM)', 'isHiddenMainGraphItem(CLAIM)', 'isMainGraphAdmitted(CLAIM)',
      'claimRelationText(CLAIM)',
    ]) {
      const expressionFor = variable => expression.replaceAll('CLAIM', variable);
      // researchRow contains its input claim; compare only the chart-facing metadata.
      const get = variable => {
        const result = execute(expressionFor(variable));
        if (expression.startsWith('researchRow')) {
          const { claim, ...metadata } = result;
          return JSON.stringify(metadata);
        }
        return JSON.stringify(result);
      };
      assert.equal(get('reduced'), get('original'), `${source} row ${index}: ${expression}`);
    }
    checked++;
  }
}
console.log(`Analysis parity: ${checked} findings; all coverage axes, paper identity, authors, compounds, admission and relation labels match.`);
