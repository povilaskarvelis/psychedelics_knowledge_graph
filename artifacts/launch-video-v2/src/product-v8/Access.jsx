import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Node,Link,Label,p,mix,areas,broad,curve} from '../product/shared';
const names=['Ketamine','Psilocybin','MDMA','LSD','Ayahuasca','DMT'];
const point=(x1,y1,x2,y2,t)=>({x:(1-t)**3*x1+3*(1-t)**2*t*mix(x1,x2,.43)+3*(1-t)*t*t*mix(x1,x2,.57)+t**3*x2,y:mix(y1,y2,3*t*t-2*t*t*t)});
export const Access=()=>{
 const f=useCurrentFrame();
 return <Stage><Title size={108}>Connect the graph to your tools</Title><Svg>
  <rect x="140" y="270" width="850" height="718" rx="28" fill="#0d1511" stroke="#345144" strokeWidth="2"/>
  <Label x={565} y={336} size={54} anchor="middle">Knowledge graph</Label>
  {names.flatMap((name,i)=>areas.map((a,j)=>{const d=broad.cells.find(c=>c.compound===name.toLowerCase()&&c.area===a.name);if(!d?.count)return null;return <Link key={`${i}-${j}`} id={`access-v8-${i}-${j}`} x1={240} y1={418+i*98} x2={725} y2={400+j*57} color={a.color} width={2+Math.sqrt(d.count)*.16} opacity={.32}/>;}))}
  {areas.map((a,j)=><path key={a.name} d={curve(725,400+j*57,990,635)} stroke={a.color} strokeWidth="1.5" fill="none" opacity={p(f,18,52)*.32}/>)}
  {names.map((name,i)=><Node key={name} x={240} y={418+i*98} r={18}/>)}{areas.map((a,j)=><Node key={a.name} x={725} y={400+j*57} r={13} color={a.color}/>)}
  {['API','MCP'].map((name,i)=><g key={name}>
   <Link id={`port-v8-${i}`} x1={990} y1={635} x2={1270} y2={468+i*350} width={6} opacity={.7} progress={p(f,44+i*12,80+i*12)}/>
   <rect x="1265" y={373+i*350} width="480" height="190" rx="30" fill="#14251e" stroke="#426a57" strokeWidth="2" opacity={p(f,62+i*14,85+i*14)}/>
   <Label x={1505} y={474+i*350} size={112} anchor="middle" opacity={p(f,68+i*14,88+i*14)}>{name}</Label>
   {Array.from({length:5},(_,k)=>{const t=((f-108-k*19)%105)/105;if(t<0)return null;const pt=point(990,635,1270,468+i*350,t);return <rect key={k} x={pt.x-6} y={pt.y-6} width="12" height="12" rx="3" fill="#9ae6c7" opacity={p(f,100,120)}/>;})}
  </g>)}
  <Node x={990} y={635} r={14} opacity={p(f,20,50)}/>
 </Svg></Stage>;
};
