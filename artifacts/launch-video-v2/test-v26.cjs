const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v25.cjs');

const read=file=>fs.readFileSync(__dirname+'/src/product-v26/'+file,'utf8');
const opening=read('Opening.jsx');
const graph=read('Graph.jsx');
const film=read('ProductFilm.jsx');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

for(const copy of [
 'Psychedelic research is growing fast',
 'Across many areas of research',
 'But the findings remain scattered<br/>across papers',
 'Now it’s all connected<br/>in a living knowledge graph',
 'From study details<br/>to patterns across the field',
]) assert(opening.includes(copy),`Missing V26 copy: ${copy}`);

assert(!opening.includes('scientific domains'));
assert(!opening.includes('keeping up still means'));
assert(opening.includes('p(f,310,326)*(1-p(f,410,426))'),'The shorter fragmentation line should be held for more than three seconds');

for(const label of ['Targets','Brain','Experience','Clinical','Real-world use']) {
 assert(opening.includes(`label:'${label}'`),`Missing breadth cluster: ${label}`);
}
assert(opening.includes('const areaToTopic=[3,3,1,2,2,3,4,1,0,0]'));
assert(opening.includes('targetY=300+areaIndex*66'),'Paper clusters should split into the ten research-area destinations');
assert(graph.includes('areas.map((area,j)=>'),'The final graph should render every research-area destination');

assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2922);
assert(root.includes('<Composition id="ProductV26" component={ProductFilmV26} durationInFrames={2922}'));

console.log('PASS: V26 separates growth and breadth, holds concise problem copy, and transforms topic clusters into the graph.');
