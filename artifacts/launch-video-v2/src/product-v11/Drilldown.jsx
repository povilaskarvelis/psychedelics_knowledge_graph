import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Node,Label,Link,p,mix,source,compounds} from '../product/shared';
import {Overview} from '../product-v9/Graph';
import {StudyFacets} from './StudyFacets';
const conditions=['Major depressive disorder','Treatment-resistant depression','Obsessive-compulsive disorder','Post-traumatic stress disorder','Alcohol use disorder','Suicidal ideation & behavior'];
export const Drilldown=()=>{
 const f=useCurrentFrame(),selected=p(f,0,32),split=p(f,36,104),pick=p(f,154,186),detail=p(f,218,255);
 const cx=mix(mix(620,520,split),235,detail),dy=i=>mix(mix(410+i*210,440+i*190,split),540,detail);
 const tx=mix(mix(1220,1100,split),630,detail),ty=j=>mix(mix(300,350+j*113,split),540,detail);
 const idx=f<397?0:f<525?1:f<630?2:3,local=f-([260,397,525,630][idx]);
 return <Stage><Title size={98} opacity={1-p(f,100,125)}>From papers to connected knowledge</Title><Title size={108} opacity={p(f,100,125)*(1-detail)}>Look closer at the research</Title><Title size={108} opacity={detail}>How the studies were done</Title><Svg>
  {f<37?<Overview selection={selected}/>:null}
  <g opacity={p(f,35,40)}>
   {compounds.flatMap((drug,i)=>conditions.map((condition,j)=>{
    const e=source.graph.edges.find(e=>e.compound===drug&&e.target===condition);if(!e)return null;
    const chosen=i===1&&j===0;
    return <Link key={`${i}-${j}`} id={`drill-${i}-${j}`} x1={cx} y1={dy(i)} x2={tx} y2={ty(j)} color="#82a9d8" width={chosen?mix(5,12,pick):2+Math.sqrt(e.count)*.28} progress={1} opacity={chosen?.85:mix(.33,0,pick)}/>;
   }))}
   {compounds.map((drug,i)=><g key={drug} opacity={i===1?1:1-pick}><Node x={cx} y={dy(i)} r={mix(24,32,detail)}/><Label x={mix(cx-42,140,detail)} y={mix(dy(i),460,detail)} anchor={detail>.5?'start':'end'} size={56}>{drug}</Label></g>)}
   {conditions.map((name,j)=><g key={name} opacity={j===0?1:1-pick}><Node x={tx} y={ty(j)} r={mix(18,28,detail)} color="#82a9d8"/><g opacity={split}>{j===0&&detail>.5?<><Label x={435} y={610} size={46}>Major depressive</Label><Label x={435} y={663} size={46}>disorder</Label></>:<Label x={tx+38} y={ty(j)} size={42}>{name}</Label>}</g></g>)}
   <Label x={1254} y={300} size={44} opacity={1-split}>Conditions</Label>
  </g>
  <circle cx={mix(900,1100,p(f,134,154))} cy={mix(525,350,p(f,134,154))} r={mix(10,28,p(f,154,167))} fill="none" stroke="#e6fff3" strokeWidth="2" opacity={p(f,130,141)*(1-p(f,176,190))}/>
  <g opacity={p(f,260,286)}><Label x={140} y={795} size={134}>75</Label><Label x={140} y={889} size={66} color="#95aca2">studies</Label></g>
 </Svg>{f>=260?<StudyFacets key={idx} index={idx} frame={local}/>:null}</Stage>;
};
