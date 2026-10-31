import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Node,Label,Link,p,mix,areas,source,broad} from '../product/shared';
import history from '../story-data.json';
const types=[{label:'Primary studies',count:16731,key:'primary',color:'#61bda3'},{label:'Reviews',count:4672,key:'reviews',color:'#82a9d8'},{label:'Meta-analyses',count:332,key:'meta',color:'#d6a84f'}];
const years=history.timeline.filter(t=>t.year>=2017&&t.year<=2025);
const trends=['Safety','Molecular effects','Real-world use'];
const authors=[source.authorRows[0],source.authorRows[1],source.authorRows[4]];
const authorAreas=['Conditions','Safety','Subjective effects','Real-world use','Brain regions','Molecular effects'];
export const AnalyticalViews=()=>{
 const f=useCurrentFrame(),hist=p(f,125,176),trend=p(f,338,368),author=p(f,578,608),matrix=p(f,793,823);
 return <Stage>
  <Title size={108} opacity={1-p(f,123,150)}>Different kinds of research</Title>
  <Title size={100} opacity={p(f,123,150)*(1-trend)}>See how the literature is changing</Title>
  <Title size={104} opacity={trend*(1-author)}>See how research areas are changing</Title>
  <Title size={104} opacity={author*(1-matrix)}>Researchers and research areas</Title>
  <Title size={104} opacity={matrix}>Research papers by topic</Title>
  <Svg>
   <g opacity={1-trend}>
    {types.map((t,i)=><g key={t.key} opacity={p(f,10+i*6,32+i*6)}>
     <Label x={410+i*540} y={mix(398,304,hist)} size={mix(62,49,hist)} anchor="middle" color={t.color}>{t.label}</Label>
     <Label x={410+i*540} y={540} size={118} anchor="middle" opacity={1-hist}>{t.count.toLocaleString()}</Label>
    </g>)}
    <g opacity={1-hist}>{types.map((t,i)=>{const start=types.slice(0,i).reduce((s,t)=>s+t.count,0);return <rect key={t.key} x={140+start/21735*1635} y={660} width={t.count/21735*1635*p(f,25,72)} height="96" fill={t.color}/>;})}</g>
    <g opacity={hist}>
     {[0,500,1000,1500].map(n=><g key={n}><path d={`M 290 ${900-n/1806*475} H 1765`} stroke="#23382e" strokeWidth="1"/><Label x={248} y={900-n/1806*475} size={42} color="#91a49a" anchor="end">{n.toLocaleString()}</Label></g>)}
     {years.map((row,i)=>{let total=0;return <g key={row.year}>{types.map(t=>{const base=total;total+=row[t.key];const q=p(f,172+i*2,218+i*2);return <rect key={t.key} x={322+i*165} y={900-(base+row[t.key])*475/1806*q} width="112" height={row[t.key]*475/1806*q} fill={t.color}/>;})}<Label x={378+i*165} y={963} size={44} anchor="middle">{row.year}</Label></g>;})}
    </g>
   </g>
   <g opacity={trend*(1-author)}>
    <Label x={1380} y={320} size={42} anchor="middle" color="#98a99f">2017–2021</Label><Label x={1640} y={320} size={42} anchor="middle">2022–2026</Label>
    {trends.map((name,i)=>{
     const d=source.momentum.find(m=>m.label===name),color=areas.find(a=>a.name===name).color;
     const points=d.svg.match(/points="([^"]+)"/)[1].split(' ').map(v=>v.split(',').map(Number));
     const [latest,prior]=d.summary.match(/[\d,]+/g).map(v=>Number(v.replaceAll(',',''))),y=439+i*208;
     return <g key={name}><rect x="139" y={y-78} width="1635" height="178" rx="24" fill="#101816" stroke="#253b32"/><Label x={178} y={y} size={48}>{name}</Label><rect x="1018" y={y-58} width="280" height="116" fill={color} opacity=".06"/><path d={`M1018 ${y-58} V${y+58}`} stroke="#657b6c" strokeDasharray="5 7"/><polyline points={points.map(([x,v])=>`${738+x*4.24},${y-63+v*4.2}`).join(' ')} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round" pathLength="1" strokeDasharray="1" strokeDashoffset={1-p(f,367+i*8,420+i*8)}/><Label x={1380} y={y} size={56} anchor="middle" color="#93a39a">{prior.toLocaleString()}</Label><Label x={1640} y={y} size={68} anchor="middle" color={color}>{latest.toLocaleString()}</Label></g>;
    })}
   </g>
   <g opacity={author*(1-matrix)}>
    {authors.flatMap((a,i)=>authorAreas.map((name,j)=>{const c=source.authorCells.find(c=>c.key===a.key&&c.area===name);if(!c?.count)return null;return <Link key={`${i}-${j}`} id={`authors-v8-${i}-${j}`} x1={740} y1={425+i*210} x2={1190} y2={320+j*118} color={c.color} width={2+Math.sqrt(c.count)*1.1} progress={p(f,608+i*4+j*2,650+i*4+j*2)} opacity={mix(.37,i===1?.78:.065,p(f,673,696)*(1-p(f,750,770)))}/>;}))}
    {authors.map((a,i)=><g key={a.key}><Node x={740} y={425+i*210} r={27}/><Label x={696} y={425+i*210} size={45} anchor="end">{a.name}</Label></g>)}
    {authorAreas.map((name,j)=><g key={name}><Node x={1190} y={320+j*118} r={21} color={areas.find(a=>a.name===name).color}/><Label x={1230} y={320+j*118} size={46}>{name}</Label></g>)}
   </g>
   <g opacity={matrix}>
    {['Conditions','Subjective effects','Treatment context'].map((name,j)=><g key={name}><Label x={885+j*345} y={j?314:339} size={48} anchor="middle">{name.split(' ')[0]}</Label>{j?<Label x={885+j*345} y={367} size={48} anchor="middle">{name.split(' ')[1]}</Label>:null}</g>)}
    {['Ketamine','Psilocybin','MDMA','LSD','Ayahuasca','DMT'].map((name,i)=><g key={name}><Label x={565} y={443+i*90} size={48} anchor="end">{name}</Label>{['Conditions','Subjective effects','Treatment context'].map((area,j)=>{const d=broad.cells.find(c=>c.compound===name.toLowerCase()&&c.area===area);return <g key={area}><rect x={735+j*345} y={406+i*90} width={300*p(f,819+i*2+j*3,842+i*2+j*3)} height="74" rx="13" fill={d.color} fillOpacity={d.count?mix(.08,.72,Math.sqrt(d.count/1985)):.02} stroke="#355043"/><Label x={885+j*345} y={443+i*90} size={48} anchor="middle" opacity={p(f,840,857)}>{d.count||'—'}</Label></g>;})}</g>)}
   </g>
  </Svg>
 </Stage>;
};
