const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v32.cjs');

const opening=fs.readFileSync(__dirname+'/src/product-v30/Opening.jsx','utf8');
const graph=fs.readFileSync(__dirname+'/src/product-v26/Graph.jsx','utf8');
const wrapper=fs.readFileSync(__dirname+'/src/product-v33/Opening.jsx','utf8');
const film=fs.readFileSync(__dirname+'/src/product-v33/ProductFilm.jsx','utf8');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes('solutionReveal?448+rand(index,4)*10'));
assert(opening.includes('solutionReveal?interpolate(f,[478,494,502],[0,1.16,1],ease)'));
assert(opening.includes('strokeDasharray=".075 .925"'));
assert(opening.includes('The Psychedelics Knowledge Graph<br/>connects findings across papers'));
assert(opening.includes('From study details to patterns<br/>across the field'));
assert(graph.includes('areaNodeStart=456'));
assert(wrapper.includes('<PreviousOpening balancedTitles wideTitles solutionReveal/>'));
assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2962);
assert(root.includes('<Composition id="ProductV33" component={ProductFilmV33} durationInFrames={2962}'));

console.log('PASS: V33 punctuates the problem, snaps the graph together, and names the product as the solution.');
