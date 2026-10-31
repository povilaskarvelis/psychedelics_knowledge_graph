const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v34.cjs');

const growth=fs.readFileSync(__dirname+'/src/product-v25/Growth.jsx','utf8');
const scale=fs.readFileSync(__dirname+'/src/product-v29/ResearchScale.jsx','utf8');
const openingBase=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const opening=fs.readFileSync(__dirname+'/src/product-v35/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v35/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('timingTightening'));
assert(opening.includes('continuousMorph'));
assert(opening.includes('animatedEllipsis'));
assert(opening.includes('singleActivation'));
assert(growth.includes('constructionTiming?[50,126]:[38,116]'));
assert(growth.includes('const dissolve=morphToAreas'));
assert(scale.includes('continuousTransform'));
assert(openingBase.includes('continuousMorph?480:256'));
assert(openingBase.includes("sharpenedReveal&&!refinedNarrative?'synthesizing the literature yourself':'connecting findings yourself'"));
assert(openingBase.includes('animatedEllipsis?<span'));
assert(openingBase.includes('singleActivation?516:532'));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV35" component={ProductFilmV35} durationInFrames={2944}'));

console.log('PASS: V35 tightens the opening, performs continuous object transformations, and removes the repeated edge pulse.');
