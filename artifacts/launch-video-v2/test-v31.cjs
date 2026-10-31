const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v30.cjs');

const opening=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const drilldown=fs.readFileSync(__dirname+'/src/product-v25/Drilldown.jsx','utf8');
const facets=fs.readFileSync(__dirname+'/src/product-v13/StudyFacets.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v31/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('balancedTitles?<React.Fragment>'));
assert(opening.includes('size={100}>Psychedelic research is growing fast'));
assert(opening.includes('size={100}>Across many research areas'));
assert(opening.includes('Now it’s all connected in a<br/>living knowledge graph'));
assert(opening.includes('From study details to<br/>patterns across the field'));
assert(drilldown.includes('size={compactTopTitles?96:balancedTitles?100:86}'));
assert(drilldown.includes('separateBars={separateBars}'));
assert(facets.includes("stroke={separateBars?'#101816':'none'}"));
assert(film.includes("import {Opening} from './Opening'"));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2922);
assert(root.includes('<Composition id="ProductV31" component={ProductFilmV31} durationInFrames={2922}'));

console.log('PASS: V31 normalizes the headline hierarchy and separates stacked facet categories.');
