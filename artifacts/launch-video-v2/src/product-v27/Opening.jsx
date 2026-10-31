import React from 'react';
import {Easing,Interactive,interpolate,useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,p,mix,ease,broad,areas,BG} from '../product/shared';
import {Growth} from '../product-v25/Growth';
import {KnowledgeGraph,compounds} from '../product-v26/Graph';
import {ResearchScale} from './ResearchScale';

const remaining=broad.rows.map(row=>row.name).filter(name=>![...compounds,'(2R,6R)-hydroxynorketamine'].includes(name));
const names=[...compounds,...remaining];
const bottomStart=names.length-compounds.length;
const smooth={...ease,easing:Easing.bezier(.42,0,.58,1)};
const rand=(i,s)=>{const value=Math.sin(i*127.1+s*311.7)*43758.5453;return value-Math.floor(value);};
const bez=(a,b,c,d,t)=>(1-t)**3*a+3*(1-t)**2*t*b+3*(1-t)*t*t*c+t**3*d;

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

const PaperOutline=({x,y,opacity})=><g opacity={opacity}>
 <path d={`M ${x-36} ${y-49} H ${x+13} L ${x+36} ${y-26} V ${y+49} H ${x-36} Z`} fill={BG} stroke="#81928c" strokeWidth="2"/>
 <path d={`M ${x+13} ${y-49} V ${y-26} H ${x+36}`} fill="none" stroke="#81928c" strokeWidth="2"/>
</g>;

export const createOpening=(Scale=ResearchScale,breadthLines=['From molecular mechanisms','to public health'])=>()=>{
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
   <Scale frame={f}/>
   {papers.map((paper,i)=>{
    const enter=p(f,300+(i%8)*2+Math.floor(i/8)*3,320+(i%8)*2+Math.floor(i/8)*3);
    return <PaperOutline key={i} x={paper.x} y={paper.y} opacity={enter*(1-p(f,430+(i%5)*2,466+(i%5)*2))}/>;
   })}
   {papers.flatMap((paper,paperIndex)=>Array.from({length:3},(_,lineIndex)=>{
    const index=paperIndex*3+lineIndex;
    const areaIndex=(paperIndex*3+lineIndex*4)%areas.length;
    const enter=p(f,305+(paperIndex%8)*2+Math.floor(paperIndex/8)*3,325+(paperIndex%8)*2+Math.floor(paperIndex/8)*3);
    const startX=paper.x+(lineIndex===1?4:-3),startY=paper.y-19+lineIndex*19;
    const start=434+rand(index,4)*19,end=482+rand(index,5)*24;
    const travel=interpolate(f,[start,end],[0,1],smooth);
    const targetX=1220+(rand(index,6)-.5)*16,targetY=300+areaIndex*66+(rand(index,7)-.5)*20;
    const x=bez(startX,mix(startX,targetX,.22),mix(startX,targetX,.8),targetX,travel);
    const y=bez(startY,startY,targetY,targetY,travel);
    const width=mix(lineIndex===1?42:32,5,travel),height=mix(5,4,travel);
    return <rect key={lineIndex} x={x-width/2} y={y-height/2} width={width} height={height} rx={height/2} fill={areas[areaIndex].color} opacity={enter*.82*(1-p(f,506,536))}/>;
   }))}
   <KnowledgeGraph frame={f} names={names} rowY={rowY} visibility={visible} formation={p(f,500,560)} nodeGrowth={p(f,480,500)} labelGrowth={p(f,480,500)} id="formation-v27-"/>
   <circle cx={mix(1470,1220,p(f,594,618))} cy={mix(420,300,p(f,594,618))} r={mix(10,28,p(f,621,633))} fill="none" stroke="#dff9ef" strokeWidth="2" opacity={p(f,590,601)*(1-p(f,634,640))}/>
  </Svg>
  <Interactive.Div name="Total research papers" style={{position:'absolute',left:280,width:620,top:365,textAlign:'center',opacity:interpolate(f,[10,18,142,160],[0,1,1,0],ease)}}>
   <Counter frame={f} value={interpolate(f,[12,28,48,68,88,105],[1,9,99,999,9999,21000],{...ease,easing:Easing.linear})}/>
   <div style={{fontSize:64,marginTop:12}}>research papers</div>
  </Interactive.Div>
  <Title opacity={p(f,0,10)*(1-p(f,142,158))} size={88}>Psychedelic research is growing fast</Title>
  <Title top={66} opacity={p(f,166,182)*(1-p(f,292,308))} size={88}>{breadthLines.map((line,index)=><React.Fragment key={line}>{index>0?<br/>:null}{line}</React.Fragment>)}</Title>
  <Title top={70} opacity={p(f,310,326)*(1-p(f,410,426))} size={88}>But the findings remain scattered<br/>across papers</Title>
  <Title top={70} opacity={p(f,424,440)*(1-p(f,552,568))} size={86}>Now it’s all connected<br/>in a living knowledge graph</Title>
  <Title top={70} opacity={p(f,570,586)} size={86}>From study details<br/>to patterns across the field</Title>
 </Stage>;
};

export const Opening=createOpening();
