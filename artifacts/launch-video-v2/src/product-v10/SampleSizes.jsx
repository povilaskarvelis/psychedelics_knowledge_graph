import React from 'react';
import {Title,Svg,Label,p,mix} from '../product/shared';
import data from '../v10-sample.json';
const bins=data.labels.slice(0,8);
const years=Array.from({length:8},(_,i)=>2019+i);
export const SampleSizes=({frame:f})=>{
 const open=p(f,0,34);
 return <div style={{opacity:p(f,0,24)}}>
  <Title size={108}>How large were the studies</Title>
  <Svg>
   <Label x={140} y={280} size={51} color="#79bba5">Psilocybin</Label>
   <path d="M 432 256 V 304" stroke="#53675e" strokeWidth="2"/>
   <Label x={466} y={280} size={51}>Major depressive disorder</Label>
   <Label x={140} y={365} size={43} color="#9eafa7">Participants</Label>
   <Label x={1110} y={358} size={42} anchor="end" color="#9eafa7">Studies</Label>
   {[1,2,3,4,5,6].map(n=><g key={n}><rect x={1140+(n-1)*101} y={334} width="86" height="46" rx="6" fill="#79bba5" fillOpacity={.16+.76*Math.sqrt(n/6)}/><Label x={1183+(n-1)*101} y={358} size={36} color="#09150f" anchor="middle">{n}</Label></g>)}
   {bins.map((bin,j)=><Label key={bin} x={405} y={432+j*64} size={45} anchor="end" opacity={p(f,15,40)}>{bin.replaceAll('-','–')}</Label>)}
   {years.map((year,i)=><g key={year}>
    {bins.map((bin,j)=>{
     const cell=data.cells.find(c=>Number(c.yearStart)===year&&c.sampleLabel===bin),count=Number(cell?.studyCount||0);
     const reveal=p(f,20+i*3+j,45+i*3+j);
     return <rect key={bin} x={mix(930,470,open)+i*mix(90,159,open)} y={401+j*64} width={147*reveal} height="56" rx="8" fill={count?'#79bba5':'#182821'} fillOpacity={count?(.16+.76*Math.sqrt(count/6))*reveal:1} stroke="#2b4438" strokeWidth="1"/>;
    })}
    <Label x={543.5+i*159} y={965} size={45} anchor="middle" opacity={p(f,25,48)}>{year}</Label>
   </g>)}
  </Svg>
 </div>;
};
