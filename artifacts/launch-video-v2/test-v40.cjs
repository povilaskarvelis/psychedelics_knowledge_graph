const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v39.cjs');

const openingBase=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const opening=fs.readFileSync(__dirname+'/src/product-v40/Opening.jsx','utf8');
const drilldownBase=fs.readFileSync(__dirname+'/src/product-v25/Drilldown.jsx','utf8');
const drilldown=fs.readFileSync(__dirname+'/src/product-v40/Drilldown.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v40/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('compactTopTitles'));
assert(drilldown.includes('compactTopTitles'));
assert(openingBase.includes('const openingTitleSize=compactTopTitles?96:100'));
assert(drilldownBase.includes('compactTopTitles?96'));
assert(film.includes('const headlineSize=96'));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV40" component={ProductFilmV40} durationInFrames={2944}'));

console.log('PASS: V40 standardizes top-level scene headlines at 96px and keeps the exploration handoff on one line.');
