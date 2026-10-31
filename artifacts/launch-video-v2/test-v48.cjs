const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v47.cjs');

const living=fs.readFileSync(__dirname+'/src/product-v24/Living.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v48/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(living.includes('rightPanelLabel'));
assert(film.includes('rightPanelLabel="Data visualizations"'));
assert(film.includes('compactLabels alignIngestionWithDivider'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV48" component={ProductFilmV48} durationInFrames={2944}'));

console.log('PASS: V48 labels the derived analytical panel “Data visualizations” while preserving the V47 animation.');
