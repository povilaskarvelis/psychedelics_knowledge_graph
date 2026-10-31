const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v52.cjs');

const film=fs.readFileSync(__dirname+'/src/product-v53/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');
const soundtrack=__dirname+'/public/story/product-v53-soundtrack.wav';

assert(film.includes("import {Audio} from '@remotion/media'"));
assert(film.includes("staticFile('story/product-v53-soundtrack.wav')"));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2944);
assert(root.includes('<Composition id="ProductV53" component={ProductFilmV53} durationInFrames={2944}'));
assert(fs.statSync(soundtrack).size>20_000_000);

console.log('PASS: V53 embeds the mastered soundtrack across the full Product V52 timeline.');
