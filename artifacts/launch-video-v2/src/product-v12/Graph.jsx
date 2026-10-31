import React from 'react';
import {areas,broad,Node,Label,p,mix,curve,GREEN} from '../product/shared';
export const compounds=['Ketamine','Psilocybin','MDMA','LSD','DMT'];
export const overviewY=i=>370+i*130;
export const graphEdges=compounds.flatMap((name,i)=>areas.map((area,j)=>({i,j,name,area,count:broad.cells.find(c=>c.compound===name.toLowerCase()&&c.area===area.name)?.count||0}))).filter(e=>e.count>0);
export const KnowledgeGraph=({names=compounds,rowY=overviewY,visibility=()=>1,formation=1,nodeGrowth=1,labelGrowth=1,id='network'})=><g>
 {names.flatMap((name,i)=>areas.map((a,j)=>{
  const c=broad.cells.find(c=>c.compound===name.toLowerCase()&&c.area===a.name);if(!c?.count)return null;
  const seed=.25+((i*7+j*3)%11)/22,start=seed*(1-formation);
  return <g key={i+'-'+j} opacity={.35*visibility(i)*Math.min(1,formation*5)}>
   <defs><linearGradient id={id+i+'-'+j} gradientUnits="userSpaceOnUse" x1="620" y1={rowY(i)} x2="1220" y2={300+j*66}><stop stopColor={GREEN}/><stop offset="1" stopColor={a.color}/></linearGradient></defs>
   <path d={curve(620,rowY(i),1220,300+j*66)} fill="none" stroke={`url(#${id+i+'-'+j})`} strokeWidth={2+Math.sqrt(c.count)*.24} strokeLinecap="round" pathLength="1" strokeDasharray={`0 ${start} ${formation} 1`}/>
  </g>;
 }))}
 {names.map((name,i)=><g key={name} opacity={visibility(i)}>
  <Node x={620} y={rowY(i)} r={24*nodeGrowth} opacity={nodeGrowth}/>
  <Label x={578} y={rowY(i)} size={56} anchor="end" opacity={labelGrowth}>{name}</Label>
 </g>)}
 {areas.map((a,j)=><g key={a.name} opacity={nodeGrowth}>
  <Node x={1220} y={300+j*66} r={15*nodeGrowth} color={a.color}/>
  <Label x={1254} y={300+j*66} size={44} opacity={labelGrowth}>{a.name}</Label>
 </g>)}
</g>;
