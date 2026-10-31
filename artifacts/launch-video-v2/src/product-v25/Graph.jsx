import React from 'react';
import {areas,broad,Node,Label,p,curve,GREEN} from '../product/shared';

export const compounds=['Ketamine','Psilocybin','MDMA','LSD','DMT'];

export const KnowledgeGraph=({frame,names,rowY,visibility,formation,nodeGrowth,labelGrowth,id='network'})=><g>
 {names.flatMap((name,i)=>areas.map((area,j)=>{
  const cell=broad.cells.find(item=>item.compound===name.toLowerCase()&&item.area===area.name);
  if(!cell?.count)return null;
  const seed=.25+((i*7+j*3)%11)/22,start=seed*(1-formation);
  return <g key={i+'-'+j} opacity={.35*visibility(i)*Math.min(1,formation*5)}>
   <defs><linearGradient id={id+i+'-'+j} gradientUnits="userSpaceOnUse" x1="620" y1={rowY(i)} x2="1220" y2={300+j*66}><stop stopColor={GREEN}/><stop offset="1" stopColor={area.color}/></linearGradient></defs>
   <path d={curve(620,rowY(i),1220,300+j*66)} fill="none" stroke={`url(#${id+i+'-'+j})`} strokeWidth={2+Math.sqrt(cell.count)*.24} strokeLinecap="round" pathLength="1" strokeDasharray={`0 ${start} ${formation} 1`}/>
  </g>;
 }))}
 {names.map((name,i)=><g key={name} opacity={visibility(i)}>
  <Node x={620} y={rowY(i)} r={24*nodeGrowth} opacity={nodeGrowth}/>
  <Label x={578} y={rowY(i)} size={56} anchor="end" opacity={labelGrowth}>{name}</Label>
 </g>)}
 {areas.map((area,j)=>{
  const areaGrowth=p(frame,214+j*3,238+j*3);
  const areaLabel=p(frame,224+j*3,250+j*3);
  return <g key={area.name}>
   <Node x={1220} y={300+j*66} r={15*areaGrowth} color={area.color} opacity={areaGrowth}/>
   <Label x={1254} y={300+j*66} size={44} opacity={areaLabel}>{area.name}</Label>
  </g>;
 })}
</g>;
