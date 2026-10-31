import React from 'react';
import {Stage,Svg,Label,p} from '../product/shared';
import history from '../story-data.json';

// Observed annual publications, not cumulative totals or forecast values.
export const years=history.timeline.filter(row=>row.year>=2000&&row.year<=2025);
const baseline=850,scale=510/2000;
const x=i=>965+i*31;
const total=years.reduce((sum,row)=>sum+row.total,0);
const rand=(i,s)=>{const value=Math.sin(i*127.1+s*311.7)*43758.5453;return value-Math.floor(value);};
export const paperOrigins=Array.from({length:560},(_,i)=>{
 const rank=(i+.5)/560*total;let accumulated=0;
 const index=years.findIndex(row=>{accumulated+=row.total;return accumulated>=rank;});
 return {x:x(index)+3+rand(i,1)*16,y:baseline-rand(i,3)*years[index].total*scale};
});
export const Growth=({frame:f})=><Svg>
 <g opacity={p(f,8,22)*(1-p(f,165,187))}>
  <Label x={965} y={275} size={54}>Papers per year</Label>
  {[0,1000,2000].map(n=><g key={n}>
   <line x1={955} x2={1762} y1={baseline-n*scale} y2={baseline-n*scale} stroke="#263c33" strokeWidth="1.5"/>
   <Label x={923} y={baseline-n*scale} size={40} color="#91a99d" anchor="end">{n.toLocaleString()}</Label>
  </g>)}
  {years.map((row,i)=>{
   const height=row.total*scale*p(f,20+i*2.7,48+i*2.7);
   return <rect key={row.year} x={x(i)} y={baseline-height} width="22" height={height} rx="3" fill="#69a196"/>;
  })}
  {[2000,2010,2025].map(year=><Label key={year} x={x(year-2000)+11} y={914} size={44} anchor={year===2000?'start':year===2025?'end':'middle'} color="#a8b7ae">{year}</Label>)}
 </g>
</Svg>;
