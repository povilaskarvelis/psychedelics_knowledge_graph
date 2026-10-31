import React from 'react';
import {Easing,Interactive,interpolate,useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Paper,Node,Label,p,mix,ease,broad,BG} from '../product/shared';
import {Overview} from '../product-v9/Graph';

const names=['Ketamine','Psilocybin','MDMA',...broad.rows.map(r=>r.name).filter(n=>!['Ketamine','Psilocybin','MDMA','(2R,6R)-hydroxynorketamine'].includes(n))];
const smooth={...ease,easing:Easing.bezier(.42,0,.58,1)};
const rand=(i,s)=>{const x=Math.sin(i*127.1+s*311.7)*43758.5453;return x-Math.floor(x);};
const bez=(a,b,c,d,t)=>(1-t)**3*a+3*(1-t)**2*t*b+3*(1-t)*t*t*c+t**3*d;
function Counter({value}){
 return <div style={{display:'flex',justifyContent:'center',fontSize:182,letterSpacing:-7,lineHeight:'198px',fontVariantNumeric:'tabular-nums'}}>
  {[4,3,2,1,0].map((place,i)=>{const power=10**place,phase=Math.floor(value/power)+Math.max(0,value%power-(power-1)),digit=Math.floor(phase)%10,shift=phase%1;return <React.Fragment key={place}><div style={{width:120,height:198,overflow:'hidden',position:'relative'}}>{[0,1].map(k=><div key={k} style={{position:'absolute',top:(k-shift)*198,left:0,right:0}}>{(digit+k)%10}</div>)}</div>{i===1?<div style={{width:54}}>,</div>:null}</React.Fragment>;})}
 </div>;
}
export const Opening=()=>{
 const f=useCurrentFrame(),growth=interpolate(f,[73,157],[0,1],smooth),camera=Math.exp(Math.log(6)*(1-growth)),zoom=p(f,515,578);
 const scroll=interpolate(f,[290,485,512,578],[0,1910,1910,0],smooth);
 const nx=mix(980,620,zoom),rowY=i=>mix(338+i*108-scroll,410+i*210,zoom);
 const travel=interpolate(f,[184,285],[0,1],smooth);
 return <Stage><Svg>
  <defs><linearGradient id="list-fade-v10" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="black"/><stop offset=".075" stopColor="white"/><stop offset=".87" stopColor="white"/><stop offset="1" stopColor="black"/></linearGradient><mask id="list-safe-v10"><rect x="0" y="285" width="1920" height="735" fill="url(#list-fade-v10)"/></mask></defs>
  {Array.from({length:560},(_,i)=>{
   const born=p(f,65,83);
   const t=Math.min(f,184),drift=t*.012;
   const sx=960+(rand(i,1)*2100-1050+Math.sin(drift+rand(i,2)*6.28)*28)*camera;
   const sy=540+(rand(i,3)*1240-620+Math.cos(drift+rand(i,4)*6.28)*24)*camera;
   const lane=Math.floor(rand(i,5)*names.length),targetY=338+lane*108;
   const x=bez(sx,sx+(980-sx)*.35,1120,980,travel);
   const y=bez(sy,sy,targetY,targetY,travel);
   const safe=(sy>320&&sy<680&&sx>490&&sx<1440)?.28:1;
   return <Paper key={i} x={x} y={y} w={mix((27+rand(i,6)*20)*camera,22,travel)} rotate={mix((rand(i,7)-.5)*22,0,travel)} opacity={born*(.18+rand(i,8)*.25)*mix(safe,1,travel)*(1-p(travel,.92,1))}/>;
  })}
  <g mask="url(#list-safe-v10)">
   {names.map((name,i)=><g key={name} opacity={p(f,178,206)*(i<3?1:1-zoom)*(1-p(f,570,590))}><Node x={nx} y={rowY(i)} r={mix(19,24,zoom)}/><Label x={nx-42} y={rowY(i)} size={mix(62,56,zoom)} anchor="end">{name}</Label>{[0,1,2,3].map(k=><Paper key={k} x={1048+k*47} y={338+i*108-scroll} w={35} opacity={p(f,272,294)*(1-zoom)*.7}/>)}</g>)}
  </g>
  <g opacity={p(f,573,592)}><Overview frame={f} reveal={585}/></g>
  <circle cx={mix(1470,1220,p(f,662,690))} cy={mix(420,300,p(f,662,690))} r={mix(10,28,p(f,693,706))} fill="none" stroke="#dff9ef" strokeWidth="2" opacity={p(f,658,673)*(1-p(f,710,720))}/>
 </Svg>
 <Interactive.Div name="Project name opening" style={{position:'absolute',left:180,right:180,top:337,fontSize:132,lineHeight:1.02,letterSpacing:-6,textAlign:'center',opacity:interpolate(f,[0,12,58,77],[0,1,1,0],ease),translate:interpolate(f,[0,24],['0px 30px','0px 0px'],ease)}}>Psychedelics<br/><span style={{color:'#70cbb4'}}>Knowledge Graph</span></Interactive.Div>
 <Interactive.Div name="Increasing paper count" style={{position:'absolute',left:140,right:140,top:315,textAlign:'center',opacity:interpolate(f,[71,83,170,185],[0,1,1,0],ease)}}><Counter value={21735*growth}/><div style={{fontSize:82,marginTop:16}}>research papers</div></Interactive.Div>
 <div style={{position:'absolute',top:0,left:0,right:0,height:290,background:BG,opacity:p(f,172,195)*(1-p(f,548,570))}}/>
 <Title opacity={p(f,182,206)} size={98}>From papers to connected knowledge</Title>
 </Stage>;
};
