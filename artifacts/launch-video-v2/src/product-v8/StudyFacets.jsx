import React from 'react';
import {p,mix} from '../product/shared';
export const facets=[
 {title:'Study designs',items:[['Randomized trials',30],['Open-label trials',6],['Observational studies',5]],all:[30,6,5,5,4,4,2,2,1,1],indices:[0,1,2]},
 {title:'Comparators',items:[['Active treatment',19],['Baseline',8],['Placebo',4]],all:[19,8,8,4,3,3,2,1,5],indices:[0,1,3]},
 {title:'Follow-up',items:[['1–3 months',30],['1–4 weeks',15],['4–12 months',9]],all:[30,15,9,3,2,2,2,1,1,5],indices:[0,1,2]},
];
const palette=['#829fbd','#b8a05a','#b77892','#70aaa0','#c49381','#9784bb','#b1b48e','#6b979a','#999283','#8192a4'];
export const StudyFacets=({frame,index})=>{
 const data=facets[index],total=data.all.reduce((a,b)=>a+b,0);let offset=0;
 return <div style={{position:'absolute',left:850,top:350,width:920,height:565,background:'#101816',border:'2px solid #30443c',borderRadius:28,padding:44,boxSizing:'border-box',opacity:p(frame,0,15),translate:`${mix(85,0,p(frame,0,25))}px 0px`}}>
  <div style={{fontSize:70,letterSpacing:-2}}>{data.title}</div>
  <svg width="826" height="64" style={{marginTop:30,marginBottom:28}}><defs><clipPath id="facet-stack"><rect width="826" height="44" rx="12"/></clipPath></defs><g clipPath="url(#facet-stack)">{data.all.map((n,i)=>{const x=offset;offset+=n/total*826;return <rect key={i} x={x} width={n/total*826*p(frame,12,40)} height="44" fill={palette[i]}/>;})}</g></svg>
  {data.items.map(([name,n],i)=><div key={name} style={{display:'flex',alignItems:'center',gap:19,fontSize:49,marginBottom:24,opacity:p(frame,20+i*5,38+i*5)}}><span style={{width:16,height:45,borderRadius:4,background:palette[data.indices[i]]}}/><span style={{flex:1}}>{name}</span><span style={{fontSize:60}}>{n}</span></div>)}
 </div>;
};
