const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v27.cjs');

const scale=fs.readFileSync(__dirname+'/src/product-v28/ResearchScale.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v28/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');
const pkg=require('./package.json');

for(const icon of ['Atom','Brain','BrainCircuit','Eye','Stethoscope','ShieldCheck','UsersRound','Earth']) {
 assert(scale.includes(icon),`Missing professional vector icon: ${icon}`);
}
for(const label of ['Molecular','mechanisms','Brain','function','Cognition &','behavior','Subjective','experience','Clinical','outcomes','Safety','Real-world','use','Public','health']) {
 assert(scale.includes(`'${label}'`),`Missing breadth label: ${label}`);
}

assert.equal((scale.match(/Icon:/g)||[]).length,8,'The breadth frame should contain eight research areas');
assert(scale.includes('strokeWidth={1.8} absoluteStrokeWidth'),'All icons should share a consistent professional stroke treatment');
assert.equal(pkg.dependencies['lucide-react'],'^1.47.0');
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2922);
assert(root.includes('<Composition id="ProductV28" component={ProductFilmV28} durationInFrames={2922}'));

console.log('PASS: V28 uses eight consistent Lucide vectors and preserves the silent 97.4-second composition.');
