import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Paper,Node,Link,Label,p,mix,areas,broad} from '../product/shared';
import history from '../story-data.json';

const names=['Ketamine','Psilocybin','MDMA'];
const selected=areas.filter(a=>['Conditions','Safety','Cognition','Subjective effects','Real-world use','Molecular effects'].includes(a.name));
const bars=history.timeline.filter(r=>r.year>=2018&&r.year<=2025);
const flowPoint=(x1,y1,x2,y2,t)=>{
 const c1x=mix(x1,x2,.43),c2x=mix(x1,x2,.57),u=1-t;
 return {x:u*u*u*x1+3*u*u*t*c1x+3*u*t*t*c2x+t*t*t*x2,y:u*u*u*y1+3*u*u*t*y1+3*u*t*t*y2+t*t*t*y2};
};

export const Living=({headlineSize=108,compactLabels=false,pipelineFlow=false,refinedPipelineFlow=false,alignIngestionWithDivider=false,rightPanelLabel})=>{
 const f=useCurrentFrame(),cycle=Math.max(0,f-28)%88,round=Math.floor(Math.max(0,f-28)/88);
 const refresh=p(cycle,39,49)*(1-p(cycle,68,83));
 const graphRefresh=refinedPipelineFlow?p(cycle,28,38)*(1-p(cycle,49,59)):pipelineFlow?p(cycle,24,35)*(1-p(cycle,48,58)):refresh;
 const chartFlow=pipelineFlow?p(cycle,42,64):0;
 const chartRefresh=refinedPipelineFlow?p(cycle,68,77)*(1-p(cycle,82,87)):pipelineFlow?p(cycle,60,70)*(1-p(cycle,78,87)):refresh;
 const ingestionX=alignIngestionWithDivider?996:pipelineFlow?565:960;
 const ingestionPulse=refinedPipelineFlow?p(cycle,14,32):0;

 return <Stage><Title size={headlineSize}>Always stay up to date</Title><Svg>
  <rect x="190" y="280" width="1540" height="510" rx="30" fill="#0d1511" stroke="#355146" strokeWidth="2"/>
  <path d={`M ${ingestionX} 790 V 907`} fill="none" stroke="#83bca2" strokeWidth="3" opacity={.65}/>
  <Label x={565} y={345} size={58} anchor="middle">Knowledge graph</Label><Label x={1360} y={345} size={58} anchor="middle">{rightPanelLabel??(compactLabels?'Charts':'Visualizations')}</Label>
  <path d="M 996 324 V 747" stroke="#2a4237" strokeWidth="2"/>

  {names.flatMap((name,i)=>selected.map((a,j)=>{
   const d=broad.cells.find(c=>c.compound===name.toLowerCase()&&c.area===a.name);
   return <Link key={`${i}-${j}`} id={`update-${i}-${j}`} x1={302} y1={450+i*120} x2={860} y2={415+j*60} color={a.color} width={3+Math.sqrt(d.count)*.13} opacity={mix(.3,i===round%3?.95:.3,graphRefresh)} progress={p(f,0,24)}/>;
  }))}
  {names.map((name,i)=><Node key={name} x={302} y={450+i*120} r={18+(i===round%3?graphRefresh*6:0)}/>)}
  {selected.map((a,j)=><Node key={a.name} x={860} y={415+j*60} r={13+(refinedPipelineFlow?graphRefresh*3:0)} color={a.color}/>)}

  {bars.map((r,i)=>{
   const height=r.total/1806*195;
   return <g key={r.year}><rect x={1080+i*72} y={629-height} width="48" height={height} rx="4" fill={i===round%8?'#F4AD61':'#72B7FF'} opacity={mix(.48,.95,chartRefresh)}/></g>;
  })}
  <path d="M1070 641 H1665" stroke="#476453" strokeWidth="2"/>
  {Array.from({length:16},(_,i)=>{
   const area=areas[i%8],compound=['ketamine','mdma'][Math.floor(i/8)],cell=broad.cells.find(c=>c.compound===compound&&c.area===area.name);
   return <rect key={i} x={1080+(i%8)*72} y={668+Math.floor(i/8)*42} width="48" height="26" rx="4" fill={area.color} opacity={.12+.60*Math.sqrt(cell.count/1996)+chartRefresh*.12}/>;
  })}

  {pipelineFlow&&!refinedPipelineFlow?<React.Fragment>
   <Link id="graph-to-charts" x1={890} y1={600} x2={1080} y2={600} color="#83bca2" width={4} opacity={.72} progress={chartFlow}/>
   <circle cx={mix(890,1080,chartFlow)} cy={600} r={7} fill="#c0efd3" opacity={p(cycle,40,45)*(1-p(cycle,65,70))}/>
   <path d="M 1061 589 L 1080 600 L 1061 611" fill="none" stroke="#83bca2" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" opacity={p(cycle,57,64)*(1-p(cycle,78,87))}/>
  </React.Fragment>:null}

  {refinedPipelineFlow?selected.map((area,j)=>{
   const barIndex=[0,2,4,1,3,6][j],barHeight=bars[barIndex].total/1806*195;
   const target=j<3?{x:1080+barIndex*72+24,y:629-barHeight}:{x:1080+barIndex*72+24,y:681+(j%2)*42};
   const start=42+j*2,end=64+j*2;
   return <g key={area.name}>
    {[0,1,2,3].map(k=>{
     const particleStart=start+k*2,particleEnd=end+k*2,travel=p(cycle,particleStart,particleEnd),point=flowPoint(874,415+j*60,target.x,target.y,travel);
     const opacity=p(cycle,particleStart,particleStart+4)*(1-p(cycle,particleEnd,particleEnd+5));
     return <g key={k} opacity={opacity}>
      <circle cx={point.x} cy={point.y} r={7-k*.8} fill={area.color}/>
      <circle cx={point.x} cy={point.y} r={12-k} fill="none" stroke={area.color} strokeWidth="2" opacity={.28-k*.04}/>
     </g>;
    })}
    <circle cx={target.x} cy={target.y} r={mix(8,22,p(cycle,end-2,end+7))} fill="none" stroke={area.color} strokeWidth="3" opacity={p(cycle,end-3,end+1)*(1-p(cycle,end+8,end+16))}/>
   </g>;
  }):null}

  <Node x={ingestionX} y={790} r={pipelineFlow?mix(11,18,graphRefresh):11} color="#83bca2"/>
  <Label x={205} y={935} size={60}>New papers</Label>
  {[0,1,2,3].map(i=>{
   const travel=p(f,16+i*88,(refinedPipelineFlow?42:54)+i*88);
   return <Paper key={i} x={pipelineFlow?ingestionX:mix(1840,ingestionX,p(f,16+i*88,65+i*88))} y={refinedPipelineFlow?mix(960,900,travel):pipelineFlow?mix(960,790,travel):935} w={72} opacity={p(f,12+i*88,24+i*88)*(1-p(f,(refinedPipelineFlow?38:pipelineFlow?58:64)+i*88,(refinedPipelineFlow?48:pipelineFlow?67:73)+i*88))} color="#bdd3c4"/>;
  })}
  {refinedPipelineFlow?<React.Fragment>
   <circle cx={ingestionX} cy={mix(900,790,ingestionPulse)} r={mix(5,8,ingestionPulse)} fill="#c0efd3" opacity={p(cycle,12,16)*(1-p(cycle,32,38))}/>
   <circle cx={ingestionX} cy={790} r={mix(9,38,p(cycle,30,40))} fill="none" stroke="#9ae6c7" strokeWidth="3" opacity={p(cycle,29,33)*(1-p(cycle,39,47))}/>
  </React.Fragment>:null}
  {!pipelineFlow?<circle cx={ingestionX} cy={mix(915,790,p(cycle,38,53))} r="6" fill="#c0efd3" opacity={p(cycle,36,41)*(1-p(cycle,53,58))}/>:null}

  {!refinedPipelineFlow?<rect x="190" y="280" width={pipelineFlow?806:1540} height="510" rx="30" fill="none" stroke="#b5dbc5" strokeWidth="3" opacity={graphRefresh*.48}/>:null}
  {pipelineFlow&&!refinedPipelineFlow?<rect x="996" y="280" width="734" height="510" rx="30" fill="none" stroke="#b5dbc5" strokeWidth="3" opacity={chartRefresh*.48}/>:null}
 </Svg></Stage>;
};
