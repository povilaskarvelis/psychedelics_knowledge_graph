import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Label,p,areas} from '../product/shared';
import data from '../v10-areas.json';
import {types} from './palette';
const dimensions=data[0].segments.map(s=>({key:s.key,name:s.label.split(', ')[1].split(':')[0]}));
const count=(key,type)=>Number(data.find(d=>d.segments[0].source===type)?.segments.find(s=>s.key===key)?.label.match(/: (\d+) papers/)[1]||0);
export const AreaBreakdown=()=>{
 const f=useCurrentFrame();
 return <Stage><Title size={100}>See where research is concentrated</Title><Svg>
  {types.map((t,i)=>{
   const total=dimensions.reduce((sum,a)=>sum+count(a.key,t.source),0);let offset=0;
   return <g key={t.key} opacity={p(f,3+i*7,20+i*7)}>
    <Label x={140} y={321+i*220} size={61}>{t.label}</Label>
    {dimensions.map(a=>{const n=count(a.key,t.source),start=offset;offset+=n;const grow=p(f,8+i*7,64+i*7);
     return <rect key={a.key} x={140+start/total*985*grow} y={369+i*220} width={n/total*985*grow} height="102" fill={areas.find(d=>d.name===a.name).color} stroke="#090e0d" strokeWidth="1.5"/>;
    })}
   </g>;
  })}
  {dimensions.map((a,j)=><g key={a.key} opacity={p(f,10+j*2,28+j*2)}>
   <rect x="1220" y={324+j*61} width="22" height="34" rx="4" fill={areas.find(d=>d.name===a.name).color}/>
   <Label x={1260} y={342+j*61} size={44}>{a.name}</Label>
  </g>)}
 </Svg></Stage>;
};
