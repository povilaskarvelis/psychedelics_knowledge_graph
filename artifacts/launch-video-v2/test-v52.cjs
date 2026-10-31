const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v51.cjs');

const opening=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const openingV52=fs.readFileSync(__dirname+'/src/product-v52/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v52/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('indefiniteBottleneckCopy=false'));
assert(opening.includes('But making sense of it all remains<br/>a bottleneck'));
assert(openingV52.includes('indefiniteBottleneckCopy'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV52" component={ProductFilmV52} durationInFrames={2944}'));

console.log('PASS: V52 changes the synthesis statement from “the bottleneck” to “a bottleneck.”');
