const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v54.cjs');

const film=fs.readFileSync(__dirname+'/src/product-v55/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');
const scoreScript=fs.readFileSync(__dirname+'/generate-v55-soundtrack.sh','utf8');
const soundtrack=__dirname+'/public/story/product-v55-soundtrack.wav';

assert(film.includes("staticFile('story/product-v55-soundtrack.wav')"));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV55" component={ProductFilmV55} durationInFrames={2944}'));
assert(fs.statSync(soundtrack).size>20_000_000);
assert(scoreScript.includes('Afloat Pad.caf'));
assert(scoreScript.includes('Harmonic Waves Synth Pad.caf'));
assert(scoreScript.includes('Genetic Code Layers 01.caf'));
assert(scoreScript.includes('aphaser='));
assert(scoreScript.includes('stereowiden='));
assert(!scoreScript.includes('Evolving Space Synth'));

console.log('PASS: V55 uses a warm organic-to-modular psychedelic-scientific score with spatial transformation and picture-locked cues.');
