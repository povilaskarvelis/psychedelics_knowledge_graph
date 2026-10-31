import React from 'react';
import {staticFile} from 'remotion';

export const C={bg:'#081315',ink:'#12312d',white:'#f2efdf',muted:'#a0b4ac',gold:'#e5bc71',mint:'#84c4ae',blue:'#8baed0',purple:'#b6a2c8',red:'#cc9588'};
export const colors=[C.gold,C.mint,C.blue,C.purple];
export const clamp=x=>Math.max(0,Math.min(1,x));
export const p=(f,a,b)=>{const t=clamp((f-a)/(b-a));return t*t*(3-2*t)};
export const out=(f,a,b)=>1-Math.pow(1-clamp((f-a)/(b-a)),3);
export const mix=(a,b,t)=>a+(b-a)*t;
export const rand=i=>{const n=Math.sin(i*127.1+3.9)*43758.5453;return n-Math.floor(n)};
export const Stage=({children,light=false})=><>
 <style>{`@font-face{font-family:Knowledge;src:url('${staticFile('landscape/space-bold.ttf')}')}`}</style>
 <svg width="1920" height="1080" viewBox="0 0 1920 1080" style={{position:'absolute',inset:0,fontFamily:'Knowledge,Arial,sans-serif',fontWeight:700}}>
  <defs>
   <radialGradient id="atmosphere"><stop stopColor="#25473e" stopOpacity=".24"/><stop offset="1" stopColor={C.bg} stopOpacity="0"/></radialGradient>
   <linearGradient id="edge"><stop stopColor={C.gold}/><stop offset="1" stopColor={C.mint}/></linearGradient>
   <filter id="glow"><feGaussianBlur stdDeviation="7"/></filter>
   <linearGradient id="scrim" x2="0" y2="1"><stop offset=".65" stopColor={C.bg}/><stop offset="1" stopColor={C.bg} stopOpacity="0"/></linearGradient>
  </defs>
  <rect width="1920" height="1080" fill={light?C.white:C.bg}/>
  {!light&&<ellipse cx="1040" cy="640" rx="1100" ry="760" fill="url(#atmosphere)"/>}
  {children}
 </svg>
</>;
export const Title=({lines,f=100,start=0,x=104,y=147,size=98,light=false,accent=-1,center=false})=><g opacity={out(f,start,start+15)} transform={`translate(0 ${mix(20,0,out(f,start,start+19))})`}>
 {lines.map((line,i)=><text key={line} x={center?960:x} y={y+i*size*1.13} fontSize={size} textAnchor={center?'middle':'start'} letterSpacing={-3.3} fill={i===accent?C.gold:light?C.ink:C.white}>{line}</text>)}
</g>;
export const Text=({x,y,children,size=38,color=C.muted,anchor='start',opacity=1})=><text x={x} y={y} fill={color} fontSize={size} opacity={opacity} textAnchor={anchor} letterSpacing={-.9}>{children}</text>;
export const Line=({d,color=C.mint,width=2,opacity=1,progress=1,dash})=><path d={d} fill="none" stroke={color} strokeWidth={width} opacity={opacity} pathLength="1" strokeDasharray={dash||1} strokeDashoffset={dash?0:1-progress} strokeLinecap="round"/>;
export const Paper=({x=0,y=0,s=1,r=0,opacity=1,accent=C.gold,highlight=false,tone=C.white})=><g transform={`translate(${x} ${y}) rotate(${r}) scale(${s})`} opacity={opacity}>
 <rect x="-73" y="-96" width="146" height="192" rx="3" fill={tone}/>
 <rect x="-52" y="-70" width="77" height="8" rx="2" fill={accent}/>
 {[0,1,2,3,4,5].map(i=><rect key={i} x="-52" y={-42+i*21} width={i%3===0?80:103} height="5" rx="2" fill={C.ink} opacity={highlight&&i===2?.8:.24}/>)}
 {highlight&&<rect x="-59" y="-7" width="118" height="22" rx="3" fill={accent} opacity=".4"/>}
</g>;
export const points=Array.from({length:150},(_,i)=>{
 const cluster=i%6,a=i*2.399963,r=70+Math.sqrt(rand(i+41))*210;
 const centers=[[420,445],[790,400],[1240,455],[530,790],[1020,800],[1510,730]];
 return {x:centers[cluster][0]+Math.cos(a)*r,y:centers[cluster][1]+Math.sin(a)*r*.75,c:colors[cluster%4],r:i%13===0?10:4+rand(i)*3};
});
export const edges=points.flatMap((n,i)=>[6,12,19].map((step,j)=>({a:i,b:(i+step)%points.length,j}))).filter(e=>Math.hypot(points[e.a].x-points[e.b].x,points[e.a].y-points[e.b].y)<420);
export const Web=({f=100,assemble=1,opacity=1,shift=0,focus=-1})=><g opacity={opacity}>
 {edges.map((e,i)=>{const a=points[e.a],b=points[e.b]; const lit=focus>=0&&(e.a%6===focus||e.b%6===focus);return <Line key={i} d={`M${a.x},${a.y} Q${(a.x+b.x)/2+shift},${(a.y+b.y)/2-20} ${b.x},${b.y}`} color={lit?C.gold:a.c} width={lit?3.4:1.3} opacity={(focus<0?.26:lit?.85:.055)*assemble} progress={clamp(assemble*1.8-i/edges.length*.7)}/>})}
 {points.map((n,i)=><circle key={i} cx={n.x} cy={n.y} r={n.r*(.8+.2*Math.sin(f*.025+i))} fill={n.c} opacity={clamp(assemble*2-rand(i))*(focus<0?1:i%6===focus?1:.12)}/>)}
</g>;
export const Chip=({x,y,w=270,label,color=C.mint,opacity=1})=><g opacity={opacity}><rect x={x} y={y} width={w} height="70" rx="35" fill={C.bg} stroke={color} strokeWidth="2"/><Text x={x+w/2} y={y+47} size={32} anchor="middle" color={C.white}>{label}</Text></g>;
export const Particle=({x,y,color=C.gold,r=6})=><g><circle cx={x} cy={y} r={r*3} fill={color} opacity=".16" filter="url(#glow)"/><circle cx={x} cy={y} r={r} fill={color}/></g>;
