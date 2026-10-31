import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Node,Label,Link,p,mix,areas,source,broad} from '../product/shared';
import history from '../story-data.json';
import {types} from './palette';
const years=history.timeline.filter(t=>t.year>=2017&&t.year<=2025);
export const PublicationTypes=()=>{
 const f=useCurrentFrame(),hist=p(f,125,176),trend=0;
 return <Stage>
 <Title size={108} opacity={1-p(f,123,150)}>Publication types</Title>
 <Title size={104} opacity={p(f,123,150)}>See how research is changing</Title><Svg>   <g opacity={1-trend}>
    {types.map((t,i)=><g key={t.key} opacity={p(f,10+i*6,32+i*6)}>
     <Label x={410+i*540} y={mix(398,304,hist)} size={mix(62,49,hist)} anchor="middle" color={t.color}>{t.label}</Label>
     <Label x={410+i*540} y={540} size={118} anchor="middle" opacity={1-hist}>{t.count.toLocaleString()}</Label>
    </g>)}
    <g opacity={1-hist}>{types.map((t,i)=>{const start=types.slice(0,i).reduce((s,t)=>s+t.count,0);return <rect key={t.key} x={140+start/21735*1635} y={660} width={t.count/21735*1635*p(f,25,72)} height="96" fill={t.color}/>;})}</g>
    <g opacity={hist}>
     {[0,500,1000,1500].map(n=><g key={n}><path d={`M 290 ${900-n/1806*475} H 1765`} stroke="#23382e" strokeWidth="1"/><Label x={248} y={900-n/1806*475} size={42} color="#91a49a" anchor="end">{n.toLocaleString()}</Label></g>)}
     {years.map((row,i)=>{let total=0;return <g key={row.year}>{types.map(t=>{const base=total;total+=row[t.key];const q=p(f,172+i*2,218+i*2);return <rect key={t.key} x={322+i*165} y={900-(base+row[t.key])*475/1806*q} width="112" height={row[t.key]*475/1806*q} fill={t.color}/>;})}<Label x={378+i*165} y={963} size={44} anchor="middle">{row.year}</Label></g>;})}
    </g>
   </g>
</Svg></Stage>;
};
