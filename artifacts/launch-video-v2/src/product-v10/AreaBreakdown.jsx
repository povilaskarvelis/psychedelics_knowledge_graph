import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Label,p,mix} from '../product/shared';
import data from '../v10-areas.json';
import {types} from './palette';
const areas=data[0].segments.map(s=>({key:s.key,name:s.label.split(', ')[1].split(':')[0],color:s.color}));
const count=(key,type)=>Number(data.find(d=>d.segments[0].source===type)?.segments.find(s=>s.key===key)?.label.match(/: (\d+) papers/)[1]||0);
export const AreaBreakdown=()=>{
 const f=useCurrentFrame();
 return <Stage><Title size={100}>See where research is concentrated</Title><Svg>
  <Label x={140} y={293} size={49} color="#9eafa7">Research-area mix</Label>
  {[0,50,100].map(n=><g key={n}><path d={`M 253 ${882-n*5.2} H 1110`} stroke="#23382e"/><Label x={215} y={882-n*5.2} size={42} color="#91a49a" anchor="end">{n}%</Label></g>)}
  {types.map((t,i)=>{
   const total=areas.reduce((sum,a)=>sum+count(a.key,t.source),0);let offset=0;
   const x=260+i*320;
   return <g key={t.key}>
    {areas.map((a,j)=>{const n=count(a.key,t.source),start=offset;offset+=n;
     const grow=p(f,10+i*7,63+i*7),h=n/total*520;
     return <rect key={a.key} x={x} y={882-(start+n)/total*520*grow} width="190" height={h*grow} fill={a.color} stroke="#090e0d" strokeWidth="1.5" opacity={p(f,4,20)}/>;
    })}
    {t.key==='primary'?<><Label x={x+95} y={940} size={49} anchor="middle" color={t.color}>Primary</Label><Label x={x+95} y={990} size={49} anchor="middle" color={t.color}>studies</Label></>:<Label x={x+95} y={965} size={49} anchor="middle" color={t.color}>{t.label}</Label>}
   </g>;
  })}
  {areas.map((a,j)=><g key={a.key} opacity={p(f,10+j*2,28+j*2)} transform={`translate(${mix(22,0,p(f,10+j*2,35+j*2))} 0)`}>
   <rect x="1220" y={345+j*56} width="22" height="34" rx="4" fill={a.color}/>
   <Label x={1260} y={363+j*56} size={44}>{a.name}</Label>
  </g>)}
 </Svg></Stage>;
};
