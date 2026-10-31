const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v31.cjs');

const opening=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const drilldown=fs.readFileSync(__dirname+'/src/product-v25/Drilldown.jsx','utf8');
const wrapper=fs.readFileSync(__dirname+'/src/product-v32/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v32/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('Now it’s all connected in a living<br/>knowledge graph'));
assert(opening.includes('From study details to patterns<br/>across the field'));
assert(drilldown.includes('From study details to patterns<br/>across the field'));
assert(wrapper.includes('<PreviousOpening balancedTitles wideTitles/>'));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2922);
assert(root.includes('<Composition id="ProductV32" component={ProductFilmV32} durationInFrames={2922}'));

console.log('PASS: V32 uses the full headline width and preserves the widened handoff title.');
