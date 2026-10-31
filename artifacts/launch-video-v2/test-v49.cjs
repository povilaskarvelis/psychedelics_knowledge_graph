const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v48.cjs');

const opening=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const openingV49=fs.readFileSync(__dirname+'/src/product-v49/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v49/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('dualSidedGraphFormation=false'));
assert(opening.includes('dualSidedGraphFormation?4:3'));
assert(opening.includes('formsCompound'));
assert(openingV49.includes('dualSidedGraphFormation'));
assert(film.includes('rightPanelLabel="Data visualizations"'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV49" component={ProductFilmV49} durationInFrames={2944}'));

console.log('PASS: V49 constructs both compound and research-area nodes from scattered paper fragments.');
