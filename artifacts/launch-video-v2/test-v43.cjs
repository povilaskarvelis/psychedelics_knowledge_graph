const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v42.cjs');

const openingBase=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const opening=fs.readFileSync(__dirname+'/src/product-v43/Opening.jsx','utf8');
const drilldownBase=fs.readFileSync(__dirname+'/src/product-v25/Drilldown.jsx','utf8');
const drilldown=fs.readFileSync(__dirname+'/src/product-v43/Drilldown.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v43/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('balancedNarrativeTiming'));
assert(drilldown.includes('balancedNarrativeTiming'));
assert(openingBase.includes('balancedNarrativeTiming?620:588'));
assert(openingBase.includes('balancedNarrativeTiming?636:604'));
assert(drilldownBase.includes('balancedNarrativeTiming?70:100'));
assert(drilldownBase.includes('balancedNarrativeTiming?91:121'));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV43" component={ProductFilmV43} durationInFrames={2944}'));

console.log('PASS: V43 holds the product statement longer and shortens the exploration handoff.');
