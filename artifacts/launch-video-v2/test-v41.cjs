const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v40.cjs');

const openingBase=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const opening=fs.readFileSync(__dirname+'/src/product-v41/Opening.jsx','utf8');
const drilldownBase=fs.readFileSync(__dirname+'/src/product-v25/Drilldown.jsx','utf8');
const drilldown=fs.readFileSync(__dirname+'/src/product-v41/Drilldown.jsx','utf8');
const living=fs.readFileSync(__dirname+'/src/product-v24/Living.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v41/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('alignedSingleLineTitles'));
assert(drilldown.includes('alignedSingleLineTitles'));
assert(openingBase.includes('top={alignedSingleLineTitles?96:70} opacity={p(f,balancedNarrativeTiming?636:604,balancedNarrativeTiming?648:618)}'));
assert(drilldownBase.includes('top={alignedSingleLineTitles?96:70} size={compactTopTitles?96'));
assert(living.includes('>Knowledge graph</Label>'));
assert(living.includes("compactLabels?'Charts':'Visualizations'"));
assert(film.includes('<Living headlineSize={headlineSize} compactLabels/>'));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV41" component={ProductFilmV41} durationInFrames={2944}'));

console.log('PASS: V41 aligns the exploration handoff with the standard 96px scene-title baseline and renames visualizations to charts.');
