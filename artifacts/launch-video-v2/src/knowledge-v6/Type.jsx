import React from 'react';
import {C,p,lerp} from './model';
const beats=[
 [0,132,['Research output','is outgrowing our capacity','to make sense of it'],104],
 [132,269,['Findings are still stored','in separate papers'],108],
 [269,403,['Connections among findings','remain buried in the text'],100],
 [403,535,['Knowledge synthesis takes time','as new papers keep coming'],98],
 [535,668,['What if connections became','part of the scientific record?'],99],
 [668,772,['AI can now help build','a living knowledge graph'],108],
 [772,941,['You could navigate research','through its connections'],103],
 [941,1100,['Zoom into one finding','Zoom out across studies'],106],
 [1100,1274,['See patterns, differences','and gaps in the research'],108],
 [1274,1433,['Use the same graph','to investigate new questions'],108],
 [1433,1600,['New findings can become','part of the same map'],108],
 [1600,1775,['Researchers and AI tools','can use the same knowledge'],106],
 [1775,1940,['Across disciplines','and new questions'],116],
 [1940,2130,['A living memory','for cumulative science'],116],
];
export const Typography=({f})=><g>
 {beats.map(([a,b,lines,size],idx)=>{
  if(f<a-8||f>b+10)return null;
  const enter=p(f,a-8,a+13),exit=p(f,b-12,b+5),opacity=enter*(1-exit);
  const pivot=a===535?1-p(f,572,623):0;
  const intro=a<132,centerShift=intro?1-p(f,95,132):0;
  return <g key={a} opacity={opacity} transform={`translate(${lerp(54,0,enter)-exit*35} 0)`}>
   {lines.map((t,i)=><g key={t}><text x={intro?960:lerp(104,178,pivot)} y={148+i*size*1.1+lerp(35,0,p(f,a-8+i*5,a+13+i*5))+pivot*300+centerShift*185} textAnchor={intro?'middle':'start'} fontSize={size+pivot*9} fontStyle={intro&&i===2?'italic':'normal'} letterSpacing={intro?-4:-3.5} fill={i===(intro?2:1)?C.gold:C.paper}>{t}</text></g>)}
  </g>;
 })}
</g>;
