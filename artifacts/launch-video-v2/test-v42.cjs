const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v41.cjs');

const living=fs.readFileSync(__dirname+'/src/product-v24/Living.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v42/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(living.includes('pipelineFlow=false'));
assert(living.includes('const graphRefresh='));
assert(living.includes('const chartFlow='));
assert(living.includes('const chartRefresh='));
assert(living.includes('id="graph-to-charts"'));
assert(film.includes('<Living headlineSize={headlineSize} compactLabels pipelineFlow/>'));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV42" component={ProductFilmV42} durationInFrames={2944}'));

console.log('PASS: V42 makes the update pipeline explicit: paper to knowledge graph, then graph to charts.');
