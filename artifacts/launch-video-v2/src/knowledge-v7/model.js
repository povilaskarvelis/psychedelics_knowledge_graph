export const C={bg:'#10131c',paper:'#f3e9d6',gold:'#eac17e',blue:'#86b8c8',coral:'#df9186',purple:'#b4a6d0',muted:'#959ba7'};
export const colors=[C.gold,C.blue,C.coral,C.purple];
export const clamp=t=>Math.max(0,Math.min(1,t));
export const p=(f,a,b)=>{const t=clamp((f-a)/(b-a));return t*t*t*(t*(t*6-15)+10)};
export const mix=(a,b,t)=>a+(b-a)*t;
export const rnd=i=>{const n=Math.sin(i*127.1+45.7)*43758.5453;return n-Math.floor(n)};
export const blend=(a,b,t)=>({x:mix(a.x,b.x,t),y:mix(a.y,b.y,t),s:mix(a.s??1,b.s??1,t)});
export const band=(f,a,b,c,d)=>p(f,a,b)*(1-p(f,c,d));
export const papers=Array.from({length:120},(_,i)=>({i,color:colors[i%4]}));
export const paperPose=(i,f)=>{
 const a=i*2.39996,r=90+Math.sqrt((i+1)/120)*1020,z=1-p(f,0,128);
 let pose={x:960+Math.cos(a)*r*mix(1,2.7,z),y:650+Math.sin(a)*r*.48*mix(1,2.7,z),s:mix(.42,1.55,z)};
 const grid={x:160+i%15*114,y:406+Math.floor(i/15)*74,s:.35};
 pose=blend(pose,grid,p(f,82,162));
 const time={x:170+(i%30)*54,y:422+Math.floor(i/30)*42,s:.18};
 pose=blend(pose,time,p(f,514,570));
 return pose;
};
export const nodes=Array.from({length:360},(_,i)=>{
 const group=i%6,centers=[[310,510],[705,465],[1150,495],[535,815],[1050,795],[1590,705]],a=rnd(i+6)*Math.PI*2,r=Math.sqrt(rnd(i+771));
 return {i,group,c:colors[group%4],x:centers[group][0]+Math.cos(a)*r*205,y:centers[group][1]+Math.sin(a)*r*145};
});
export const edges=nodes.flatMap((n,i)=>nodes.map((o,j)=>({a:i,b:j,d:Math.hypot(n.x-o.x,n.y-o.y)})).filter(e=>e.b>i&&e.d<210).sort((a,b)=>a.d-b.d).slice(0,3));
export const pose=(n,f)=>{
 const page=paperPose(Math.floor(n.i/3),797),assemble=p(f,800+(n.i%15),937+(n.i%15));
 const source=n.i<80?{x:305+(n.i%10)*30+Math.floor(n.i/40)*560,y:776+Math.floor((n.i%40)/10)*33,s:1}:{x:page.x,y:page.y+(n.i%3-1)*11,s:1};
 let a=blend(source,{x:n.x,y:n.y,s:1},assemble);
 a.y-=Math.sin(assemble*Math.PI)*(70+n.i%7*13);
 const foundation=p(f,1100,1190)*(1-p(f,2630,2720));
 a=blend(a,{x:475+(n.x-960)*.4,y:680+(n.y-650)*.88,s:.85},foundation);
 return {...a,assemble,foundation};
};

// Each projected point retains the identity and colour of a finding in the persistent graph.
export const projection=(i,f)=>{
 const node=nodes[(i*7)%324],source=pose(node,f),j=i%90,col=j%15,row=Math.floor(j/15),lower=i>=90;
 const reframe=p(f,1650,1740),second=p(f,1880,1970),growth=p(f,2150,2360);
 const initial={x:1036+col*49,y:lower?768+row*29:642-row*(17+(col%5)*4),s:1};
 const context={x:lower?1036+((col+row*3)%15)*49:1036+((col*7+row*3)%15)*49,y:lower?768+row*29:461+((row*5+col)%9)*21,s:1};
 const overTime={x:1036+col*49,y:lower?768+row*29:639-row*(14+col*1.25),s:1};
 let target=blend(initial,context,reframe);
 target=blend(target,overTime,second);
 if(!lower)target.y-=growth*(row/5)*(10+col*1.6);
 const access=p(f,2420,2510);
 if(lower)target=blend(target,{x:1110+(j%3)*246,y:798+Math.floor(j/3)*16,s:1},access);
 const travel=p(f,1160+(i%15)*2,1240+(i%15)*2);
 const position=blend(source,target,travel);
 const originallyMissing=lower&&col>9&&row>2;
 const filled=(originallyMissing?mix(.06,.85,growth):1)*(lower&&j>=36?1-access:1);
 return {...position,c:node.c,source,travel,filled,lower,access};
};
