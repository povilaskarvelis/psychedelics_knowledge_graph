const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v46.cjs');

const opening=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const openingV47=fs.readFileSync(__dirname+'/src/product-v47/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v47/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('But making sense of it all remains<br/>the bottleneck'));
assert(openingV47.includes('remainsBottleneckCopy'));
assert(film.includes('compactLabels alignIngestionWithDivider'));
assert(film.includes("['Ketamine','Psilocybin','MDMA','LSD','DMT','Ayahuasca','Mescaline']"));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV47" component={ProductFilmV47} durationInFrames={2944}'));

console.log('PASS: V47 changes the synthesis line to “remains the bottleneck” and preserves the V46 animation.');
