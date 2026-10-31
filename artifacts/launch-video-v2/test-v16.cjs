const fs=require('fs');
const assert=require('node:assert/strict');
const {Easing,interpolate}=require('remotion');
const source=fs.readFileSync(__dirname+'/src/product-v16/Opening.jsx','utf8');
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
assert.deepEqual(at(282).ys.slice(-5),[370,500,630,760,890]);
assert.deepEqual(at(578).ys.slice(0,5),[370,500,630,760,890]);
for(let f=283;f<=578;f++) {
 assert(at(f).scroll<=at(f-1).scroll,'Viewport must move only toward the top');
 assert(at(f).ys[0]>=at(f-1).ys[0],'Rows must move downward on screen as viewport moves up');
}
assert.equal(at(719).scroll,0);
assert.equal(at(719).ys[5],1020);
console.log('PASS: original order, bottom-five start, monotonic bottom-to-top viewport, first-five finish, no rewind.');
