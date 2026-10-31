import React from 'react';
import {Easing,Interactive,interpolate,useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Paper,Node,Label,p,mix,ease,broad,areas,BG} from '../product/shared';
import {KnowledgeGraph,compounds} from '../product-v12/Graph';

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
 const begins=[73,90,110,134,159];
 return <div style={{display:'flex',justifyContent:'center',fontSize:182,letterSpacing:-7,lineHeight:'198px',fontVariantNumeric:'tabular-nums'}}>
  {places.map(place=>{
   const power=10**place,phase=Math.floor(value/power)+Math.max(0,value%power-(power-1)),digit=Math.floor(phase)%10,shift=phase%1;
   const reveal=place===0?1:p(frame,begins[place],begins[place]+5);
   return <React.Fragment key={place}>
    <div style={{width:120*reveal,height:198,overflow:'hidden',position:'relative',opacity:reveal}}>
     {[0,1].map(k=><div key={k} style={{position:'absolute',top:(k-shift)*198,left:0,right:0}}>{(digit+k)%10}</div>)}
    </div>
    {place===3?<div style={{width:54*p(frame,134,139),opacity:p(frame,134,139),overflow:'hidden'}}>,</div>:null}
   </React.Fragment>;
  })}
  <div style={{width:108*p(frame,175,183),opacity:p(frame,175,183),overflow:'hidden'}}>+</div>
 </div>;
}
export const Opening=()=>{
 const f=useCurrentFrame(),growth=interpolate(f,[73,175],[0,1],smooth),camera=Math.exp(Math.log(6)*(1-growth));
 const scroll=interpolate(f,[308,446],[bottomStart*130,0],{...ease,easing:Easing.bezier(.45,0,.55,1)});
 const rowY=i=>370+i*130-scroll;
 const visible=i=>{
  const y=rowY(i),edge=Math.min(1,Math.max(0,(y-322)/40),Math.max(0,(1005-y)/55));
  return edge;
 };
 return <Stage><Svg>
  <KnowledgeGraph names={names} rowY={rowY} visibility={visible} formation={p(f,232,308)} nodeGrowth={p(f,271,309)} labelGrowth={p(f,271,306)} id="formation-"/>
  {Array.from({length:560},(_,i)=>{
   const born=p(f,65,83),drift=Math.min(f,185)*.012;
   const sx=960+(rand(i,1)*2100-1050+Math.sin(drift+rand(i,2)*6.28)*28)*camera;
   const sy=540+(rand(i,3)*1240-620+Math.cos(drift+rand(i,4)*6.28)*24)*camera;
   const edge=graphEdges[i%graphEdges.length],u=.08+.84*rand(i,9);
   const tx=bez(620,878,962,1220,u),ty=bez(rowY(edge.i),rowY(edge.i),300+edge.j*66,300+edge.j*66,u);
   const start=185+rand(i,10)*18,end=250+rand(i,11)*24;
   const travel=interpolate(f,[start,end],[0,1],smooth);
   const x=bez(sx,mix(sx,tx,.2),mix(sx,tx,.85),tx,travel);
   const y=bez(sy,sy,ty,ty,travel);
   const safe=(sy>320&&sy<680&&sx>490&&sx<1440)?.28:1;
   const morph=p(travel,.62,.96),alpha=born*(.18+rand(i,8)*.25)*mix(safe,1,travel);
   return <g key={i}>
    <Paper x={x} y={y} w={mix((27+rand(i,6)*20)*camera,6,travel)} rotate={mix((rand(i,7)-.5)*22,0,travel)} opacity={alpha*(1-morph)}/>
    <circle cx={x} cy={y} r={mix(3,1.8,p(f,275,311))} fill={edge.area.color} opacity={morph*.75*(1-p(f,283,313))}/>
   </g>;
  })}
  <circle cx={mix(1470,1220,p(f,462,486))} cy={mix(420,300,p(f,462,486))} r={mix(10,28,p(f,489,501))} fill="none" stroke="#dff9ef" strokeWidth="2" opacity={p(f,458,469)*(1-p(f,502,512))}/>
 </Svg>
 <Interactive.Div name="Project name opening" style={{position:'absolute',left:180,right:180,top:337,fontSize:132,lineHeight:1.02,letterSpacing:-6,textAlign:'center',opacity:interpolate(f,[0,12,58,77],[0,1,1,0],ease),translate:interpolate(f,[0,24],['0px 30px','0px 0px'],ease)}}>Psychedelics<br/><span style={{color:'#70cbb4'}}>Knowledge Graph</span></Interactive.Div>
 <Interactive.Div name="Increasing paper count" style={{position:'absolute',left:140,right:140,top:355,textAlign:'center',opacity:interpolate(f,[73,81,195,211],[0,1,1,0],ease)}}><Counter frame={f} value={interpolate(f,[73,89,109,133,158,175],[1,9,99,999,9999,21000],{...ease,easing:Easing.linear})}/><div style={{fontSize:82,marginTop:16}}>research papers</div></Interactive.Div>
 <Title opacity={p(f,66,80)*(1-p(f,194,207))} size={90}>Psychedelic science is growing fast</Title>
 <Interactive.Div name="Interdisciplinary scope of psychedelic science" style={{position:'absolute',left:140,right:140,top:748,textAlign:'center',fontSize:68,letterSpacing:-2,color:'#b1c4b9',opacity:interpolate(f,[98,112,194,207],[0,1,1,0],ease)}}>From molecules to minds and society</Interactive.Div>
 <Title opacity={p(f,208,230)*(1-p(f,474,488))} size={94}>Organize and connect the research</Title>
 <Title opacity={p(f,489,507)} size={98}>Explore the connections</Title>
 </Stage>;
};
