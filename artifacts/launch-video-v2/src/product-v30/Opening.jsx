import React from 'react';
import {Easing,Interactive,interpolate,useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,p,mix,ease,broad,areas,BG,curve} from '../product/shared';
import {Growth,paperOrigins} from '../product-v25/Growth';
import {KnowledgeGraph,compounds} from '../product-v26/Graph';
import {ResearchScale} from '../product-v29/ResearchScale';

const remaining=broad.rows.map(row=>row.name).filter(name=>![...compounds,'(2R,6R)-hydroxynorketamine'].includes(name));
const names=[...compounds,...remaining];
const smooth={...ease,easing:Easing.bezier(.42,0,.58,1)};
const rand=(i,s)=>{const value=Math.sin(i*127.1+s*311.7)*43758.5453;return value-Math.floor(value);};
const bez=(a,b,c,d,t)=>(1-t)**3*a+3*(1-t)**2*t*b+3*(1-t)*t*t*c+t**3*d;
const linePoint=(x1,y1,x2,y2,t)=>({x:mix(x1,x2,t),y:mix(y1,y2,t)});
const polylinePoint=(points,t)=>{
 const lengths=points.slice(1).map((point,index)=>Math.hypot(point[0]-points[index][0],point[1]-points[index][1]));
 const total=lengths.reduce((sum,length)=>sum+length,0);let distance=t*total;
 for(let index=0;index<lengths.length;index++){
  if(distance<=lengths[index])return linePoint(points[index][0],points[index][1],points[index+1][0],points[index+1][1],distance/lengths[index]);
  distance-=lengths[index];
 }
 return {x:points.at(-1)[0],y:points.at(-1)[1]};
};

const scaleCenters=[
 {x:300,y:430,color:'#72a77c'},
 {x:740,y:430,color:'#5f9eb5'},
 {x:1180,y:430,color:'#a88bd1'},
 {x:1620,y:430,color:'#55b7ab'},
 {x:300,y:755,color:'#d1846f'},
 {x:740,y:755,color:'#d6a84f'},
 {x:1180,y:755,color:'#9bab62'},
 {x:1620,y:755,color:'#82a9d8'},
];

const iconParticleTarget=(areaIndex,slot)=>{
 const center=scaleCenters[areaIndex];
 if(slot<24){
  const angle=-Math.PI/2+slot/24*Math.PI*2;
  return {x:center.x+Math.cos(angle)*72,y:center.y+Math.sin(angle)*72};
 }
 const k=slot-24,t=k/35,angle=t*Math.PI*2;
 let point;
 if(areaIndex===0){
  if(k<14){const u=k/13;point={x:-19+15*Math.sin(u*Math.PI*2),y:-46+u*92};}
  else if(k<28){const u=(k-14)/13;point={x:19+15*Math.sin(u*Math.PI*2+Math.PI),y:-46+u*92};}
  else {const u=(k-28)/7;point={x:(k%2?18:-18),y:-38+u*76};}
 }else if(areaIndex===1){
  const side=k<18?-1:1,u=(k%18)/17,theta=-Math.PI/2+u*Math.PI*2;
  point={x:side*(13+27*Math.abs(Math.cos(theta))),y:37*Math.sin(theta)};
 }else if(areaIndex===2){
  if(k<18){const u=k/17,theta=-Math.PI/2+u*Math.PI*2;point={x:-17-23*Math.abs(Math.cos(theta)),y:38*Math.sin(theta)};}
  else {const branch=Math.floor((k-18)/6),u=((k-18)%6)/5;point=linePoint(-5,-28+branch*28,38,-28+branch*28,u);}
 }else if(areaIndex===3){
  if(k<24)point={x:45*Math.cos(k/24*Math.PI*2),y:27*Math.sin(k/24*Math.PI*2)};
  else point={x:13*Math.cos((k-24)/12*Math.PI*2),y:13*Math.sin((k-24)/12*Math.PI*2)};
 }else if(areaIndex===4){
  if(k<22){const u=k/21,theta=u*Math.PI;point={x:30*Math.cos(theta),y:-29+54*Math.sin(theta)};}
  else if(k<30)point=linePoint(0,25,31,43,(k-22)/7);
  else point={x:31+10*Math.cos((k-30)/6*Math.PI*2),y:43+10*Math.sin((k-30)/6*Math.PI*2)};
 }else if(areaIndex===5){
  if(k<24)point=polylinePoint([[-38,-34],[0,-49],[38,-34],[32,19],[0,48],[-32,19],[-38,-34]],k/23);
  else point=polylinePoint([[-18,0],[-3,15],[24,-17]],(k-24)/11);
 }else if(areaIndex===6){
  if(k<12)point={x:-15+15*Math.cos(k/12*Math.PI*2),y:-24+15*Math.sin(k/12*Math.PI*2)};
  else if(k<22)point={x:22+12*Math.cos((k-12)/10*Math.PI*2),y:-14+12*Math.sin((k-12)/10*Math.PI*2)};
  else point={x:-4+43*Math.cos(Math.PI+(k-22)/13*Math.PI),y:39+25*Math.sin(Math.PI+(k-22)/13*Math.PI)};
 }else{
  if(k<16)point={x:41*Math.cos(k/16*Math.PI*2),y:41*Math.sin(k/16*Math.PI*2)};
  else if(k<26)point={x:38*Math.cos((k-16)/10*Math.PI*2),y:15*Math.sin((k-16)/10*Math.PI*2)};
  else point=polylinePoint([[-28,-8],[-10,-24],[5,-17],[17,-4],[29,4],[10,13],[-4,30],[-17,13],[-28,-8]],(k-26)/9);
 }
 return {x:center.x+point.x,y:center.y+point.y};
};

const papers=Array.from({length:32},(_,i)=>{
 const column=i%8,row=Math.floor(i/8);
 return {x:155+column*230+(rand(i,1)-.5)*34,y:422+row*148+(rand(i,2)-.5)*26};
});

function Counter({value,frame}){
 const highest=Math.floor(Math.log10(Math.max(1,Math.floor(value))));
 const places=Array.from({length:highest+1},(_,i)=>highest-i);
 const begins=[12,29,49,69,89];
 return <div style={{display:'flex',justifyContent:'center',fontSize:148,letterSpacing:-5,lineHeight:'170px',fontVariantNumeric:'tabular-nums'}}>
  {places.map(place=>{
   const power=10**place,phase=Math.floor(value/power)+Math.max(0,value%power-(power-1)),digit=Math.floor(phase)%10,shift=phase%1;
   const reveal=place===0?1:p(frame,begins[place],begins[place]+5);
   return <React.Fragment key={place}>
    <div style={{width:96*reveal,height:170,overflow:'hidden',position:'relative',opacity:reveal}}>
     {[0,1].map(k=><div key={k} style={{position:'absolute',top:(k-shift)*170,left:0,right:0}}>{(digit+k)%10}</div>)}
    </div>
    {place===3?<div style={{width:44*p(frame,69,74),opacity:p(frame,69,74),overflow:'hidden'}}>,</div>:null}
   </React.Fragment>;
  })}
  <div style={{width:86*p(frame,105,113),opacity:p(frame,105,113),overflow:'hidden'}}>+</div>
 </div>;
}

const PaperOutline=({x,y,scale,opacity})=><g opacity={opacity} transform={`translate(${x} ${y}) scale(${scale})`}>
 <path d="M -36 -49 H 13 L 36 -26 V 49 H -36 Z" fill={BG} stroke="#81928c" strokeWidth={2/scale}/>
 <path d="M 13 -49 V -26 H 36" fill="none" stroke="#81928c" strokeWidth={2/scale}/>
</g>;

export const Opening=({balancedTitles=false,wideTitles=false,solutionReveal=false,narrativeRefinement=false,balancedGraphLayout=false,timingTightening=false,continuousMorph=false,animatedEllipsis=false,singleActivation=false,constructAreas=false,sharpenedReveal=false,nonRepeatingPulse=false,refinedNarrative=false,integratedNarrative=false,compactTopTitles=false,alignedSingleLineTitles=false,balancedNarrativeTiming=false,bottleneckCopy=false,remainsBottleneckCopy=false,indefiniteBottleneckCopy=false,findingsMapCopy=false,dualSidedGraphFormation=false,compoundNames,earlySolutionTitle=false,totalPaperCount=21000})=>{
 const rawFrame=useCurrentFrame();
 const f=timingTightening?(rawFrame<118?rawFrame*136/118:rawFrame+18):rawFrame;
 const displayNames=compoundNames??names;
 const bottomStart=displayNames.length-compounds.length;
 const openingTitleSize=compactTopTitles?96:100;
 const scroll=interpolate(f,solutionReveal?[520,608]:[500,574],[bottomStart*130,0],{...ease,easing:Easing.bezier(.45,0,.55,1)});
 const rowY=i=>370+i*130-scroll;
 const areaY=j=>(balancedGraphLayout?370:300)+j*(balancedGraphLayout?58:66);
 const visible=i=>{
  const y=rowY(i);
  return Math.min(1,Math.max(0,(y-322)/40),Math.max(0,(1005-y)/55));
 };
 return <Stage>
  <Growth frame={f} morphToAreas={continuousMorph} syncArrow={timingTightening} constructionTiming={constructAreas}/>
  <Svg>
   {Array.from({length:continuousMorph?480:256},(_,i)=>{
    const particleCount=continuousMorph?480:256;
    const source=paperOrigins[Math.floor(i*paperOrigins.length/particleCount)];
    const areaIndex=i%scaleCenters.length,center=scaleCenters[areaIndex];
    const angle=rand(i,3)*Math.PI*2,radius=18+rand(i,4)*48;
    const target=constructAreas?iconParticleTarget(areaIndex,Math.floor(i/scaleCenters.length)):{x:center.x+Math.cos(angle)*radius,y:center.y+Math.sin(angle)*radius};
    const targetX=target.x,targetY=target.y;
    const gather=interpolate(f,constructAreas?[148+areaIndex*3+rand(i,5)*6,176+areaIndex*6+rand(i,6)*6]:continuousMorph?[122+rand(i,5)*10,190+rand(i,6)*16]:[144+rand(i,5)*10,190+rand(i,6)*18],[0,1],smooth);
    const x=bez(source.x,mix(source.x,targetX,.2),mix(source.x,targetX,.82),targetX,gather);
    const y=bez(source.y,source.y,targetY,targetY,gather);
    const particleIn=constructAreas?p(f,144+rand(i,7)*5,152+rand(i,8)*5):continuousMorph?p(f,110+rand(i,7)*8,122+rand(i,8)*8):p(f,132,148);
    const particleOut=constructAreas?p(f,178+areaIndex*6,196+areaIndex*6):continuousMorph?p(f,214,234):p(f,208,226);
    return <circle key={i} cx={x} cy={y} r={mix(continuousMorph?2.7:2.4,1.6,gather)} fill={center.color} opacity={particleIn*(continuousMorph ? .82 : .58)*(1-particleOut)}/>;
   })}
   <ResearchScale frame={f} continuousTransform={continuousMorph} constructFromParticles={constructAreas}/>
   {papers.map((paper,i)=>{
    const origin=(i%8+Math.floor(i/8)*3)%scaleCenters.length;
    const source=scaleCenters[origin];
    const scatter=interpolate(f,continuousMorph?[274+origin*2,312+origin*2]:[280+origin*2,314+origin*2],[0,1],smooth);
    const x=bez(source.x,source.x,paper.x,paper.x,scatter),y=bez(source.y,source.y,paper.y,paper.y,scatter);
    const paperReveal=continuousMorph?p(f,264+origin*2,278+origin*2):scatter;
    const dim=solutionReveal?mix(1,.42,p(f,440,450)):1;
    const exit=solutionReveal?p(f,448+(i%5)*1.3,468+(i%5)*1.3):p(f,430+(i%5)*2,466+(i%5)*2);
    const settle=solutionReveal?mix(1,.97,p(f,440,452)):1;
    return <PaperOutline key={i} x={x} y={y} scale={mix(continuousMorph ? .24 : .34,1,scatter)*settle} opacity={paperReveal*dim*(1-exit)}/>;
   })}
   {papers.flatMap((paper,paperIndex)=>Array.from({length:dualSidedGraphFormation?4:3},(_,lineIndex)=>{
    const fragmentCount=dualSidedGraphFormation?4:3;
    const index=paperIndex*fragmentCount+lineIndex;
    const areaIndex=(paperIndex*3+lineIndex*4)%areas.length;
    const compoundIndex=bottomStart+(paperIndex*2+lineIndex)%compounds.length;
    const formsCompound=dualSidedGraphFormation&&lineIndex<2;
    const origin=(paperIndex%8+Math.floor(paperIndex/8)*3)%scaleCenters.length;
    const source=scaleCenters[origin];
    const scatter=interpolate(f,continuousMorph?[274+origin*2,312+origin*2]:[280+origin*2,314+origin*2],[0,1],smooth);
    const paperReveal=continuousMorph?p(f,264+origin*2,278+origin*2):scatter;
    const paperX=bez(source.x,source.x,paper.x,paper.x,scatter),paperY=bez(source.y,source.y,paper.y,paper.y,scatter);
    const paperScale=mix(.34,1,scatter);
    const embeddedX=paperX+((lineIndex%2)*7-3)*paperScale,embeddedY=paperY+((lineIndex-(fragmentCount-1)/2)*16)*paperScale;
    const start=solutionReveal?448+rand(index,4)*10:434+rand(index,4)*19;
    const end=solutionReveal?480+rand(index,5)*12:482+rand(index,5)*24;
    const travel=interpolate(f,[start,end],[0,1],smooth);
    const targetX=(formsCompound?620:1220)+(rand(index,6)-.5)*(formsCompound?28:16);
    const targetY=(formsCompound?rowY(compoundIndex):areaY(areaIndex))+(rand(index,7)-.5)*(formsCompound?30:20);
    const x=bez(embeddedX,mix(embeddedX,targetX,.22),mix(embeddedX,targetX,.8),targetX,travel);
    const y=bez(embeddedY,embeddedY,targetY,targetY,travel);
    const width=mix((lineIndex===1?42:32)*paperScale,5,travel),height=mix(5*paperScale,4,travel);
    return <rect key={lineIndex} x={x-width/2} y={y-height/2} width={width} height={height} rx={height/2} fill={formsCompound?'#61c7ac':areas[areaIndex].color} opacity={paperReveal*.82*(1-p(f,solutionReveal?516:506,solutionReveal?538:536))}/>;
   }))}
   <KnowledgeGraph
    frame={f}
    names={displayNames}
    rowY={rowY}
    visibility={visible}
    formation={p(f,solutionReveal?486:500,solutionReveal?514:560)}
    nodeGrowth={solutionReveal?interpolate(f,[478,494,502],[0,1.16,1],ease):p(f,480,500)}
    labelGrowth={p(f,solutionReveal?490:480,solutionReveal?508:500)}
    areaNodeStart={solutionReveal?476:456}
    areaLabelStart={solutionReveal?490:476}
    areaStep={solutionReveal ? .8 : 2}
    areaNodeDuration={solutionReveal?18:28}
    areaLabelDuration={solutionReveal?18:30}
    areaYStart={balancedGraphLayout?370:300}
    areaGap={balancedGraphLayout?58:66}
    id={solutionReveal?'formation-v33-':'formation-v30-'}
   />
   {solutionReveal?displayNames.flatMap((name,i)=>areas.map((area,j)=>{
    const cell=broad.cells.find(item=>item.compound===name.toLowerCase()&&item.area===area.name);
    if(!cell?.count)return null;
    const activation=p(f,singleActivation?500:506,singleActivation?522:532)*(nonRepeatingPulse ? .92 : 1);
    return <path key={'activation-'+i+'-'+j} d={curve(620,rowY(i),1220,areaY(j))} fill="none" stroke={area.color} strokeWidth={5+Math.sqrt(cell.count)*.25} strokeLinecap="round" pathLength="1" strokeDasharray=".075 .925" strokeDashoffset={1-activation} opacity={visible(i)*p(f,singleActivation?496:502,singleActivation?502:508)*(1-p(f,nonRepeatingPulse?514:singleActivation?516:532,nonRepeatingPulse?520:singleActivation?522:540))*.9}/>;
   })):null}
   <circle cx={mix(1470,1220,p(f,solutionReveal?632:594,solutionReveal?656:618))} cy={mix(420,areaY(0),p(f,solutionReveal?632:594,solutionReveal?656:618))} r={mix(10,28,p(f,solutionReveal?659:621,solutionReveal?671:633))} fill="none" stroke="#dff9ef" strokeWidth="2" opacity={p(f,solutionReveal?628:590,solutionReveal?639:601)*(1-p(f,solutionReveal?672:634,solutionReveal?678:640))}/>
  </Svg>
  <Interactive.Div name="Total research papers" style={{position:'absolute',left:280,width:620,top:365,textAlign:'center',opacity:interpolate(f,[10,18,142,160],[0,1,1,0],ease)}}>
   <Counter frame={f} value={interpolate(f,[12,28,48,68,88,105],[1,9,99,999,9999,totalPaperCount],{...ease,easing:Easing.linear})}/>
   <div style={{fontSize:64,marginTop:12}}>research papers</div>
  </Interactive.Div>
  {solutionReveal?<React.Fragment>
   <Title opacity={p(f,0,10)*(1-p(f,constructAreas?150:142,constructAreas?166:158))} size={openingTitleSize}>{narrativeRefinement?'Psychedelic science is growing fast':'Psychedelic research is growing fast'}</Title>
   <Title opacity={p(f,constructAreas?174:166,constructAreas?190:182)*(1-p(f,292,308))} size={openingTitleSize}>{integratedNarrative?'…across many research areas':refinedNarrative?'It spans many research areas':'Across many research areas'}</Title>
   <Title opacity={p(f,310,326)*(1-p(f,420,434))} size={openingTitleSize}>{indefiniteBottleneckCopy?<React.Fragment>But making sense of it all remains<br/>a bottleneck</React.Fragment>:remainsBottleneckCopy?<React.Fragment>But making sense of it all remains<br/>the bottleneck</React.Fragment>:bottleneckCopy?<React.Fragment>But making sense of it all<br/>becomes the bottleneck</React.Fragment>:integratedNarrative?<React.Fragment>But seeing how the findings<br/>fit together is still difficult</React.Fragment>:narrativeRefinement?<React.Fragment>Keeping up still means<br/>{sharpenedReveal&&!refinedNarrative?'synthesizing the literature yourself':'connecting findings yourself'}{animatedEllipsis?<span style={{display:'inline-flex',width:96}}>{[0,1,2].map(index=><span key={index} style={{opacity:p(f,344+index*7,352+index*7)}}>.</span>)}</span>:null}</React.Fragment>:<React.Fragment>But the findings remain scattered<br/>across papers</React.Fragment>}</Title>
   {sharpenedReveal&&!integratedNarrative?<Title center top={104} opacity={p(f,432,440)*(1-p(f,472,482))} size={116}>{refinedNarrative?'Now it comes together.':'Not anymore.'}</Title>:null}
   <Title top={70} opacity={p(f,earlySolutionTitle?434:498,earlySolutionTitle?446:506)*(1-p(f,balancedNarrativeTiming?620:588,balancedNarrativeTiming?634:602))} size={openingTitleSize}>{findingsMapCopy?<React.Fragment>Psychedelics Knowledge Graph<br/>organizes findings into one living map</React.Fragment>:integratedNarrative?<React.Fragment>Psychedelics Knowledge Graph<br/>organizes them into one living map</React.Fragment>:sharpenedReveal?<React.Fragment>Psychedelics Knowledge Graph<br/>brings findings into one living map</React.Fragment>:<React.Fragment>The Psychedelics Knowledge Graph<br/>connects findings across papers</React.Fragment>}</Title>
   <Title top={alignedSingleLineTitles?96:70} opacity={p(f,balancedNarrativeTiming?636:604,balancedNarrativeTiming?648:618)} size={openingTitleSize}>{narrativeRefinement?'So you can explore how it all connects':<React.Fragment>From study details to patterns<br/>across the field</React.Fragment>}</Title>
  </React.Fragment>:balancedTitles?<React.Fragment>
   <Title opacity={p(f,0,10)*(1-p(f,142,158))} size={100}>Psychedelic research is growing fast</Title>
   <Title opacity={p(f,166,182)*(1-p(f,292,308))} size={100}>Across many research areas</Title>
   <Title opacity={p(f,310,326)*(1-p(f,410,426))} size={100}>But the findings remain scattered<br/>across papers</Title>
   <Title top={70} opacity={p(f,424,440)*(1-p(f,552,568))} size={100}>{wideTitles?<React.Fragment>Now it’s all connected in a living<br/>knowledge graph</React.Fragment>:<React.Fragment>Now it’s all connected in a<br/>living knowledge graph</React.Fragment>}</Title>
   <Title top={70} opacity={p(f,570,586)} size={100}>{wideTitles?<React.Fragment>From study details to patterns<br/>across the field</React.Fragment>:<React.Fragment>From study details to<br/>patterns across the field</React.Fragment>}</Title>
  </React.Fragment>:<React.Fragment>
   <Title opacity={p(f,0,10)*(1-p(f,142,158))} size={88}>Psychedelic research is growing fast</Title>
   <Title top={66} opacity={p(f,166,182)*(1-p(f,292,308))} size={88}>Across many research areas</Title>
   <Title top={70} opacity={p(f,310,326)*(1-p(f,410,426))} size={88}>But the findings remain scattered<br/>across papers</Title>
   <Title top={70} opacity={p(f,424,440)*(1-p(f,552,568))} size={86}>Now it’s all connected<br/>in a living knowledge graph</Title>
   <Title top={70} opacity={p(f,570,586)} size={86}>From study details<br/>to patterns across the field</Title>
  </React.Fragment>}
 </Stage>;
};
