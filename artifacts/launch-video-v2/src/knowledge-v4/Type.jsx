import React from 'react';
import {C,p,lerp} from './model';
const beats=[
 [0,132,['Research keeps','accelerating'],126],
 [132,269,['But findings arrive','paper by paper'],112],
 [269,403,['Connections between findings','remain implicit'],99],
 [403,535,['Synthesis has to keep','rebuilding the picture'],110],
 [535,668,['What if connections became','part of the scientific record?'],99],
 [668,772,['AI helps build','a living knowledge graph'],112],
 [772,941,['Search across studies','by the details that matter'],105],
 [941,1100,['Follow one finding.','Then change your scale.'],107],
 [1100,1274,['Reveal patterns,','differences and gaps'],114],
 [1274,1433,['Make synthesis reusable','across new questions'],108],
 [1433,1600,['New research arrives.','The picture evolves.'],114],
 [1600,1775,['Knowledge that people','and AI can build on'],112],
 [1775,1940,['Already taking shape in','Psychedelics Knowledge Graph'],91],
 [1940,2130,['A living memory','for cumulative science'],116],
];
export const Typography=({f})=><g>
 {beats.map(([a,b,lines,size],idx)=>{
  if(f<a-8||f>b+10)return null;
  const enter=p(f,a-8,a+13),exit=p(f,b-12,b+5),opacity=enter*(1-exit);
  const pivot=idx===4?1-p(f,572,623):0;
  return <g key={a} opacity={opacity} transform={`translate(${lerp(54,0,enter)-exit*35} 0)`}>
   {lines.map((t,i)=><g key={t}><text x={lerp(104,178,pivot)} y={148+i*size*1.1+lerp(35,0,p(f,a-8+i*5,a+13+i*5))+pivot*300} fontSize={size+pivot*9} letterSpacing={-3.5} fill={i===1?C.gold:C.paper}>{t}</text></g>)}
  </g>;
 })}
</g>;
