const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v36.cjs');

const openingBase=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const opening=fs.readFileSync(__dirname+'/src/product-v37/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v37/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('sharpenedReveal'));
assert(opening.includes('nonRepeatingPulse'));
assert(openingBase.includes("'synthesizing the literature yourself'"));
assert(openingBase.includes("refinedNarrative?'Now it comes together.':'Not anymore.'"));
assert(openingBase.includes('Psychedelics Knowledge Graph<br/>brings findings into one living map'));
assert(!openingBase.includes('>The Psychedelics Knowledge Graph<br/>brings findings into one living map'));
assert(openingBase.includes("p(f,singleActivation?500:506,singleActivation?522:532)*(nonRepeatingPulse ? .92 : 1)"));
assert(openingBase.includes('nonRepeatingPulse?514:singleActivation?516:532'));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV37" component={ProductFilmV37} durationInFrames={2944}'));

console.log('PASS: V37 sharpens the reveal, removes repetitive connection copy, and prevents the activation pulse from wrapping.');
