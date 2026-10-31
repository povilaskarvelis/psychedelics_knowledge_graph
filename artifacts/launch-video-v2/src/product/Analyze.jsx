import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Node,Label,Link,Tabs,p,mix,areas,source,broad} from './shared';

const trends=['Conditions','Subjective effects','Treatment context'];
const authors=[source.authorRows[0],source.authorRows[1],source.authorRows[4]];
const focusAreas=['Conditions','Safety','Subjective effects','Real-world use','Brain regions','Molecular effects'];
export const Analyze=()=>{
 const f=useCurrentFrame(),toAuthors=p(f,345,380),toMatrix=p(f,640,675);
 return <Stage><Tabs active="Analyze" frame={f}/>
  <Title top={160} size={100} opacity={1-toAuthors}>See how research is changing</Title>
  <Title top={160} size={100} opacity={toAuthors*(1-toMatrix)}>Find who works on your topic</Title>
  <Title top={160} size={100} opacity={toMatrix}>Research papers by topic</Title>
  <Svg>
   <g opacity={1-toAuthors}>
    <Label x={1380} y={333} size={40} anchor="middle" color="#98a99f">2017–2021</Label><Label x={1640} y={333} size={40} anchor="middle" color="#cbd9d0">2022–2026</Label>
    {trends.map((name,i)=>{
     const d=source.momentum.find(m=>m.label===name),color=areas.find(a=>a.name===name).color;
     const points=d.svg.match(/points="([^"]+)"/)[1].split(' ').map(v=>v.split(',').map(Number));
     const [latest,prior]=d.summary.match(/[\d,]+/g).map(v=>Number(v.replaceAll(',','')));
     const y=452+i*214,prog=p(f,30+i*8,100+i*8);
     return <g key={name} opacity={p(f,18+i*10,40+i*10)}>
      <rect x="139" y={y-85} width="1635" height="188" rx="24" fill="#101816" stroke="#253b32"/>
      <Label x={178} y={y-8} size={name.length>16?44:52}>{name}</Label>
      <rect x="1018" y={y-60} width="280" height="120" fill={color} opacity=".06"/>
      <path d={`M 1018 ${y-58} V ${y+58}`} stroke="#66796e" strokeDasharray="5 7"/>
      <polyline points={points.map(([x,v])=>`${738+x*4.24},${y-63+v*4.2}`).join(' ')} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" pathLength="1" strokeDasharray="1" strokeDashoffset={1-prog}/>
      <Label x={1380} y={y-6} size={55} anchor="middle" color="#93a39a">{prior.toLocaleString()}</Label><Label x={1640} y={y-6} size={68} anchor="middle" color={color}>{latest.toLocaleString()}</Label>
     </g>;
    })}
    <Label x={1510} y={990} size={44} anchor="middle" color="#a3b4aa">Research papers</Label>
   </g>
   <g opacity={toAuthors*(1-toMatrix)}>
    {authors.flatMap((author,i)=>focusAreas.map((name,j)=>{
     const c=source.authorCells.find(c=>c.key===author.key&&c.area===name);if(!c?.count)return null;
     const highlight=p(f,480,505)*(1-p(f,565,590));
     return <Link key={`${i}-${j}`} id={`author-${i}-${j}`} x1={740} y1={455+i*200} x2={1190} y2={365+j*112} color={c.color} width={2+Math.sqrt(c.count)*1.1} progress={p(f,376+i*6+j*3,422+i*6+j*3)} opacity={mix(.37,i===1?.78:.065,highlight)}/>;
    }))}
    {authors.map((a,i)=><g key={a.key}><Node x={740} y={455+i*200} r={27}/><Label x={696} y={455+i*200} anchor="end" size={45}>{a.name}</Label></g>)}
    {focusAreas.map((name,j)=><g key={name}><Node x={1190} y={365+j*112} color={areas.find(a=>a.name===name).color} r={21}/><Label x={1230} y={365+j*112} size={46}>{name}</Label></g>)}
   </g>
   <g opacity={toMatrix}>
    {['Conditions','Subjective effects','Treatment context'].map((name,j)=><g key={name}><Label x={885+j*345} y={j?330:355} size={48} anchor="middle">{name.split(' ')[0]}</Label>{j?<Label x={885+j*345} y={383} size={48} anchor="middle">{name.split(' ')[1]}</Label>:null}</g>)}
    {['Ketamine','Psilocybin','MDMA','LSD','Ayahuasca','DMT'].map((name,i)=><g key={name}><Label x={565} y={455+i*90} size={48} anchor="end">{name}</Label>{['Conditions','Subjective effects','Treatment context'].map((area,j)=>{const d=broad.cells.find(c=>c.compound===name.toLowerCase()&&c.area===area);return <g key={area}><rect x={735+j*345} y={418+i*90} width="300" height="74" rx="13" fill={d?.color||'#55b7ab'} fillOpacity={d?.count?mix(.08,.72,Math.sqrt(d.count/1985)):.02} stroke="#355043"/><Label x={885+j*345} y={455+i*90} size={48} anchor="middle">{d?.count||'—'}</Label></g>;})}</g>)}
   </g>
  </Svg>
 </Stage>;
};
