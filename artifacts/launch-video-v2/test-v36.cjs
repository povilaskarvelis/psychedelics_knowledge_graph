const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v35.cjs');

const growth=fs.readFileSync(__dirname+'/src/product-v25/Growth.jsx','utf8');
const scale=fs.readFileSync(__dirname+'/src/product-v29/ResearchScale.jsx','utf8');
const openingBase=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const opening=fs.readFileSync(__dirname+'/src/product-v36/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v36/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('constructAreas'));
assert(growth.includes('constructionTiming?[50,126]:[38,116]'));
assert(growth.includes('(constructionTiming?148:116)+i*12'));
assert(scale.includes('constructFromParticles?178+index*6'));
assert(openingBase.includes('iconParticleTarget'));
assert(openingBase.includes('176+areaIndex*6+rand(i,6)*6'));
assert(openingBase.includes('178+areaIndex*6,196+areaIndex*6'));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV36" component={ProductFilmV36} durationInFrames={2944}'));

console.log('PASS: V36 holds the completed histogram and constructs each research-area symbol from its own staggered particle stream.');
