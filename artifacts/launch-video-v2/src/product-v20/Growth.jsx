import React from 'react';
import {Svg,Label,p} from '../product/shared';
import history from '../story-data.json';

// Observed annual counts, with a separately identified full-year projection.
export const years=history.timeline.filter(row=>row.year>=2000&&row.year<=2026);
const first=years.find(row=>row.year===2021).total;
const latest=years.find(row=>row.year===2025).total;
export const projected2026=Math.round(latest*Math.pow(latest/first,1/4)/100)*100;
const baseline=850,scale=510/2000;
const x=i=>965+i*30;
const total=years.reduce((sum,row)=>sum+row.total,0);
const rand=(i,s)=>{const value=Math.sin(i*127.1+s*311.7)*43758.5453;return value-Math.floor(value);};
export const paperOrigins=Array.from({length:560},(_,i)=>{
 const rank=(i+.5)/560*total;let accumulated=0;
 const index=years.findIndex(row=>{accumulated+=row.total;return accumulated>=rank;});
 return {x:x(index)+3+rand(i,1)*16,y:baseline-rand(i,3)*years[index].total*scale};
});
export const Growth=({frame:f})=><Svg>
 <defs><pattern id="current-year-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><rect width="3" height="7" fill="#69a196"/></pattern></defs>
 <g opacity={p(f,8,22)*(1-p(f,165,187))}>
  {years.map((row,i)=>{
   const reveal=p(f,20+i*2.7,48+i*2.7),observedHeight=row.total*scale*reveal;
   const height=(row.year===2026?projected2026:row.total)*scale*reveal;
   return <g key={row.year}>
    <rect x={x(i)} y={baseline-observedHeight} width="22" height={observedHeight} rx="3" fill="#69a196"/>
    {row.year===2026?<rect x={x(i)} y={baseline-height} width="22" height={Math.max(0,height-observedHeight)} fill="url(#current-year-hatch)" stroke="#69a196" strokeWidth="1.5"/>:null}
    {[2000,2026].includes(row.year)?<Label x={x(i)+(row.year===2026?22:11)} y={baseline-height-34} size={44} anchor={row.year===2026?'end':'middle'} color="#b3c5bb" opacity={p(f,112,129)}>{row.year===2026?'~'+projected2026.toLocaleString():row.total.toLocaleString()}</Label>:null}
   </g>;
  })}
  {[2000,2010,2026].map(year=><Label key={year} x={x(year-2000)+(year===2026?22:11)} y={914} size={44} anchor={year===2000?'start':year===2026?'end':'middle'} color="#a8b7ae">{year===2026?'2026 projected':year}</Label>)}
 </g>
</Svg>;
