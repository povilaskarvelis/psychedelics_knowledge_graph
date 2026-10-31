import React from 'react';
import {C,records,p,paperPose,lerp,palette} from './model';
export const Archive=({f})=>{
 const open=p(f,541,593),focus=p(f,132,174)*(1-p(f,247,281));
 const review=p(f,410,444)*(1-p(f,506,538));
 const paper=(r)=>{
  const pos=paperPose(r.i,f),prior=paperPose(r.i,Math.max(0,f-4));
  const appear=p(f,-16,30),backgroundDim=r.i<12?1:lerp(1,.12,review);
  const alpha=(1-open)*appear*backgroundDim*(r.i===0?1:lerp(.83,.19,focus));
  return <g key={r.i} opacity={alpha}>
   {f<140&&<path d={`M${prior.x} ${prior.y} L${pos.x} ${pos.y}`} fill="none" stroke={r.c} strokeWidth="5" opacity={.37*(1-p(f,85,140))}/>}
   <g transform={`translate(${pos.x} ${pos.y}) rotate(${lerp((r.z-.5)*25,0,focus)}) scale(${pos.s})`}>
   <rect x="-67" y="-86" width="134" height="172" rx="3" fill={C.paper}/>
   <rect x="-48" y="-65" width="77" height="6" rx="2" fill={r.c}/>
   {[0,1,2,3,4,5].map(j=><rect key={j} x="-48" y={-39+j*19} width={j%3===0?73:95} height="4" rx="1" fill={C.bg} opacity=".27"/>)}
   </g>
  </g>
 };
 return <g>
 {records.filter(r=>r.i>=12).sort((a,b)=>a.z-b.z).map(paper)}
 {/* Review documents cover the archive, and their selected source papers remain visible inside. */}
 <g opacity={p(f,420,453)*(1-p(f,500,535))}>
  {['REVIEW','META-ANALYSIS'].map((label,j)=><g key={label}>
   <rect x={290+j*505} y="472" width="418" height="416" rx="12" fill={C.bg} stroke={j?C.blue:C.gold} strokeWidth="3"/>
   <rect x={315+j*505} y="497" width="368" height="10" rx="5" fill={j?C.blue:C.gold}/>
   <text x={325+j*505} y="577" fontSize={j?39:47} fill={C.paper}>{label}</text>
  </g>)}
 </g>
 {records.filter(r=>r.i<12).sort((a,b)=>a.z-b.z).map(paper)}
 {f>434&&f<540&&Array.from({length:8},(_,i)=>{
  const q=p(f,445+i*6,481+i*6),x=lerp(1980,1370+i%2*190,q),y=525+Math.floor(i/2)*104;
  return <g key={i} transform={`translate(${x} ${y})`} opacity={q*(1-p(f,510,540))}>
   <rect x="-37" y="-47" width="74" height="94" rx="2" fill={C.paper}/>
   {[0,1,2].map(j=><path key={j} d={`M-24 ${-18+j*20} H24`} stroke={palette[(i+j)%4]} strokeWidth="4"/>)}
  </g>;
 })}
 </g>
};
