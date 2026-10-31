import React from 'react';
import {Label,p,mix} from '../product/shared';
import data from '../v10-sample.json';
const bins=data.labels.slice(0,8);
const years=Array.from({length:8},(_,i)=>2019+i);
export const SampleSizes=({frame:f})=><div style={{position:'absolute',left:850,top:350,width:920,height:565,background:'#101816',border:'2px solid #30443c',borderRadius:28,padding:44,boxSizing:'border-box',opacity:p(f,0,15),translate:`${mix(85,0,p(f,0,25))}px 0px`}}>
 <div style={{fontSize:70,letterSpacing:-2}}>Sample sizes</div>
 <svg width="826" height="398" style={{marginTop:18}}>
  {bins.map((bin,j)=><Label key={bin} x={178} y={23+j*42} size={40} anchor="end">{bin.replaceAll('-','–')}</Label>)}
  {years.map((year,i)=><g key={year}>
   {bins.map((bin,j)=>{
    const cell=data.cells.find(c=>Number(c.yearStart)===year&&c.sampleLabel===bin),count=Number(cell?.studyCount||0);
    const reveal=p(f,10+i*2,34+i*2);
    return <rect key={bin} x={200+i*77} y={4+j*42} width={70*reveal} height="36" rx="5" fill={count?'#b89a5b':'#1e2a26'} fillOpacity={count?.16+.76*Math.sqrt(count/6):1}/>;
   })}
   {[0,3,7].includes(i)?<Label x={235+i*77} y={371} size={40} anchor="middle" color="#95aca2">{year}</Label>:null}
  </g>)}
 </svg>
</div>;
