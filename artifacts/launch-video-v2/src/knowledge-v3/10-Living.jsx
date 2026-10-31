import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Text,Web,Line,Paper,Particle,C,p,mix,colors} from './shared';
export const Living=()=>{
 const f=useCurrentFrame(),impact=p(f,52,70);
 return <Stage>
  <Title lines={f<132?['New research enters.','The knowledge evolves.']:['Accessible to people.','Programmable for AI and tools.']} size={101} f={f<132?f+10:f-132} accent={1}/>
  <g transform="translate(0 80)"><Web f={f} assemble={1}/></g>
  {[0,1,2].map(i=>{const q=p(f,i*48,i*48+58);return <g key={i} opacity={1-p(q,.82,1)}><Paper x={mix(-130,530,q)} y={mix(510+i*125,650,q)} s={mix(.63,.06,q)} accent={colors[i]}/></g>})}
  {[0,1,2].map(i=>{const q=p(f,53+i*48,97+i*48);return <ellipse key={i} cx="530" cy="650" rx={q*1170} ry={q*470} fill="none" stroke={colors[i]} strokeWidth={mix(9,1,q)} opacity={Math.sin(q*Math.PI)*.65}/>})}
  <g opacity={p(f,144,184)}>
   {['Explore','Analyze','API / MCP'].map((lab,i)=><g key={lab}><rect x={360+i*410} y="899" width="350" height="90" rx="45" fill={C.bg} stroke={colors[i]} strokeWidth="3"/><Text x={535+i*410} y={957} size={39} anchor="middle" color={C.white}>{lab}</Text></g>)}
  </g>
 </Stage>
};
