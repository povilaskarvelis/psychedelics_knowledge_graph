import React from 'react';
import {Easing,Interactive,interpolate,useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Paper,Node,Label,p,mix,ease,compounds,BG} from '../product/shared';
import {Overview} from './Graph';

const names=['Ketamine','Psilocybin','MDMA','LSD','S-ketamine','Ayahuasca','DMT','Salvinorin A','Ibogaine','Mescaline','5-MeO-DMT','Psilocin','MDA','2C-B','Nitrous oxide'];
function Counter({value}){
 return <div style={{display:'flex',justifyContent:'center',fontSize:182,letterSpacing:-7,lineHeight:'198px',fontVariantNumeric:'tabular-nums'}}>
  {[4,3,2,1,0].map((place,i)=>{
   const power=10**place;
   const phase=Math.floor(value/power)+Math.max(0,value%power-(power-1));
   const digit=Math.floor(phase)%10,shift=phase%1;
   return <React.Fragment key={place}><div style={{width:120,height:198,overflow:'hidden',position:'relative'}}>{[0,1].map(k=><div key={k} style={{position:'absolute',top:(k-shift)*198,left:0,right:0}}>{(digit+k)%10}</div>)}</div>{i===1?<div style={{width:54}}>,</div>:null}</React.Fragment>;
  })}
 </div>;
}
export const Opening=()=>{
 const f=useCurrentFrame(),wall=p(f,12,90),form=p(f,170,235),zoom=p(f,370,435);
 const scroll=interpolate(f,[250,350,370,435],[0,570,570,0],{...ease,easing:Easing.bezier(.4,0,.6,1)});
 const rowY=i=>mix(338+i*108-scroll,410+i*210,zoom);
 const nx=mix(980,620,zoom);
 return <Stage><Svg>
  <defs><linearGradient id="list-fade" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="black"/><stop offset=".055" stopColor="white"/><stop offset=".88" stopColor="white"/><stop offset="1" stopColor="black"/></linearGradient><mask id="list-safe"><rect x="0" y="285" width="1920" height="735" fill="url(#list-fade)"/></mask></defs>
  <g mask={f>170?'url(#list-safe)':undefined}>
   {Array.from({length:210},(_,i)=>{
    const lane=i%names.length,col=i%21,row=Math.floor(i/21),offset=(i*31)%65;
    const sx=960+(col-10)*mix(168,90,wall),sy=560+(row-4.5)*mix(194,96,wall);
    const q=p(f,174+offset*.5,222+offset*.7);
    const x=mix(sx,980,q),y=mix(sy,338+lane*108-scroll,q);
    return <Paper key={i} x={x} y={y} w={mix(mix(96,40,wall),32,q)} rotate={mix(i%9-4,0,q)} opacity={mix(.26,.65,form)*(1-p(f,220+offset*.7,234+offset*.7))}/>;
   })}
   {names.map((name,i)=><g key={name} opacity={p(f,172+i*1.5,194+i*1.5)*(i<3?1:1-zoom)*(1-p(f,430,450))}><Node x={nx} y={rowY(i)} r={mix(19,24,zoom)}/><Label x={nx-42} y={rowY(i)} size={mix(62,56,zoom)} anchor="end">{name}</Label>
    {Array.from({length:4},(_,k)=><Paper key={k} x={1048+k*47} y={338+i*108-scroll} w={35} opacity={p(f,232+k*10,250+k*10)*(1-zoom)*.7}/>)}</g>)}
  </g>
  <g opacity={p(f,430,450)}><Overview frame={f} reveal={440}/></g>
  <circle cx={mix(1470,1220,p(f,532,564))} cy={mix(420,300,p(f,532,564))} r={mix(10,28,p(f,567,584))} fill="none" stroke="#dff9ef" strokeWidth="2" opacity={p(f,530,545)*(1-p(f,590,600))}/>
 </Svg>
 <Interactive.Div name="Project name opening" style={{position:'absolute',left:180,right:180,top:337,fontSize:132,lineHeight:1.02,letterSpacing:-6,textAlign:'center',opacity:interpolate(f,[0,12,58,77],[0,1,1,0],ease),translate:interpolate(f,[0,24],['0px 30px','0px 0px'],ease)}}>Psychedelics<br/><span style={{color:'#70cbb4'}}>Knowledge Graph</span></Interactive.Div>
 <Interactive.Div name="Increasing paper count" style={{position:'absolute',left:140,right:140,top:315,textAlign:'center',opacity:interpolate(f,[71,83,166,183],[0,1,1,0],ease)}}><Counter value={21735*p(f,79,146)}/><div style={{fontSize:82,marginTop:16}}>research papers</div></Interactive.Div>
 <div style={{position:'absolute',top:0,left:0,right:0,height:290,background:BG,opacity:p(f,170,191)}}/>
 <Title opacity={p(f,179,200)} size={98}>From papers to connected knowledge</Title>
 </Stage>;
};
