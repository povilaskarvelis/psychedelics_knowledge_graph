const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v53.cjs');

const film=fs.readFileSync(__dirname+'/src/product-v54/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');
const scoreScript=fs.readFileSync(__dirname+'/generate-v54-soundtrack.sh','utf8');
const soundtrack=__dirname+'/public/story/product-v54-soundtrack.wav';

assert(film.includes("staticFile('story/product-v54-soundtrack.wav')"));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV54" component={ProductFilmV54} durationInFrames={2944}'));
assert(fs.statSync(soundtrack).size>20_000_000);
assert(!scoreScript.includes('Evolving Space Synth'));
assert(scoreScript.includes('adelay=14470|14470'));
assert(scoreScript.includes('adelay=47670|47670'));
assert(scoreScript.includes('adelay=81530|81530'));
assert(scoreScript.includes('adelay=92130|92130'));

console.log('PASS: V54 replaces the bright looping riff with a lower, edit-scored arrangement and explicit narrative cues.');
