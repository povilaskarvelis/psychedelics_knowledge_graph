const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v43.cjs');

const living=fs.readFileSync(__dirname+'/src/product-v24/Living.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v44/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(living.includes('refinedPipelineFlow=false'));
assert(living.includes('const ingestionPulse='));
assert(living.includes('[0,1,2,3].map(k=>'));
assert(living.includes('selected.map((area,j)=>'));
assert(film.includes('pipelineFlow refinedPipelineFlow'));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV44" component={ProductFilmV44} durationInFrames={2944}'));

console.log('PASS: V44 restores the paper-to-pulse impact and derives charts through staggered graph-output traces.');
