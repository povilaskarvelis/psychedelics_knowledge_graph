const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v45.cjs');

const living=fs.readFileSync(__dirname+'/src/product-v24/Living.jsx','utf8');
const opening=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const openingV46=fs.readFileSync(__dirname+'/src/product-v46/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v46/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(living.includes('alignIngestionWithDivider=false'));
assert(living.includes('alignIngestionWithDivider?996'));
assert(opening.includes('But making sense of it all<br/>becomes the bottleneck'));
assert(opening.includes('organizes findings into one living map'));
assert(openingV46.includes('bottleneckCopy findingsMapCopy'));
assert(film.includes('compactLabels alignIngestionWithDivider'));
assert(!film.includes('pipelineFlow'));
assert(!film.includes('refinedPipelineFlow'));
assert(film.includes("['Ketamine','Psilocybin','MDMA','LSD','DMT','Ayahuasca','Mescaline']"));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV46" component={ProductFilmV46} durationInFrames={2944}'));

console.log('PASS: V46 restores the centered simultaneous graph-and-charts update and aligns ingestion with the divider.');
