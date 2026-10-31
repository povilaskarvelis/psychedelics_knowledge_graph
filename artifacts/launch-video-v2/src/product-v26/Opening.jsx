import React from 'react';
import {Easing,Interactive,interpolate,useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Paper,Node,Label,p,mix,ease,broad,areas} from '../product/shared';
import {Growth,paperOrigins} from '../product-v25/Growth';
import {KnowledgeGraph,compounds} from './Graph';

const remaining=broad.rows.map(row=>row.name).filter(name=>![...compounds,'(2R,6R)-hydroxynorketamine'].includes(name));
const names=[...compounds,...remaining];
const bottomStart=names.length-compounds.length;
const smooth={...ease,easing:Easing.bezier(.42,0,.58,1)};
const rand=(i,s)=>{const value=Math.sin(i*127.1+s*311.7)*43758.5453;return value-Math.floor(value);};
const bez=(a,b,c,d,t)=>(1-t)**3*a+3*(1-t)**2*t*b+3*(1-t)*t*t*c+t**3*d;

const topics=[
 {label:'Targets',x:260,y:570,color:areas[9].color},
 {label:'Brain',x:610,y:700,color:areas[7].color},
 {label:'Experience',x:960,y:570,color:areas[4].color},
 {label:'Clinical',x:1310,y:700,color:areas[0].color},
 {label:'Real-world use',x:1660,y:570,color:areas[6].color},
];

// Each of the product's ten research areas belongs to one of the five broad
// clusters above. The particles visibly split from these clusters into the
// final research-area destinations before the compound links are drawn.
const areaToTopic=[3,3,1,2,2,3,4,1,0,0];

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

export const Opening=()=>{
 const f=useCurrentFrame();
 const scroll=interpolate(f,[500,574],[bottomStart*130,0],{...ease,easing:Easing.bezier(.45,0,.55,1)});
 const rowY=i=>370+i*130-scroll;
 const visible=i=>{
  const y=rowY(i);
  return Math.min(1,Math.max(0,(y-322)/40),Math.max(0,(1005-y)/55));
 };
 return <Stage>
  <Growth frame={f}/>
  <Svg>
   {topics.map((topic,j)=>{
    const enter=p(f,178+j*5,204+j*5);
    const leave=p(f,416+j*2,458+j*2);
    return <g key={topic.label} opacity={enter*(1-leave)}>
     <circle cx={topic.x} cy={topic.y} r={mix(22,42,enter)} fill={topic.color} fillOpacity=".12" stroke={topic.color} strokeWidth="3"/>
     <circle cx={topic.x} cy={topic.y} r={mix(48,76,enter)} fill="none" stroke={topic.color} strokeWidth="2" opacity=".22"/>
     <Label x={topic.x} y={topic.y+116} size={50} anchor="middle">{topic.label}</Label>
    </g>;
   })}
   {Array.from({length:420},(_,i)=>{
    const born=p(f,148,166);
    const {x:sx,y:sy}=paperOrigins[Math.floor(i*paperOrigins.length/420)];
    const areaIndex=i%areas.length,topic=topics[areaToTopic[areaIndex]];
    const angle=rand(i,3)*Math.PI*2,radius=54+rand(i,4)*96;
    const clusterX=topic.x+Math.cos(angle)*radius;
    const clusterY=topic.y+Math.sin(angle)*radius*.58;
    const gather=interpolate(f,[160+rand(i,5)*22,216+rand(i,6)*26],[0,1],smooth);
    const split=interpolate(f,[423+rand(i,7)*18,476+rand(i,8)*25],[0,1],smooth);
    const targetX=1220+(rand(i,9)-.5)*16;
    const targetY=300+areaIndex*66+(rand(i,10)-.5)*22;
    const gatheredX=bez(sx,mix(sx,clusterX,.28),mix(sx,clusterX,.82),clusterX,gather);
    const gatheredY=bez(sy,sy,clusterY,clusterY,gather);
    const x=bez(gatheredX,mix(gatheredX,targetX,.2),mix(gatheredX,targetX,.82),targetX,split);
    const y=bez(gatheredY,gatheredY,targetY,targetY,split);
    const morph=p(split,.58,.94);
    return <g key={i} opacity={born*(1-p(f,506,536))}>
     <Paper x={x} y={y} w={mix(16,8,split)} rotate={mix((rand(i,11)-.5)*25,0,split)} opacity={(.26+rand(i,12)*.28)*(1-morph)}/>
     <circle cx={x} cy={y} r={mix(2.4,3.4,morph)} fill={areas[areaIndex].color} opacity={morph*.9}/>
    </g>;
   })}
   <KnowledgeGraph frame={f} names={names} rowY={rowY} visibility={visible} formation={p(f,500,560)} nodeGrowth={p(f,480,500)} labelGrowth={p(f,480,500)} id="formation-v26-"/>
   <circle cx={mix(1470,1220,p(f,594,618))} cy={mix(420,300,p(f,594,618))} r={mix(10,28,p(f,621,633))} fill="none" stroke="#dff9ef" strokeWidth="2" opacity={p(f,590,601)*(1-p(f,634,640))}/>
  </Svg>
  <Interactive.Div name="Total research papers" style={{position:'absolute',left:280,width:620,top:365,textAlign:'center',opacity:interpolate(f,[10,18,142,160],[0,1,1,0],ease)}}>
   <Counter frame={f} value={interpolate(f,[12,28,48,68,88,105],[1,9,99,999,9999,21000],{...ease,easing:Easing.linear})}/>
   <div style={{fontSize:64,marginTop:12}}>research papers</div>
  </Interactive.Div>
  <Title opacity={p(f,0,10)*(1-p(f,142,158))} size={88}>Psychedelic research is growing fast</Title>
  <Title opacity={p(f,168,184)*(1-p(f,292,308))} size={90}>Across many areas of research</Title>
  <Title top={70} opacity={p(f,310,326)*(1-p(f,410,426))} size={88}>But the findings remain scattered<br/>across papers</Title>
  <Title top={70} opacity={p(f,424,440)*(1-p(f,552,568))} size={86}>Now it’s all connected<br/>in a living knowledge graph</Title>
  <Title top={70} opacity={p(f,570,586)} size={86}>From study details<br/>to patterns across the field</Title>
 </Stage>;
};
