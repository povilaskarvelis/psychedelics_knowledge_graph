const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v37.cjs');

const openingBase=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const opening=fs.readFileSync(__dirname+'/src/product-v38/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v38/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('refinedNarrative'));
assert(openingBase.includes("refinedNarrative?'It spans many research areas':'Across many research areas'"));
assert(openingBase.includes("sharpenedReveal&&!refinedNarrative?'synthesizing the literature yourself':'connecting findings yourself'"));
assert(openingBase.includes("refinedNarrative?'Now it comes together.':'Not anymore.'"));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV38" component={ProductFilmV38} durationInFrames={2944}'));

console.log('PASS: V38 restores the shorter burden statement and makes the breadth and reveal copy flow naturally.');
