import React from 'react';
import {C,nodes,edges,p,nodePose,lerp,palette,clamp} from './model';
export const Network=({f})=>{
 const appear=p(f,530,552),link=p(f,592,648),query=p(f,770,831)*(1-p(f,922,960)),fan=p(f,1280,1344)*(1-p(f,1428,1484));
 const poses=nodes.map(n=>nodePose(n,f));
 const living=p(f,1440,1495),newAlpha=p(f,1480,1585);
 return <g>
  <g opacity={p(f,277,310)*(1-p(f,396,424))}>
   {Array.from({length:22},(_,i)=>{const a=poses[i*3],b=poses[(i*13+81)%360];return <path key={i} d={`M${a.x} ${a.y} Q${(a.x+b.x)/2} ${(a.y+b.y)/2-60} ${b.x} ${b.y}`} fill="none" stroke={palette[i%4]} strokeWidth="2" strokeDasharray="8 15" opacity=".4"/>})}
  </g>
  {edges.map((e,i)=>{
   const a=poses[e.a],b=poses[e.b],same=nodes[e.a].cluster===nodes[e.b].cluster;
   const selected=e.a<72&&e.b<72,alpha=appear*link*(1-a.chart)*lerp(1,e.a%3===e.b%3?1:.03,fan)*lerp(1,selected?.25:.06,query)*(e.a>=324||e.b>=324?lerp(.08,1,newAlpha):1);
   const pulse=clamp(1-Math.abs(((f-620)*.015-i*.018)%5-2.5)*2);
   return <path key={i} d={`M${a.x} ${a.y} Q${(a.x+b.x)/2+7} ${(a.y+b.y)/2-8} ${b.x} ${b.y}`} fill="none" stroke={nodes[e.a].c} strokeWidth={same?1.3:2.1} opacity={alpha*(same?.23:.46)+alpha*pulse*.32} pathLength="1" strokeDasharray="1" strokeDashoffset={1-p(f,600+i%29,651+i%29)}/>;
  })}
  {nodes.map((n,i)=>{
   const a=poses[i],newNode=i>=324;
   const grow=newNode?lerp(.12,1,newAlpha):1;
   const alpha=appear*grow*lerp(1,i<72?1:.1,query);
   const queryW=i<72?lerp(12,260,query):12;
   const width=lerp(lerp(29,12,a.toGraph),a.chart?25:queryW,Math.max(a.chart,query));
   const height=lerp(lerp(4,n.r*1.8,a.toGraph),a.chart?20:7,Math.max(a.chart,query));
   const fill=i>=180&&a.chart>.8&&i%17===0?C.bg:n.c;
   return <rect key={i} x={a.x-width/2} y={a.y-height/2} width={width} height={height} rx={lerp(n.r,a.chart?3:2,Math.max(a.chart,query))} fill={fill} stroke={fill===C.bg?C.purple:'none'} opacity={alpha}/>;
  })}
  {/* Trace source context around a finding, while retaining the full network. */}
  <g opacity={p(f,669,706)*(1-p(f,749,779))}>
   <path d="M870 645 C635 540 470 520 315 665" fill="none" stroke={C.gold} strokeWidth="3"/>
   <rect x="167" y="588" width="254" height="248" rx="5" fill={C.paper}/>
   <text x="194" y="637" fontSize="27" fill={C.bg}>Source study</text>
   {[0,1,2,3].map(i=><rect key={i} x="195" y={674+i*34} width={i%2?160:186} height="6" rx="2" fill={C.bg} opacity=".3"/>)}
   {['Method','Population','Outcome'].map((t,i)=><g key={t}><path d={`M870 645 C1070 640 1100 ${503+i*147} 1330 ${503+i*147}`} fill="none" stroke={palette[i+1]} strokeWidth="3"/><rect x="1260" y={467+i*147} width="392" height="72" rx="36" fill={C.bg} stroke={palette[i+1]} strokeWidth="2"/><text x="1456" y={516+i*147} textAnchor="middle" fontSize="34" fill={C.paper}>{t}</text></g>)}
   <circle cx="870" cy="645" r="27" fill={C.bg} stroke={C.gold} strokeWidth="5"/>
  </g>
  {/* The three columns emerge from the graph's own records. */}
  <g opacity={query}>{['Methods','Populations','Outcomes'].map((t,i)=><text key={t} x={520+i*440} y="363" fill={palette[i]} fontSize="38" textAnchor="middle">{t}</text>)}</g>
  <g opacity={p(f,1100,1140)*(1-p(f,1252,1280))}>
   <text x="497" y="379" fill={C.paper} fontSize="39" textAnchor="middle">Accumulation</text>
   <text x="1390" y="379" fill={C.paper} fontSize="39" textAnchor="middle">Gaps & differences</text>
  </g>
  <g opacity={fan}>{['Compare methods','Track outcomes','Ask a new question'].map((t,i)=><text key={t} x={350+i*610} y="955" fill={palette[i]} fontSize="40" textAnchor="middle">{t}</text>)}</g>
  {/* Each arriving document resolves into specific new nodes, then edges. */}
  {f>1420&&f<1630&&Array.from({length:12},(_,i)=>{
   const q=p(f,1440+i*8,1500+i*8),dest=poses[324+i*3];
   const x=lerp(-90,dest.x,q),y=lerp(475+i%3*170,dest.y,q),s=lerp(1,.12,q);
   return <g key={i} opacity={1-p(q,.8,1)} transform={`translate(${x} ${y}) scale(${s}) rotate(${lerp(-12,0,q)})`}><rect x="-40" y="-53" width="80" height="106" rx="3" fill={C.paper}/>{[0,1,2].map(j=><rect key={j} x="-25" y={-22+j*21} width="50" height="5" fill={palette[j]}/>)}</g>;
  })}
 </g>
};
