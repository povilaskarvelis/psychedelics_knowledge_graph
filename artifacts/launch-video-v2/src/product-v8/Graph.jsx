import React from 'react';
import {areas,broad,compounds,Node,Label,Link,p,mix} from '../product/shared';

// The same geometry is used at the end of the opening and the start of the drill-down.
export const Overview=({frame=1000,reveal=0,selection=0})=><g>
 {compounds.flatMap((name,i)=>areas.map((a,j)=>{
  const c=broad.cells.find(c=>c.compound===name.toLowerCase()&&c.area===a.name);
  return c?.count?<Link key={`${i}-${j}`} id={`overview-${i}-${j}`} x1={620} y1={410+i*210} x2={1220} y2={300+j*66} color={a.color} width={2+Math.sqrt(c.count)*.24} progress={p(frame,reveal+i*3+j,reveal+45+i*3+j)} opacity={j===0?mix(.35,.85,selection):.35*(1-selection)}/>:null;
 }))}
 {compounds.map((name,i)=><g key={name}><Node x={620} y={410+i*210} r={24}/><Label x={578} y={410+i*210} size={56} anchor="end">{name}</Label></g>)}
 {areas.map((a,j)=><g key={a.name} opacity={p(frame,reveal+j,reveal+20+j)*(j?1-selection:1)}><Node x={1220} y={300+j*66} r={j===0?mix(15,26,selection):15} color={a.color}/><Label x={1254} y={300+j*66} size={44}>{a.name}</Label></g>)}
</g>;
