import React from 'react';
import {interpolate,useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Label,p} from '../product/shared';
import data from '../v13-area-timeline.json';

// Same assignment-based denominator as Analyze's research-area composition.
// Shared cubic boundaries preserve the stack and cannot cross between years.
const left=140,right=1125,top=325,height=560;
const xs=data.years.map((_,i)=>left+i*(right-left)/(data.years.length-1));
const boundaries=Array.from({length:data.areas.length+1},(_,i)=>data.years.map(row=>{
 const total=row.counts.reduce((a,b)=>a+b,0);
 return top+height*row.counts.slice(0,i).reduce((a,b)=>a+b,0)/total;
}));
const trace=(values,reverse=false)=>{
 const indices=xs.map((_,i)=>i);if(reverse)indices.reverse();
 return indices.slice(1).map((index,k)=>{
  const prev=indices[k],mid=(xs[prev]+xs[index])/2;
  return `C${mid} ${values[prev]},${mid} ${values[index]},${xs[index]} ${values[index]}`;
 }).join(' ');
};
const ribbon=i=>`M${left} ${boundaries[i][0]} ${trace(boundaries[i])} L${right} ${boundaries[i+1].at(-1)} ${trace(boundaries[i+1],true)} Z`;
export const ResearchTrends=()=>{
 const f=useCurrentFrame();
 const progress=interpolate(f,[16,158],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
 const cursor=left+(right-left)*progress;
 return <Stage><Title size={104} opacity={p(f,12,22)*(1-p(f,281,288))}>See how research is changing</Title><Svg>
  <defs><clipPath id="v13-timeline-reveal"><rect x={left-2} y={top-2} width={4+(right-left)*progress} height={height+4}/></clipPath></defs>
  <g clipPath="url(#v13-timeline-reveal)" opacity={p(f,0,16)}>
   {data.areas.map((area,i)=><path key={area.key} d={ribbon(i)} fill={area.color} stroke="#090e0d" strokeWidth="2"/>)}
  </g>
  <line x1={cursor} x2={cursor} y1={top-9} y2={top+height+9} stroke="#e6ece8" strokeWidth="2" opacity={p(f,5,16)*(1-p(f,160,182))*.7}/>
  {[2010,2015,2020,2025].map(year=>{
   const i=year-2010,x=xs[i];
   return <g key={year} opacity={p(f,8,26)}>
    <line x1={x} x2={x} y1={top+height+12} y2={top+height+24} stroke="#526158" strokeWidth="2"/>
    <Label x={x} y={top+height+65} size={44} anchor={i===0?'start':i===15?'end':'middle'} color="#a8b7ae">{year}</Label>
   </g>;
  })}
  {data.areas.map((area,j)=><g key={area.key}>
   <rect x="1220" y={324+j*61} width="22" height="34" rx="4" fill={area.color}/>
   <Label x={1260} y={342+j*61} size={44}>{area.label}</Label>
  </g>)}
 </Svg></Stage>;
};
