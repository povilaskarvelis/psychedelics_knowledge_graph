const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v50.cjs');

const opening=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const openingV51=fs.readFileSync(__dirname+'/src/product-v51/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v51/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('earlySolutionTitle=false'));
assert(opening.includes('earlySolutionTitle?434:498'));
assert(opening.includes('earlySolutionTitle?446:506'));
assert(openingV51.includes('earlySolutionTitle'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV51" component={ProductFilmV51} durationInFrames={2944}'));

console.log('PASS: V51 introduces the solution title as the graph begins forming, eliminating the empty handoff.');
