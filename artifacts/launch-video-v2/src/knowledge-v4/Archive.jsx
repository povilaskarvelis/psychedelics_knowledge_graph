import React from 'react';
import {C,records,p,paperPose,lerp,palette} from './model';
export const Archive=({f})=>{
 const open=p(f,535,596),focus=p(f,132,192)*(1-p(f,254,300));
 return <g>
 {records.slice().sort((a,b)=>a.z-b.z).map(r=>{
  const pos=paperPose(r.i,f),appear=p(f+17,r.i*.6,r.i*.6+19),alpha=(1-open)*appear*(r.i===0?1:lerp(.83,.19,focus));
  return <g key={r.i} opacity={alpha} transform={`translate(${pos.x} ${pos.y}) rotate(${lerp((r.z-.5)*25,0,focus)}) scale(${pos.s})`}>
   <rect x="-67" y="-86" width="134" height="172" rx="3" fill={C.paper}/>
   <rect x="-48" y="-65" width="77" height="6" rx="2" fill={r.c}/>
   {[0,1,2,3,4,5].map(j=><rect key={j} x="-48" y={-39+j*19} width={j%3===0?73:95} height="4" rx="1" fill={C.bg} opacity=".27"/>)}
   {r.i===0&&['Methods','Population','Findings'].map((label,j)=><g key={label} opacity={p(f,180+j*10,196+j*10)*(1-p(f,243,258))}><rect x="-54" y={-44+j*39} width="110" height="25" fill={palette[j]}/><text x="-47" y={-27+j*39} fontSize="11" fill={C.bg}>{label}</text></g>)}
  </g>
 })}
 {/* A review gathers a subset while the rest of the archive keeps advancing. */}
 <g opacity={p(f,421,458)*(1-p(f,493,525))} transform={`translate(${lerp(820,0,p(f,419,458))} 0)`}>
  <rect x="337" y="415" width="527" height="492" rx="8" fill={C.bg} stroke={C.gold} strokeWidth="3"/>
  <text x="380" y="485" fontSize="37" fill={C.gold}>A synthesis</text>
  {[0,1,2,3].map(i=><g key={i}><path d={`M390 ${560+i*66} H800`} stroke={C.blue} strokeWidth="3" opacity=".7"/><circle cx={510+i%2*116} cy={560+i*66} r="10" fill={C.blue}/></g>)}
 </g>
 {f>395&&f<538&&Array.from({length:10},(_,i)=>{const q=p(f,415+i*5,444+i*5);return <g key={i} transform={`translate(${lerp(2000,1180+i%5*124,q)} ${540+Math.floor(i/5)*211})`} opacity={q*(1-p(f,496,536))}><rect x="-38" y="-51" width="76" height="102" rx="2" fill={C.paper}/>{[0,1,2].map(j=><path key={j} d={`M-25 ${-21+j*21} H24`} stroke={C.blue} strokeWidth="4"/>)}</g>})}
 </g>
};
