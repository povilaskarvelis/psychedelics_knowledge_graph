const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v24.cjs');

const read=file=>fs.readFileSync(__dirname+'/src/product-v25/'+file,'utf8');
const opening=read('Opening.jsx');
const drilldown=read('Drilldown.jsx');
const graph=read('Graph.jsx');
const film=read('ProductFilm.jsx');
const broad=require('./src/v6-data.json');

for(const line of [
 'Psychedelic research is growing fast',
 'Across many scientific domains',
 'But keeping up still means',
 'piecing together paper after paper',
 'Now, it comes together',
 'in a living knowledge graph',
 'From study details',
 'to patterns across the field',
]) assert(opening.includes(line),`Missing opening copy: ${line}`);

assert(!opening.includes('We’ve organized it'));
assert(!opening.includes('Psychedelic science'));
assert(drilldown.includes('From study details<br/>to patterns across the field'));
assert(drilldown.includes('See how the studies were done'));

assert(graph.includes('areas.map((area,j)=>'),'Every configured research area should be rendered as a destination');
assert.deepEqual(broad.cells.slice(0,10).map(cell=>cell.area),['Conditions','Safety','Cognition','Behavior','Subjective effects','Treatment context','Real-world use','Brain regions','Molecular effects','Targets']);
assert(graph.includes('p(frame,214+j*3,238+j*3)'),'Research-area nodes should emerge in a readable stagger');
assert(graph.includes('p(frame,224+j*3,250+j*3)'),'Research-area labels should follow their nodes');
assert(opening.includes('i%5===0?1:.08+.84*rand(i,9)'),'A regular stream of papers should reach named research areas');
assert(opening.includes('245+j*2,255+j*2'),'Research-area arrival pulses should be staggered');

assert(!film.includes('Audio'));
assert(film.indexOf('<Access/>')<film.indexOf('<Living/>'),'Tool access should precede the living-update close');
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((n,m)=>n+Number(m[1]),0)-48,2794);

console.log('PASS: V25 opening narrative, breadth animation, continuity, silence, and duration verified.');
