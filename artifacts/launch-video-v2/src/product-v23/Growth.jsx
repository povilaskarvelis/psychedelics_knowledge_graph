import React from 'react';
import {Svg,Label,p} from '../product/shared';
import history from '../v22-area-timeline.json';

// Observed annual counts, with a separately identified full-year projection.
export const years=history.years.map(row=>({year:row.year,total:row.papers}));
const first=years.find(row=>row.year===2021).total;
const latest=years.find(row=>row.year===2025).total;
export const projected2026=Math.round(latest*Math.pow(latest/first,1/4)/100)*100;
const baseline=850,scale=510/2000;
const x=i=>140+i*1620/(years.length-1);
const barWidth=15;
const total=years.reduce((sum,row)=>sum+row.total,0);
const rand=(i,s)=>{const value=Math.sin(i*127.1+s*311.7)*43758.5453;return value-Math.floor(value);};
export const paperOrigins=Array.from({length:560},(_,i)=>{
 const rank=(i+.5)/560*total;let accumulated=0;
 const index=years.findIndex(row=>{accumulated+=row.total;return accumulated>=rank;});
 return {x:x(index)+2+rand(i,1)*(barWidth-4),y:baseline-rand(i,3)*years[index].total*scale};
});
export const Growth=({frame:f})=><Svg>
 <defs><pattern id="current-year-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><rect width="3" height="7" fill="#69a196"/></pattern></defs>
 <g opacity={p(f,8,22)*(1-p(f,165,187))}>
  {/* A directional cue, not an additional data series. */}
  <g fill="none" stroke="#b3c5bb" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round">
   <path d="M 1060 755 C 1300 738 1510 580 1635 365" pathLength="1" strokeDasharray="1" strokeDashoffset={1-p(f,60,127)} opacity={p(f,60,72)*.8}/>
   <path d="M 1608 382 L 1635 365 L 1637 397" opacity={p(f,122,134)*.8}/>
  </g>
  {years.map((row,i)=>{
   const reveal=p(f,20+i*70/(years.length-1),48+i*70/(years.length-1)),observedHeight=row.total*scale*reveal;
   const height=(row.year===2026?projected2026:row.total)*scale*reveal;
   return <g key={row.year}>
    <rect x={x(i)} y={baseline-observedHeight} width={barWidth} height={observedHeight} rx="3" fill="#69a196"/>
    {row.year===2026?<rect x={x(i)} y={baseline-height} width={barWidth} height={Math.max(0,height-observedHeight)} fill="url(#current-year-hatch)" stroke="#69a196" strokeWidth="1.5"/>:null}
   </g>;
  })}
  {[1950,1970,1990,2010,2026].map(year=><Label key={year} x={x(year-1950)+(year===2026?barWidth:barWidth/2)} y={914} size={44} anchor={year===1950?'start':year===2026?'end':'middle'} color="#a8b7ae">{year}</Label>)}
 </g>
</Svg>;
