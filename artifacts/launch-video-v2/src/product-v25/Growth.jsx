import React from 'react';
import {Easing,interpolate} from 'remotion';
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
export const Growth=({frame:f,morphToAreas=false,syncArrow=false,constructionTiming=false})=><Svg>
 <defs><pattern id="current-year-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><rect width="3" height="7" fill="#69a196"/></pattern></defs>
 <g opacity={p(f,8,22)*(morphToAreas?1:1-p(f,165,187))}>
  {/* A directional cue, not an additional data series. */}
  <g fill="none" stroke="#b3c5bb" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" opacity={morphToAreas?1-p(f,constructionTiming?148:120,constructionTiming?176:150):1}>
   <path d="M 1070 755 C 1330 738 1580 585 1745 250" pathLength="1" strokeDasharray="1" strokeDashoffset={1-interpolate(f,syncArrow?(constructionTiming?[50,126]:[38,116]):[58,140],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:Easing.bezier(.45,0,.55,1)})} opacity={p(f,syncArrow?(constructionTiming?52:40):60,syncArrow?(constructionTiming?62:50):72)*.8}/>
   <path d="M 1717 270 L 1745 250 L 1747 284" opacity={p(f,syncArrow?(constructionTiming?126:116):140,syncArrow?(constructionTiming?134:122):146)*.8}/>
  </g>
  {years.map((row,i)=>{
   const reveal=p(f,20+i*70/(years.length-1),48+i*70/(years.length-1)),observedHeight=row.total*scale*reveal;
   const height=(row.year===2026?projected2026:row.total)*scale*reveal;
   const dissolve=morphToAreas?p(f,(constructionTiming?148:116)+i*12/(years.length-1),(constructionTiming?180:148)+i*12/(years.length-1)):0;
   return <g key={row.year} opacity={1-dissolve}>
    <rect x={x(i)} y={baseline-observedHeight} width={barWidth} height={observedHeight} rx="3" fill="#69a196"/>
    {row.year===2026?<rect x={x(i)} y={baseline-height} width={barWidth} height={Math.max(0,height-observedHeight)} fill="url(#current-year-hatch)" stroke="#69a196" strokeWidth="1.5"/>:null}
   </g>;
  })}
  <g opacity={morphToAreas?1-p(f,constructionTiming?148:120,constructionTiming?176:150):1}>{[1950,1970,1990,2010,2026].map(year=><Label key={year} x={x(year-1950)+(year===2026?barWidth:barWidth/2)} y={914} size={44} anchor={year===1950?'start':year===2026?'end':'middle'} color="#a8b7ae">{year}</Label>)}</g>
 </g>
</Svg>;
