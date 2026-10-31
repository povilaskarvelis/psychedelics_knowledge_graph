import React from 'react';
import {Easing,interpolate,useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Node,Label,Link,p,mix,source,areas,broad} from '../product/shared';
import {compounds,overviewY} from '../product-v12/Graph';
import {StudyFacets} from '../product-v13/StudyFacets';
const conditions=['Major depressive disorder','Treatment-resistant depression','Obsessive-compulsive disorder','Post-traumatic stress disorder','Alcohol use disorder','Suicidal ideation & behavior'];
const labelEase={extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:Easing.bezier(.45,0,.25,1)};
export const Drilldown=({balancedTitles=false,wideTitles=false,separateBars=false,explorationTitle=false,balancedGraphLayout=false,compactTopTitles=false,alignedSingleLineTitles=false,balancedNarrativeTiming=false,smoothConditionLabel=false,smoothConditionLabelEnd=268,cohesiveConditionLabel=false,studyTitleStart=null,clickSelectedEdge=false})=>{
 const f=useCurrentFrame(),selected=p(f,0,32),split=p(f,36,104),pick=p(f,154,186),detail=p(f,218,268);
 const cx=mix(mix(620,520,split),235,detail),dy=i=>mix(overviewY(i),540,detail);
 const areaY=j=>(balancedGraphLayout?370:300)+j*(balancedGraphLayout?58:66);
 const tx=mix(mix(1220,1100,split),630,detail),ty=j=>mix(mix(areaY(0),350+j*113,split),540,detail);
 const idx=f<397?0:f<525?1:f<630?2:3,local=f-([260,397,525,630][idx]);
 const labelSize=mix(42,46,detail);
 const conditionLabelMotion=cohesiveConditionLabel?interpolate(f,[202,268],[0,1],labelEase):detail;
 const conditionWrapX=cohesiveConditionLabel?interpolate(f,[218,268],[0,1],labelEase):smoothConditionLabel?interpolate(f,[218,smoothConditionLabelEnd],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'}):null;
 const conditionWrapY=cohesiveConditionLabel?conditionWrapX:null;
 const conditionLabelX=mix(mix(1220,1100,split)+38,435,conditionLabelMotion);
 const conditionLabelY=cohesiveConditionLabel?mix(350,610,conditionLabelMotion):mix(mix(300,350,split)+80*p(f,202,218),610,detail);
 return <Stage>
  <Title top={alignedSingleLineTitles?96:70} size={compactTopTitles?96:balancedTitles?100:86} opacity={1-p(f,studyTitleStart===null?(balancedNarrativeTiming?70:100):studyTitleStart-20,studyTitleStart===null?(balancedNarrativeTiming?90:120):studyTitleStart)}>{explorationTitle?'So you can explore how it all connects':wideTitles?<React.Fragment>From study details to patterns<br/>across the field</React.Fragment>:balancedTitles?<React.Fragment>From study details to<br/>patterns across the field</React.Fragment>:<React.Fragment>From study details<br/>to patterns across the field</React.Fragment>}</Title>
  <Title size={compactTopTitles?96:100} opacity={p(f,studyTitleStart===null?(balancedNarrativeTiming?91:121):studyTitleStart,studyTitleStart===null?(balancedNarrativeTiming?111:141):studyTitleStart+18)}>See how the studies were done</Title>
  <Svg>
   {compounds.flatMap((drug,i)=>areas.map((a,j)=>{
    const c=broad.cells.find(c=>c.compound===drug.toLowerCase()&&c.area===a.name);if(!c?.count)return null;
    return <Link key={'b'+i+'-'+j} id={'broad-drill-'+i+'-'+j} x1={cx} y1={dy(i)} x2={j===0?tx:1220} y2={j===0?ty(0):areaY(j)} color={a.color} width={2+Math.sqrt(c.count)*.24} opacity={(j===0?mix(.35,.85,selected):.35*(1-selected))*(1-split)}/>;
   }))}
   {compounds.flatMap((drug,i)=>conditions.map((condition,j)=>{
    const e=source.graph.edges.find(e=>e.compound===drug&&e.target===condition);if(!e)return null;
    const chosen=i===1&&j===0;
    return <Link key={i+'-'+j} id={'condition-drill-'+i+'-'+j} x1={cx} y1={dy(i)} x2={tx} y2={ty(j)} color="#82a9d8" width={chosen?mix(5,12,pick):2+Math.sqrt(e.count)*.28} opacity={split*(chosen?.85:mix(.33,0,pick))}/>;
   }))}
   {compounds.map((drug,i)=><g key={drug} opacity={i===1?1:1-pick}>
    <Node x={cx} y={dy(i)} r={mix(24,32,detail)}/>
    <Label x={mix(mix(620,520,split)-42,408,detail)} y={mix(overviewY(i)-80*p(f,202,218),460,detail)} anchor="end" size={56}>{drug}</Label>
   </g>)}
   {areas.slice(1).map((a,k)=><g key={a.name} opacity={1-selected}><Node x={1220} y={areaY(k+1)} r={15} color={a.color}/><Label x={1254} y={areaY(k+1)} size={44}>{a.name}</Label></g>)}
   {conditions.map((name,j)=><g key={name} opacity={(j===0?1:split)*(j===0?1:1-pick)}>
    <Node x={tx} y={ty(j)} r={j===0?mix(mix(mix(15,26,selected),18,split),28,detail):18} color="#82a9d8"/>
    <g opacity={p(f,50,76)}>
     {j===0?<React.Fragment>
      <Label x={conditionLabelX} y={conditionLabelY} size={labelSize}>Major depressive</Label>
      <Label
       x={conditionLabelX+335.634*labelSize/42*(1-(conditionWrapX??p(detail,.4,.95)))}
       y={conditionLabelY+53*(conditionWrapY??p(detail,0,.45))}
       size={labelSize}
      >disorder</Label>
     </React.Fragment>:<Label x={tx+38} y={ty(j)} size={42}>{name}</Label>}
    </g>
   </g>)}
   <Label x={tx+34} y={ty(0)} size={44} opacity={1-p(f,32,48)}>Conditions</Label>
   <circle cx={mix(900,clickSelectedEdge?860:1100,p(f,134,154))} cy={mix(525,clickSelectedEdge?403:350,p(f,134,154))} r={mix(10,28,p(f,154,167))} fill="none" stroke="#e6fff3" strokeWidth="2" opacity={p(f,130,141)*(1-p(f,176,190))}/>
   <g opacity={p(f,272,295)}><Label x={140} y={795} size={134}>75</Label><Label x={140} y={889} size={66} color="#95aca2">studies</Label></g>
  </Svg>
  {f>=260?<StudyFacets key={idx} index={idx} frame={local} separateBars={separateBars}/>:null}
 </Stage>;
};
