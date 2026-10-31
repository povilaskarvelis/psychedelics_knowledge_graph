import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,AreaGraph,Node,Link,Label,p,mix,areas,broad} from './shared';

export const Access=()=>{
 const f=useCurrentFrame();
 return <Stage><Title size={110}>Build on it with your own tools</Title><Svg>
  <g opacity={.7}>{['Ketamine','Psilocybin','MDMA','LSD','Ayahuasca','DMT'].flatMap((name,i)=>areas.map((a,j)=>{
   const d=broad.cells.find(c=>c.compound===name.toLowerCase()&&c.area===a.name);if(!d?.count)return null;
   return <Link key={`${i}-${j}`} id={`api-${i}-${j}`} x1={240} y1={370+i*108} x2={805} y2={320+j*68} color={a.color} width={2+Math.sqrt(d.count)*.16} opacity={.32} progress={1}/>;
  }))}{['Ketamine','Psilocybin','MDMA','LSD','Ayahuasca','DMT'].map((name,i)=><Node key={name} x={240} y={370+i*108} r={18}/>)}{areas.map((a,j)=><Node key={a.name} x={805} y={320+j*68} r={13} color={a.color}/>)}</g>
  {['API','MCP'].map((name,i)=><g key={name}>
   <Link id={`out-${i}`} x1={805} y1={626} x2={1250} y2={440+i*350} width={6} opacity={.7} progress={p(f,18+i*16,65+i*16)}/>
   <rect x="1245" y={350+i*350} width="510" height="190" rx="30" fill="#14251e" stroke="#426a57" strokeWidth="2" opacity={p(f,40+i*15,65+i*15)}/>
   <Label x={1500} y={446+i*350} size={112} anchor="middle" opacity={p(f,45+i*15,70+i*15)}>{name}</Label>
   {Array.from({length:4},(_,k)=>{const t=((f-85-k*17)%95)/95;if(t<0)return null;const x=(1-t)**3*805+3*(1-t)**2*t*996.35+3*(1-t)*t*t*1058.65+t**3*1250;const y=mix(626,440+i*350,3*t*t-2*t*t*t);return <rect key={k} x={x-6} y={y-6} width="12" height="12" rx="3" fill="#9ae6c7" opacity={p(f,85,108)} />;})}
  </g>)}
 </Svg><div style={{position:'absolute',left:1180,right:110,top:987,textAlign:'center',fontSize:48,color:'#b2cbbd',opacity:p(f,110,140)}}>For researchers and AI</div></Stage>;
};
