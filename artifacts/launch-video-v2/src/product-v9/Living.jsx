import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Paper,Node,Link,Label,p,mix,areas,broad} from '../product/shared';
import history from '../story-data.json';
const names=['Ketamine','Psilocybin','MDMA'];
const selected=areas.filter(a=>['Conditions','Safety','Cognition','Subjective effects','Real-world use','Molecular effects'].includes(a.name));
const bars=history.timeline.filter(r=>r.year>=2018&&r.year<=2025);
export const Living=()=>{
 const f=useCurrentFrame(),cycle=Math.max(0,f-28)%88,round=Math.floor(Math.max(0,f-28)/88);
 const arrive=p(cycle,0,37),refresh=p(cycle,39,49)*(1-p(cycle,68,83));
 return <Stage><Title size={108}>Updated as new papers arrive</Title><Svg>
  <rect x="190" y="280" width="1540" height="510" rx="30" fill="#0d1511" stroke="#355146" strokeWidth="2"/>
  <path d="M 960 790 V 907" fill="none" stroke="#83bca2" strokeWidth="3" opacity={.65}/>
  <Label x={565} y={345} size={58} anchor="middle">Knowledge graph</Label><Label x={1360} y={345} size={58} anchor="middle">Visualizations</Label>
  <path d="M 996 324 V 747" stroke="#2a4237" strokeWidth="2"/>
  {names.flatMap((name,i)=>selected.map((a,j)=>{const d=broad.cells.find(c=>c.compound===name.toLowerCase()&&c.area===a.name);return <Link key={`${i}-${j}`} id={`update-${i}-${j}`} x1={302} y1={450+i*120} x2={860} y2={415+j*60} color={a.color} width={3+Math.sqrt(d.count)*.13} opacity={mix(.3,i===round%3?.95:.3,refresh)} progress={p(f,0,24)}/>;}))}
  {names.map((name,i)=><Node key={name} x={302} y={450+i*120} r={18+(i===round%3?refresh*6:0)}/>)}{selected.map((a,j)=><Node key={a.name} x={860} y={415+j*60} r={13} color={a.color}/>)}
  {bars.map((r,i)=>{const height=r.total/1806*195;return <g key={r.year}><rect x={1080+i*72} y={629-height} width="48" height={height} rx="4" fill={i===round%8?'#F4AD61':'#72B7FF'} opacity={mix(.48,.95,refresh)}/></g>;})}
  <path d="M1070 641 H1665" stroke="#476453" strokeWidth="2"/>
  {Array.from({length:16},(_,i)=>{const area=areas[i%8],compound=['ketamine','mdma'][Math.floor(i/8)],cell=broad.cells.find(c=>c.compound===compound&&c.area===area.name);return <rect key={i} x={1080+(i%8)*72} y={668+Math.floor(i/8)*42} width="48" height="26" rx="4" fill={area.color} opacity={.12+.60*Math.sqrt(cell.count/1996)+refresh*.12}/>;})}
  <Node x={960} y={790} r={11} color="#83bca2"/>
  <Label x={205} y={935} size={60}>New papers</Label>
  {[0,1,2,3].map(i=><Paper key={i} x={mix(1840,960,p(f,16+i*88,65+i*88))} y={935} w={72} opacity={p(f,12+i*88,24+i*88)*(1-p(f,64+i*88,73+i*88))} color="#bdd3c4"/>)}
  <circle cx={960} cy={mix(915,790,p(cycle,38,53))} r="6" fill="#c0efd3" opacity={p(cycle,36,41)*(1-p(cycle,53,58))}/>
  <rect x="190" y="280" width="1540" height="510" rx="30" fill="none" stroke="#b5dbc5" strokeWidth="3" opacity={refresh*.55}/>
 </Svg></Stage>;
};
