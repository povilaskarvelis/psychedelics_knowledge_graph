import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Node,Label,Link,Tabs,p,mix,source,GREEN} from './shared';

const drugs=['Ketamine','Psilocybin','MDMA'];
const conditions=['Major depressive disorder','Treatment-resistant depression','Obsessive-compulsive disorder','Post-traumatic stress disorder','Alcohol use disorder','Suicidal ideation & behavior'];
const sections=[
 {title:'Study designs',items:[['Randomized trials',30,'#829fbd'],['Open-label trials',6,'#b8a05a'],['Observational studies',5,'#b77892']],all:[30,6,5,5,4,4,2,2,1,1]},
 {title:'Comparators',items:[['Active treatment',19,'#829fbd'],['Baseline',8,'#b8a05a'],['Placebo',4,'#b77892']],all:[19,8,8,4,3,3,2,1,5]},
 {title:'Follow-up',items:[['1–3 months',30,'#829fbd'],['1–4 weeks',15,'#b8a05a'],['4–12 months',9,'#b77892']],all:[30,15,9,3,2,2,2,1,1,5]}
];
const palette=['#829fbd','#b8a05a','#b77892','#70aaa0','#c49381','#9784bb','#b1b48e','#6b979a','#999283','#8192a4'];
function Facet({data,frame}){
 const total=data.all.reduce((a,b)=>a+b,0);
 let offset=0;
 return <div style={{position:'absolute',left:850,top:380,width:920,height:550,background:'#101816',border:'2px solid #30443c',borderRadius:28,padding:45,boxSizing:'border-box',opacity:p(frame,0,16),translate:`${mix(100,0,p(frame,0,28))}px 0px`}}>
  <div style={{fontSize:70,letterSpacing:-2}}>{data.title}</div>
  <svg width="826" height="64" style={{marginTop:30,marginBottom:30}}><defs><clipPath id="barclip"><rect width="826" height="42" rx="12"/></clipPath></defs><g clipPath="url(#barclip)">{data.all.map((n,i)=>{const x=offset;offset+=n/total*826;return <rect key={i} x={x} y="0" width={n/total*826*p(frame,12,44)} height="42" fill={palette[i]}/>;})}</g></svg>
  {data.items.map(([name,n,color],i)=><div key={name} style={{display:'flex',alignItems:'center',gap:20,fontSize:48,marginBottom:26,opacity:p(frame,24+i*5,40+i*5)}}><span style={{width:16,height:44,borderRadius:5,background:color}}/><span style={{flex:1}}>{name}</span><span style={{fontSize:58}}>{n}</span></div>)}
 </div>;
}
export const Explore=()=>{
 const f=useCurrentFrame(),select=p(f,136,180),expand=p(f,215,255);
 const idx=f<410?0:f<548?1:2,local=f-(idx===0?260:idx===1?410:548);
 return <Stage><Tabs frame={f}/><Title top={160} size={100} opacity={1-expand}>Explore how studies connect</Title><Title top={160} size={100} opacity={expand}>Compare studies in context</Title>
  <Svg>
   {drugs.flatMap((drug,i)=>conditions.map((condition,j)=>{
    const e=source.graph.edges.find(e=>e.compound===drug&&e.target===condition);if(!e)return null;
    const on=i===1&&j===0;
    return <Link key={`${i}-${j}`} id={`condition-${i}-${j}`} x1={mix(520,235,expand)} y1={mix(440+i*190,540,expand)} x2={mix(1100,630,expand)} y2={mix(350+j*113,540,expand)} color="#82a9d8" width={on?mix(4,12,select):2+Math.sqrt(e.count)*.28} progress={p(f,15+i*3+j,65+i*3+j)} opacity={on?.85:mix(.3,.018,select)}/>;
   }))}
   {drugs.map((drug,i)=><g key={drug} opacity={i===1?1:1-select}><Node x={mix(520,235,expand)} y={mix(440+i*190,540,expand)} r={mix(24,32,expand)}/><Label x={mix(475,140,expand)} y={mix(440+i*190,460,expand)} anchor={expand>.5?'start':'end'} size={52}>{drug}</Label></g>)}
   {conditions.map((name,j)=><g key={name} opacity={j===0?1:1-select}><Node x={mix(1100,630,expand)} y={mix(350+j*113,540,expand)} color="#82a9d8" r={mix(18,28,expand)}/>{j===0?<><Label x={mix(1138,435,expand)} y={mix(350,600,expand)} size={mix(44,45,expand)}>{expand>.5?'Major depressive':name}</Label>{expand>.5?<Label x={435} y={654} size={45}>disorder</Label>:null}</>:<Label x={1138} y={350+j*113} size={42}>{name.length>28?name.replace(' & behavior',''):name}</Label>}</g>)}
   <g opacity={p(f,254,285)}><Label x={140} y={793} size={132}>75</Label><Label x={140} y={893} size={66} color="#95aca2">studies</Label></g>
   <circle cx={mix(880,1100,p(f,105,132))} cy={mix(620,350,p(f,105,132))} r={mix(10,28,p(f,133,151))} fill="none" stroke="#e7fff4" strokeWidth="2" opacity={p(f,94,110)*(1-p(f,165,184))}/>
  </Svg>
  {f>=260?<Facet key={idx} data={sections[idx]} frame={local}/>:null}
 </Stage>;
};
