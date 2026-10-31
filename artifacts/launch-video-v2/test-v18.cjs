const fs=require('fs');
const assert=require('node:assert/strict');
const {Easing,interpolate}=require('remotion');
const source=fs.readFileSync(__dirname+'/src/product-v18/Opening.jsx','utf8');
const broad=require('./src/v6-data.json');
const compounds=['Ketamine','Psilocybin','MDMA','LSD','DMT'];
const areas=broad.cells.slice(0,10).map(c=>({name:c.area,color:c.color}));
const ease={extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:Easing.bezier(.22,1,.36,1)};
const declarations=source.slice(source.indexOf('const remaining='),source.indexOf('const smooth='));
const model=new Function('broad','compounds','areas',declarations+'return {names,bottomStart,graphEdges};')(broad,compounds,areas);
assert.deepEqual(model.names,[...compounds,...broad.rows.map(r=>r.name).filter(n=>![...compounds,'(2R,6R)-hydroxynorketamine'].includes(n))]);
assert.deepEqual(model.names.slice(-5),['Methylone','Dextromethorphan','Nitrous oxide','DOM','Noribogaine']);
assert(model.graphEdges.every(edge=>edge.i>=model.bottomStart && edge.i<model.names.length));
const positionCode=source.slice(source.indexOf('const scroll='),source.indexOf('const visible='));
const positions=new Function('f','bottomStart','interpolate','ease','Easing',positionCode+'return {scroll,ys:Array.from({length:23},(_,i)=>rowY(i))};');
const at=f=>positions(f,model.bottomStart,interpolate,ease,Easing);
assert.deepEqual(at(308).ys.slice(-5),[370,500,630,760,890]);
assert.deepEqual(at(446).ys.slice(0,5),[370,500,630,760,890]);
for(let f=309;f<=446;f++) {
 assert(at(f).scroll<=at(f-1).scroll,'Viewport must move only toward the top');
 assert(at(f).ys[0]>=at(f-1).ys[0],'Rows must move downward on screen as viewport moves up');
}
assert.equal(at(511).scroll,0);
assert.equal(at(511).ys[5],1020);
console.log('PASS: original order, bottom-five start, monotonic bottom-to-top viewport, first-five finish, no rewind.');

const opening=source;
assert(opening.includes("const highest=Math.floor(Math.log10(Math.max(1,Math.floor(value))))"));
assert(!opening.includes('[4,3,2,1,0].map'));
const counterExpression=opening.match(/value=\{(interpolate\(f,\[73,89,109,133,158,175\].*?\))\}/)[1];
const countAt=new Function('f','interpolate','ease','Easing','return '+counterExpression);
for(const [frame,digits] of [[81,1],[101,2],[122,3],[148,4],[175,5]]) {
 const count=Math.floor(countAt(frame,interpolate,ease,Easing));
 assert.equal(String(count).length,digits);
 assert(count>=1&&count<=21000);
}
assert.equal(countAt(175,interpolate,ease,Easing),21000);
const movie=fs.readFileSync(__dirname+'/src/product-v18/ProductFilm.jsx','utf8');
assert(movie.indexOf('<Access/>')<movie.indexOf('<Living/>'));
assert.equal([...movie.matchAll(/durationInFrames=\{(\d+)\}/g)].reduce((n,m)=>n+Number(m[1]),0)-4*12,2870);
const speed=f=>at(f).scroll-at(f+1).scroll;
assert(speed(377)>speed(309)*5 && speed(360)>speed(444)*5);
console.log('PASS: 1/2/3/4/5-digit progression; faster eased scroll; tools before updating; 2870-frame cut.');

assert(opening.includes('Organize and connect the research'));
assert(opening.includes('Explore the connections'));
assert(opening.includes('Psychedelic science is growing fast'));
assert(opening.includes('From molecules to minds and society'));
assert(opening.includes("p(f,489,507)"));
assert(opening.includes("p(f,458,469)"));
assert.equal(458-446,12,'Only 0.4 seconds from scroll settle to cursor appearance');
assert(opening.includes(">+</div>"));
console.log('PASS: problem/solution/exploration copy, rounded 21,000+ total, and short first-click pause.');
