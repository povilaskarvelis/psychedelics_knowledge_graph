export const W=1920,H=1080,DURATION=1937;
export const C={bg:'#10111c',paper:'#f4e8d1',muted:'#9e9aab',gold:'#efbe73',coral:'#eb897a',blue:'#8abecb',purple:'#b3a3de',line:'#536170'};
export const palette=[C.gold,C.blue,C.coral,C.purple];
export const clamp=t=>Math.max(0,Math.min(1,t));
export const smooth=t=>{t=clamp(t);return t*t*t*(t*(t*6-15)+10)};
export const p=(f,a,b)=>smooth((f-a)/(b-a));
export const lerp=(a,b,t)=>a+(b-a)*t;
export const rnd=i=>{const n=Math.sin(i*127.1+45.7)*43758.5453;return n-Math.floor(n)};
export const blend=(a,b,t)=>({x:lerp(a.x,b.x,t),y:lerp(a.y,b.y,t),s:lerp(a.s??1,b.s??1,t)});
export const records=Array.from({length:120},(_,i)=>{
 const a=i*2.399963,r=110+Math.sqrt(i/120)*1050;
 return {i,x:960+Math.cos(a)*r,y:690+Math.sin(a)*r*.48,z:rnd(i+99),c:palette[i%4]};
});
export const nodes=Array.from({length:360},(_,i)=>{
 const cluster=i%6,centers=[[360,515],[750,465],[1220,490],[495,805],[1030,785],[1570,715]],a=rnd(i+6)*Math.PI*2,r=Math.sqrt(rnd(i+771));
 return {i,record:Math.floor(i/3),part:i%3,cluster,c:palette[cluster%4],x:centers[cluster][0]+Math.cos(a)*r*245,y:centers[cluster][1]+Math.sin(a)*r*177,r:3.5+rnd(i+245)*3.5};
});
export const edges=nodes.flatMap((n,i)=>nodes.map((o,j)=>({a:i,b:j,d:Math.hypot(n.x-o.x,n.y-o.y)})).filter(e=>e.b>i&&e.d<220).sort((a,b)=>a.d-b.d).slice(0,3));

export const paperPose=(i,f)=>{
 const r=records[i],grow=p(f,0,135),focus=p(f,132,192),release=p(f,254,300);
 let a={x:960+(r.x-960)*lerp(2.7,1,grow),y:685+(r.y-685)*lerp(2.7,1,grow),s:lerp(1.5,.43,grow)*(0.65+r.z*.5)};
 const page={x:i===0?960:960+(r.x-960)*1.36,y:i===0?650:660+(r.y-660)*1.1,s:i===0?2.25:.33};
 a=blend(a,page,focus*(1-release));
 const grid={x:140+(i%15)*117,y:410+Math.floor(i/15)*74,s:.31};
 a=blend(a,grid,p(f,303,377));
 const gather=p(f,404,455);
 if(i%4===0) a=blend(a,{x:570+(i%5)*8,y:650+(i%7)*7,s:.52},gather);
 const reopen=p(f,493,551);
 a=blend(a,grid,reopen);
 return a;
};
export const graphPose=(n,f)=>{
 const phase=p(f,938,1010)*(1-p(f,1019,1095));
 const focusX=nodes[84].x,focusY=nodes[84].y;
 const scale=lerp(1,2.15,phase);
 return {x:960+(n.x-lerp(960,focusX,phase))*scale,y:675+(n.y-lerp(675,focusY,phase))*scale,s:scale};
};
export const nodePose=(n,f)=>{
 const paper=paperPose(n.record,Math.min(f,550));
 const source={x:paper.x,y:paper.y+(n.part-1)*38*paper.s,s:1};
 const toGraph=p(f,540+(n.record%15)*1.4,636+(n.record%15)*1.4);
 let a=blend(source,graphPose(n,f),toGraph);
 const query=p(f,770,831)*(1-p(f,922,960));
 if(n.i<72){const row=Math.floor(n.i/3),col=n.part;a=blend(a,{x:520+col*440,y:410+row*22,s:1},query)}
 else a=blend(a,{x:960+(n.x-960)*1.1,y:680+(n.y-680)*1.08,s:1},query);
 const chart=p(f,1090+(n.i%18)*1.3,1158+(n.i%18)*1.3)*(1-p(f,1252,1322));
 let target;
 if(n.i<180){const col=Math.floor(n.i/15),row=n.i%15;target={x:197+col*57,y:865-row*(14+col*1.25),s:1};}
 else {const j=n.i-180;target={x:1094+j%15*42,y:476+Math.floor(j/15)*33,s:1};}
 a=blend(a,target,chart);
 const fan=p(f,1280,1344)*(1-p(f,1428,1484)),section=n.i%3;
 a=blend(a,{x:350+section*610+(n.x-960)*.27,y:665+(n.y-660)*.65,s:.75},fan);
 return {...a,chart,query,toGraph};
};
