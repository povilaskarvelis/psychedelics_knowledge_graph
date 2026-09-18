const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Exercise the actual browser labelers without starting the UI or fetching data.
function analysisContext() {
  const source = fs.readFileSync(path.join(__dirname, '../../ui/app.js'), 'utf8');
  const context = vm.createContext({ document: { addEventListener() {}, getElementById() { return null; } } });
  const declarations = new Map();
  for (const match of source.matchAll(/^(?:async )?function (\w+)\([\s\S]*?^}/gm)) {
    // A few UI functions contain unindented template strings. They are deliberately
    // outside this pure calculation harness; invoking an absent function fails.
    try { new vm.Script(match[0]); declarations.set(match[1], match[0]); } catch (_) {}
  }
  declarations.forEach(code => vm.runInContext(code, context));
  const views = JSON.parse(fs.readFileSync(path.join(__dirname, '../../schema/graph_view_contract.json'), 'utf8')).views;
  context.ENTITY_CATEGORY_OPTIONS = views.map(view => ({ ...view, key: view.id }));
  context.ENTITY_CATEGORY_OPTION_SPECS = new Map(views.map(view => [view.id, {
    kinds: new Set(view.object_kinds || []), domains: new Set(view.domains || []),
    labels: new Set((view.object_labels || []).map(value => value.toLowerCase())),
  }]));
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../../ui/research-analysis.js'), 'utf8'), context);
  vm.runInContext('researchCoverageAxes = Object.keys(RESEARCH_FIELDS)', context);
  function execute(code) {
    for (let attempt = 0; attempt < 100; attempt++) {
      try { return vm.runInContext(code, context); }
      catch (error) {
        const name = String(error).match(/ReferenceError: (\w+) is not defined/)?.[1];
        if (!name) throw error;
        const declaration = source.match(new RegExp(`^(?:const|let) ${name} =\\s*[\\s\\S]*?;\\n`, 'm'));
        if (!declaration) throw error;
        execute(declaration[0].replace(/^(const|let) /, 'var '));
      }
    }
    throw new Error('Unresolved calculation dependencies');
  }
  return { context, execute };
}
module.exports = { analysisContext };
