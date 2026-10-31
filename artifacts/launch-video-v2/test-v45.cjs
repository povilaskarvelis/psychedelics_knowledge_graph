const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v44.cjs');

const researchers=fs.readFileSync(__dirname+'/src/product-v11/Researchers.jsx','utf8');
const analytical=fs.readFileSync(__dirname+'/src/product-v23/AnalyticalViews.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v45/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(researchers.includes('compoundNames=compounds'));
assert(analytical.includes('researcherCompounds'));
assert(film.includes("['Ketamine','Psilocybin','MDMA','LSD','DMT','Ayahuasca','Mescaline']"));
assert(!film.includes('R-ketamine'));
assert(!film.includes('S-ketamine'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV45" component={ProductFilmV45} durationInFrames={2944}'));

console.log('PASS: V45 replaces redundant ketamine variants with data-backed ayahuasca and mescaline examples.');
