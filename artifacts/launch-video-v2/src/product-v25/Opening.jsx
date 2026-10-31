import React from 'react';
import {Easing,Interactive,interpolate,useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Paper,Node,Label,p,mix,ease,broad,areas,BG} from '../product/shared';
import {Growth, paperOrigins} from './Growth';
import {KnowledgeGraph,compounds} from './Graph';

// Preserve the original top-first order; the viewport begins at the bottom.
const remaining=broad.rows.map(r=>r.name).filter(n=>![...compounds,'(2R,6R)-hydroxynorketamine'].includes(n));
const names=[...compounds,...remaining];
const bottomStart=names.length-compounds.length;
const graphEdges=names.slice(bottomStart).flatMap((name,k)=>areas.map((area,j)=>({i:bottomStart+k,j,area,count:broad.cells.find(c=>c.compound===name.toLowerCase()&&c.area===area.name)?.count||0}))).filter(e=>e.count>0);
const smooth={...ease,easing:Easing.bezier(.42,0,.58,1)};
const rand=(i,s)=>{const x=Math.sin(i*127.1+s*311.7)*43758.5453;return x-Math.floor(x);};
const bez=(a,b,c,d,t)=>(1-t)**3*a+3*(1-t)**2*t*b+3*(1-t)*t*t*c+t**3*d;
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
 const scroll=interpolate(f,[308,446],[bottomStart*130,0],{...ease,easing:Easing.bezier(.45,0,.55,1)});
 const rowY=i=>370+i*130-scroll;
 const visible=i=>{
  const y=rowY(i),edge=Math.min(1,Math.max(0,(y-322)/40),Math.max(0,(1005-y)/55));
  return edge;
 };
 return <Stage><Growth frame={f}/><Svg>
  {areas.map((area,j)=>{
   const pulse=p(f,245+j*2,255+j*2)*(1-p(f,270+j*2,286+j*2));
   return <circle key={area.name} cx="1220" cy={300+j*66} r={mix(18,44,pulse)} fill="none" stroke={area.color} strokeWidth="3" opacity={pulse*.42}/>;
  })}
  <KnowledgeGraph frame={f} names={names} rowY={rowY} visibility={visible} formation={p(f,238,308)} nodeGrowth={p(f,271,309)} labelGrowth={p(f,271,306)} id="formation-"/>
  {Array.from({length:560},(_,i)=>{
   const born=p(f,166,181);
   const {x:sx,y:sy}=paperOrigins[i];
   const edge=graphEdges[i%graphEdges.length],u=i%5===0?1:.08+.84*rand(i,9);
   const tx=bez(620,878,962,1220,u),ty=bez(rowY(edge.i),rowY(edge.i),300+edge.j*66,300+edge.j*66,u);
   const start=185+rand(i,10)*18,end=250+rand(i,11)*24;
   const travel=interpolate(f,[start,end],[0,1],smooth);
   const x=bez(sx,mix(sx,tx,.2),mix(sx,tx,.85),tx,travel);
   const y=bez(sy,sy,ty,ty,travel);
   const safe=(sy>320&&sy<680&&sx>490&&sx<1440)?.28:1;
   const morph=p(travel,.62,.96),alpha=born*(.18+rand(i,8)*.25)*mix(safe,1,travel);
   return <g key={i}>
    <Paper x={x} y={y} w={mix(12,6,travel)+12*Math.sin(Math.PI*travel)} rotate={mix((rand(i,7)-.5)*22,0,travel)} opacity={alpha*(1-morph)}/>
    <circle cx={x} cy={y} r={mix(3,1.8,p(f,275,311))} fill={edge.area.color} opacity={morph*.92*(1-p(f,296,326))}/>
   </g>;
  })}
  <circle cx={mix(1470,1220,p(f,462,486))} cy={mix(420,300,p(f,462,486))} r={mix(10,28,p(f,489,501))} fill="none" stroke="#dff9ef" strokeWidth="2" opacity={p(f,458,469)*(1-p(f,502,512))}/>
 </Svg>
 <Interactive.Div name="Total research papers" style={{position:'absolute',left:280,width:620,top:365,textAlign:'center',opacity:interpolate(f,[10,18,164,185],[0,1,1,0],ease)}}><Counter frame={f} value={interpolate(f,[12,28,48,68,88,105],[1,9,99,999,9999,21000],{...ease,easing:Easing.linear})}/><div style={{fontSize:64,marginTop:12}}>research papers</div></Interactive.Div>
 <Title opacity={p(f,0,10)*(1-p(f,146,160))} size={88}>Psychedelic research is growing fast</Title>
 <Title top={202} opacity={p(f,32,46)*(1-p(f,146,160))} size={72}>Across many scientific domains</Title>
 <Title top={70} opacity={p(f,162,178)*(1-p(f,226,242))} size={84}>But keeping up still means<br/>piecing together paper after paper</Title>
 <Title top={70} opacity={p(f,236,252)*(1-p(f,404,420))} size={84}>Now, it comes together<br/>in a living knowledge graph</Title>
 <Title top={70} opacity={p(f,416,432)} size={86}>From study details<br/>to patterns across the field</Title>
 </Stage>;
};
