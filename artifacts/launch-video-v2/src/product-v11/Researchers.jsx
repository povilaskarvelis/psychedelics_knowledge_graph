import React from 'react';
import data from '../v11-authors.json';
import {Label,Node,Link,p,mix,areas,BG,GREEN} from '../product/shared';
const compounds=['Ketamine','Psilocybin','MDMA','LSD','DMT','R-ketamine','S-ketamine'];
const authorY=i=>410+i*160;
const compoundY=i=>356+i*93;
const areaY=i=>335+i*66;
const focus=(f,i)=>{
 const starts=[0,88,162,236],ends=[88,162,236,Infinity];
 return p(f,starts[i],starts[i]+22)*(Number.isFinite(ends[i])?1-p(f,ends[i],ends[i]+22):1);
};
export const Researchers=({frame:f,compoundNames=compounds})=><g>
 {data.authors.flatMap((author,i)=>compoundNames.map((name,j)=>{
  const record=author.compounds.find(c=>c.name===name);if(!record)return null;
  return <Link key={i+'-'+j} id={'author-compound-'+i+'-'+j} x1={620} y1={authorY(i)} x2={850} y2={compoundY(j)} color={GREEN} width={2+Math.sqrt(record.count)*.55} progress={p(f,12+i*4,52+i*4)} opacity={mix(.09,.75,focus(f,i))}/>;
 }))}
 {data.authors.flatMap((author,i)=>compoundNames.flatMap((name,j)=>{
  const record=author.compounds.find(c=>c.name===name);if(!record)return [];
  return record.areas.map(a=>{
   const k=areas.findIndex(d=>d.name===a.name);if(k<0)return null;
   return <Link key={i+'-'+j+'-'+k} id={'author-scope-'+i+'-'+j+'-'+k} x1={1130} y1={compoundY(j)} x2={1360} y2={areaY(k)} color={areas[k].color} width={1.5+Math.sqrt(a.count)*.65} progress={p(f,35+j*2,79+j*2)} opacity={focus(f,i)*.59}/>;
  });
 }))}
 {data.authors.map((a,i)=><g key={a.key} opacity={p(f,0+i*4,18+i*4)}>
  <Label x={140} y={authorY(i)} size={46} opacity={mix(.58,1,focus(f,i))}>{a.name}</Label>
  <Node x={620} y={authorY(i)} r={mix(17,26,focus(f,i))}/>
 </g>)}
 {compoundNames.map((name,j)=><g key={name} opacity={p(f,14+j*2,37+j*2)}>
  <rect x="850" y={compoundY(j)-33} width="280" height="66" rx="25" fill={BG} stroke={GREEN} strokeWidth="2" strokeOpacity=".62"/>
  <Label x={990} y={compoundY(j)} size={44} anchor="middle">{name}</Label>
 </g>)}
 {areas.map((a,k)=><g key={a.name} opacity={p(f,40+k,63+k)}>
  <Node x={1360} y={areaY(k)} color={a.color} r={16}/>
  <Label x={1395} y={areaY(k)} size={44}>{a.name}</Label>
 </g>)}
</g>;
