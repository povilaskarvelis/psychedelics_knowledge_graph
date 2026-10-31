const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v29.cjs');

const opening=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v30/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes("import {Growth,paperOrigins}"),'The histogram should provide the source geometry for the morph');
assert(opening.includes('continuousMorph?480:256'),'The histogram should resolve into a substantial particle field');
assert(opening.includes('[144+rand(i,5)*10,190+rand(i,6)*18]'),'Histogram particles should converge into the research-area icons');
assert(opening.includes('particleIn*(continuousMorph ? .82 : .58)*(1-particleOut)'),'Particles should be absorbed as the icons finish forming');
assert(opening.includes('const origin=(i%8+Math.floor(i/8)*3)%scaleCenters.length'),'Each icon should branch into four papers distributed across the frame');
assert(opening.includes("mix(continuousMorph ? .24 : .34,1,scatter)*settle"),'Papers should grow directly out of their source icons');
assert(opening.includes('Across many research areas'));
assert(opening.includes("import {ResearchScale} from '../product-v29/ResearchScale'"),'V30 should retain the DNA correction and eight professional icons');

assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2922);
assert(root.includes('<Composition id="ProductV30" component={ProductFilmV30} durationInFrames={2922}'));

console.log('PASS: V30 continuously morphs histogram data into research areas, papers, and the graph.');
