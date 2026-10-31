const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v33.cjs');

const opening=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const graph=fs.readFileSync(__dirname+'/src/product-v26/Graph.jsx','utf8');
const drilldown=fs.readFileSync(__dirname+'/src/product-v25/Drilldown.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v34/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes("narrativeRefinement?'Psychedelic science is growing fast'"));
assert(opening.includes("sharpenedReveal&&!refinedNarrative?'synthesizing the literature yourself':'connecting findings yourself'"));
assert(opening.includes("narrativeRefinement?'So you can explore how it all connects'"));
assert(opening.includes('areaYStart={balancedGraphLayout?370:300}'));
assert(graph.includes('areaYStart=300,areaGap=66'));
assert(drilldown.includes("explorationTitle?'So you can explore how it all connects'"));
assert(drilldown.includes('(balancedGraphLayout?370:300)+j*(balancedGraphLayout?58:66)'));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2962);
assert(root.includes('<Composition id="ProductV34" component={ProductFilmV34} durationInFrames={2962}'));

console.log('PASS: V34 clarifies the narrative, rebalances the graph, and preserves the exploration handoff.');
