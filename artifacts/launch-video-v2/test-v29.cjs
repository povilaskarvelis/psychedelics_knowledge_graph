const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v28.cjs');

const opening=fs.readFileSync(__dirname+'/src/product-v29/Opening.jsx','utf8');
const scale=fs.readFileSync(__dirname+'/src/product-v29/ResearchScale.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v29/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes("['Across many research areas']"));
assert(!opening.includes('From molecular mechanisms'));
assert(scale.includes('Dna'));
assert(scale.includes("Icon:Dna"));
assert(!scale.includes('Atom'));
assert.equal((scale.match(/Icon:/g)||[]).length,8);
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2922);
assert(root.includes('<Composition id="ProductV29" component={ProductFilmV29} durationInFrames={2922}'));

console.log('PASS: V29 uses the concise breadth headline and a biological DNA symbol.');
