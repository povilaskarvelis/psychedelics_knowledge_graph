import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Paper,Text,Line,Chip,C,p,mix,colors,Particle} from './shared';
export const Structure=()=>{
 const f=useCurrentFrame(),move=p(f,20,76),audit=p(f,178,217);
 const labs=['Finding','Method','Population','Outcome'];
 return <Stage>
  <Title lines={f<133?['AI helps turn papers','into structured knowledge']:['Keep the source.','Make the structure inspectable.']} size={96} f={f<133?f+10:f-133} accent={1}/>
  <Paper x={340} y={650} s={2.35} highlight accent={C.gold}/>
  {labs.map((lab,i)=>{const q=p(f,23+i*11,69+i*11),y=410+i*145;return <g key={lab}>
   <Line d={`M475 ${610+i*26} C760 ${610+i*26} 740 ${y+35} 1000 ${y+35}`} color={colors[i]} width={3} progress={q} opacity={.7}/>
   <Particle x={mix(475,1000,q)} y={mix(610+i*26,y+35,q)} color={colors[i]}/>
   <Chip x={1000} y={y} w={440} label={lab} color={colors[i]} opacity={q}/>
   <Line d={`M1440 ${y+35} Q1600 ${y+35} 1625 647`} color={colors[i]} width={2} progress={p(f,86+i*7,129+i*7)} opacity={.5}/>
  </g>})}
  <g opacity={p(f,102,135)}><circle cx="1625" cy="647" r="42" fill={C.ink} stroke={C.gold} strokeWidth="4"/><circle cx="1625" cy="647" r="15" fill={C.gold}/></g>
  <g opacity={audit}>
   <Line d="M1625 693 C1640 1050 370 1030 340 894" color={C.gold} width={3} progress={audit}/>
   <rect x="642" y="909" width="628" height="69" rx="34" fill={C.bg}/><Text x={956} y={957} anchor="middle" size={38} color={C.gold}>Traceable. Auditable. Correctable.</Text>
  </g>
 </Stage>
};
