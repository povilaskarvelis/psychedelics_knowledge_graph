import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Label,p,source,areas} from '../product/shared';
const trends=['Safety','Molecular effects','Real-world use'];
export const ResearchTrends=()=>{
 const f=useCurrentFrame()+350;
 return <Stage><Title size={104}>See how research is changing</Title><Svg>   <g opacity={1}>
    <Label x={1380} y={320} size={42} anchor="middle" color="#98a99f">2017–2021</Label><Label x={1640} y={320} size={42} anchor="middle">2022–2026</Label>
    {trends.map((name,i)=>{
     const d=source.momentum.find(m=>m.label===name),color=areas.find(a=>a.name===name).color;
     const points=d.svg.match(/points="([^"]+)"/)[1].split(' ').map(v=>v.split(',').map(Number));
     const [latest,prior]=d.summary.match(/[\d,]+/g).map(v=>Number(v.replaceAll(',',''))),y=439+i*208;
     return <g key={name}><rect x="139" y={y-78} width="1635" height="178" rx="24" fill="#101816" stroke="#253b32"/><Label x={178} y={y} size={48}>{name}</Label><rect x="1018" y={y-58} width="280" height="116" fill={color} opacity=".06"/><path d={`M1018 ${y-58} V${y+58}`} stroke="#657b6c" strokeDasharray="5 7"/><polyline points={points.map(([x,v])=>`${738+x*4.24},${y-63+v*4.2}`).join(' ')} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round" pathLength="1" strokeDasharray="1" strokeDashoffset={1-p(f,367+i*8,420+i*8)}/><Label x={1380} y={y} size={56} anchor="middle" color="#93a39a">{prior.toLocaleString()}</Label><Label x={1640} y={y} size={68} anchor="middle" color={color}>{latest.toLocaleString()}</Label></g>;
    })}
   </g>
</Svg></Stage>;
};
