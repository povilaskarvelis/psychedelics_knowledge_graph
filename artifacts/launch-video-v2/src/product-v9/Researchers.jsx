import React from 'react';
import data from '../v9-authors.json';
import {Label,Node,Link,p,mix} from '../product/shared';

export const Researchers=({frame})=>{
 const expand=p(frame,95,145);
 return <g>
  <rect x="140" y="265" width="260" height="86" rx="18" fill="#25374c" stroke="#6382a7"/>
  <Label x={270} y={311} size={58} anchor="middle">{data.compound}</Label>
  <Label x={440} y={311} size={53}>{data.topic}</Label>
  <Label x={165} y={405} size={44} color="#9eafa7">First / last authors</Label>
  <Label x={mix(1705,792,expand)} y={405} size={44} anchor="end" color="#9eafa7">Studies</Label>
  {data.authors.slice(0,4).map((a,i)=><g key={a.name} opacity={p(frame,28+i*5,49+i*5)}>
   <rect x="140" y={445+i*125} width={mix(1630,705,expand)} height={108} rx="16" fill="#101816" stroke={i===0?'#72B7FF':'#101816'} strokeOpacity={expand}/>
   <Label x={172} y={482+i*125} size={mix(49,45,expand)}>{a.name}</Label>
   <rect x={mix(920,173,expand)} y={mix(465,518,expand)+i*125} width={mix(610,450,expand)*a.papers/data.authors[0].papers*p(frame,40+i*4,78+i*4)} height={mix(35,12,expand)} rx="6" fill="#72B7FF"/>
   <Label x={mix(1705,792,expand)} y={482+i*125} size={mix(60,48,expand)} anchor="end">{a.papers}</Label>
  </g>)}
  <g opacity={p(frame,122,150)}>
   <Label x={1245} y={400} size={49}>Research areas</Label>
   {data.researcherConnections.edges.map((e,j)=><g key={j}>
    <Link id={`researcher-area-${j}`} x1={845} y1={482} x2={1220} y2={470+j*89} color={e.color} width={2+e.width} progress={p(frame,140+j*3,178+j*3)} opacity={.65}/>
    <Node x={1220} y={470+j*89} r={16} color={e.color}/>
    <Label x={1254} y={470+j*89} size={43}>{data.researcherConnections.labels[j+1]}</Label>
   </g>)}
   <Node x={845} y={482} r={14} color="#72B7FF"/>
  </g>
 </g>;
};
