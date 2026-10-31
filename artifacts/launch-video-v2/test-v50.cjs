const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v49.cjs');

const opening=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const openingV50=fs.readFileSync(__dirname+'/src/product-v50/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v50/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('const displayNames=compoundNames??names'));
assert(openingV50.includes("'Salvinorin A','Ibogaine','5-MeO-DMT','Mescaline','Ayahuasca'"));
for(const excluded of ['Noribogaine','Methoxetamine','Methylone','Dextromethorphan','Nitrous oxide','R-ketamine','S-ketamine'])assert(!openingV50.includes(excluded));
assert(film.includes('rightPanelLabel="Data visualizations"'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV50" component={ProductFilmV50} durationInFrames={2944}'));

console.log('PASS: V50 uses a curated, defensible 15-name psychedelic display list.');
