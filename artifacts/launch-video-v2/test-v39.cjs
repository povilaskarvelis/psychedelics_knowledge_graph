const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v38.cjs');

const openingBase=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const opening=fs.readFileSync(__dirname+'/src/product-v39/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v39/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('integratedNarrative'));
assert(openingBase.includes("integratedNarrative?'…across many research areas'"));
assert(openingBase.includes('But seeing how the findings<br/>fit together is still difficult'));
assert(openingBase.includes('sharpenedReveal&&!integratedNarrative'));
assert(openingBase.includes('Psychedelics Knowledge Graph<br/>organizes them into one living map'));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV39" component={ProductFilmV39} durationInFrames={2944}'));

console.log('PASS: V39 joins the opening with an ellipsis, states the synthesis problem plainly, and removes the dramatic bridge.');
