import React from 'react';
import {Easing,Interactive,interpolate,useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Paper,Node,Label,p,mix,ease,broad,BG} from '../product/shared';
import {KnowledgeGraph,compounds,overviewY,graphEdges} from './Graph';

const names=[...compounds,...broad.rows.map(r=>r.name).filter(n=>![...compounds,'(2R,6R)-hydroxynorketamine'].includes(n))];
const smooth={...ease,easing:Easing.bezier(.42,0,.58,1)};
const rand=(i,s)=>{const x=Math.sin(i*127.1+s*311.7)*43758.5453;return x-Math.floor(x);};
const bez=(a,b,c,d,t)=>(1-t)**3*a+3*(1-t)**2*t*b+3*(1-t)*t*t*c+t**3*d;
function Counter({value}){
 return <div style={{display:'flex',justifyContent:'center',fontSize:182,letterSpacing:-7,lineHeight:'198px',fontVariantNumeric:'tabular-nums'}}>
  {[4,3,2,1,0].map((place,i)=>{const power=10**place,phase=Math.floor(value/power)+Math.max(0,value%power-(power-1)),digit=Math.floor(phase)%10,shift=phase%1;return <React.Fragment key={place}><div style={{width:120,height:198,overflow:'hidden',position:'relative'}}>{[0,1].map(k=><div key={k} style={{position:'absolute',top:(k-shift)*198,left:0,right:0}}>{(digit+k)%10}</div>)}</div>{i===1?<div style={{width:54}}>,</div>:null}</React.Fragment>;})}
 </div>;
}
export const Opening=()=>{
 const f=useCurrentFrame(),growth=interpolate(f,[73,157],[0,1],smooth),camera=Math.exp(Math.log(6)*(1-growth)),focus=p(f,515,578);
 const scroll=interpolate(f,[320,485,512,578],[0,1910,1910,0],smooth);
 const rowY=i=>mix(370+i*108-scroll,overviewY(i),focus);
 const visible=i=>{
  const y=rowY(i),edge=Math.min(1,Math.max(0,(y-322)/40),Math.max(0,(1005-y)/55));
  return edge*(i<5?1:p(f,304,326)*(1-focus));
 };
 return <Stage><Svg>
  <KnowledgeGraph names={names} rowY={rowY} visibility={visible} formation={p(f,238,323)} nodeGrowth={p(f,281,325)} labelGrowth={p(f,281,322)} id="formation-"/>
  {Array.from({length:560},(_,i)=>{
   const born=p(f,65,83),drift=Math.min(f,184)*.012;
   const sx=960+(rand(i,1)*2100-1050+Math.sin(drift+rand(i,2)*6.28)*28)*camera;
   const sy=540+(rand(i,3)*1240-620+Math.cos(drift+rand(i,4)*6.28)*24)*camera;
   const edge=graphEdges[i%graphEdges.length],u=.08+.84*rand(i,9);
   const tx=bez(620,878,962,1220,u),ty=bez(rowY(edge.i),rowY(edge.i),300+edge.j*66,300+edge.j*66,u);
   const start=184+rand(i,10)*28,end=267+rand(i,11)*35;
   const travel=interpolate(f,[start,end],[0,1],smooth);
   const x=bez(sx,mix(sx,tx,.2),mix(sx,tx,.85),tx,travel);
   const y=bez(sy,sy,ty,ty,travel);
   const safe=(sy>320&&sy<680&&sx>490&&sx<1440)?.28:1;
   const morph=p(travel,.62,.96),alpha=born*(.18+rand(i,8)*.25)*mix(safe,1,travel);
   return <g key={i}>
    <Paper x={x} y={y} w={mix((27+rand(i,6)*20)*camera,6,travel)} rotate={mix((rand(i,7)-.5)*22,0,travel)} opacity={alpha*(1-morph)}/>
    <circle cx={x} cy={y} r={mix(3,1.8,p(f,285,327))} fill={edge.area.color} opacity={morph*.75*(1-p(f,293,329))}/>
   </g>;
  })}
  <circle cx={mix(1470,1220,p(f,662,690))} cy={mix(420,300,p(f,662,690))} r={mix(10,28,p(f,693,706))} fill="none" stroke="#dff9ef" strokeWidth="2" opacity={p(f,658,673)*(1-p(f,710,720))}/>
 </Svg>
 <Interactive.Div name="Project name opening" style={{position:'absolute',left:180,right:180,top:337,fontSize:132,lineHeight:1.02,letterSpacing:-6,textAlign:'center',opacity:interpolate(f,[0,12,58,77],[0,1,1,0],ease),translate:interpolate(f,[0,24],['0px 30px','0px 0px'],ease)}}>Psychedelics<br/><span style={{color:'#70cbb4'}}>Knowledge Graph</span></Interactive.Div>
 <Interactive.Div name="Increasing paper count" style={{position:'absolute',left:140,right:140,top:315,textAlign:'center',opacity:interpolate(f,[71,83,170,185],[0,1,1,0],ease)}}><Counter value={21735*growth}/><div style={{fontSize:82,marginTop:16}}>research papers</div></Interactive.Div>
 <Title opacity={p(f,182,206)} size={98}>From papers to connected knowledge</Title>
 </Stage>;
};
