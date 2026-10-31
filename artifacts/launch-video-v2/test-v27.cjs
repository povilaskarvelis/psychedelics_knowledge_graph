const fs=require('fs'),assert=require('node:assert/strict');
require('./test-v26.cjs');

const read=file=>fs.readFileSync(__dirname+'/src/product-v27/'+file,'utf8');
const opening=read('Opening.jsx');
const scale=read('ResearchScale.jsx');
const film=read('ProductFilm.jsx');
const root=fs.readFileSync(__dirname+'/src/root.jsx','utf8');

assert(opening.includes("breadthLines=['From molecular mechanisms','to public health']"));
assert(opening.includes('But the findings remain scattered<br/>across papers'));
assert(opening.includes('Now it’s all connected<br/>in a living knowledge graph'));
assert(!opening.includes('Across many areas of research'));
assert(!opening.includes('scientific domains'));

for(const label of ['Molecular','mechanisms','Brain &','experience','Clinical','outcomes','Public','health']) {
 assert(scale.includes(`'${label}'`),`Missing research-scale label: ${label}`);
}
for(const kind of ['molecule','brain','clinical','public']) {
 assert(scale.includes(`kind:'${kind}'`),`Missing research-scale icon: ${kind}`);
}

assert(opening.includes('Array.from({length:32}'),'The fragmentation scene should show a clean field of 32 papers');
assert(opening.includes('Array.from({length:3}'),'Each paper should expose three structured findings');
assert(opening.includes('targetY=300+areaIndex*66'),'Findings should travel into the ten research-area destinations');
assert(opening.includes('1-p(f,430+(i%5)*2,466+(i%5)*2)'),'Paper outlines should recede while findings detach');

assert(!film.includes('Audio'));
assert.equal([...film.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((sum,match)=>sum+Number(match[1]),0)-48,2922);
assert(root.includes('<Composition id="ProductV27" component={ProductFilmV27} durationInFrames={2922}'));

console.log('PASS: V27 uses a clean scale progression, separates scattered papers, and carries findings into the graph.');
