import React from 'react';
import {Interactive,interpolate,useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,Paper,AreaGraph,Label,Node,p,mix,ease,broad} from './shared';

export const Foundation=()=>{
 const f=useCurrentFrame();
 const shrink=p(f,12,105),feed=p(f,135,230),focus=p(f,255,310);
 return <Stage>
  <Svg>
   {Array.from({length:216},(_,i)=>{
    const col=i%24,row=Math.floor(i/24),lane=i%3;
    const sx=960+(col-11.5)*mix(172,82,shrink),sy=570+(row-4)*mix(225,106,shrink);
    const stagger=(i*37)%101;
    const arrive=185+stagger*.65;
    const q=p(f,135+stagger*.45,arrive);
    const tx=620,ty=410+lane*210;
    const x=mix(sx,tx,q),y=mix(sy,ty,q);
    return <Paper key={i} x={x} y={y} w={mix(mix(105,42,shrink),28,q)} opacity={mix(.28,.6,feed)*(1-p(f,arrive-3,arrive+5))} rotate={mix((i%7-3)*3,0,q)}/>;
   })}
   <AreaGraph frame={f} start={198} nodeStart={138}/>
  </Svg>
  <Interactive.Div name="Opening statement" style={{position:'absolute',left:180,right:180,top:340,fontSize:134,lineHeight:1.03,letterSpacing:-6,textAlign:'center',opacity:interpolate(f,[0,10,70,91],[0,1,1,0],ease),translate:interpolate(f,[0,24],['0px 30px','0px 0px'],ease)}}>Make sense of<br/><span style={{color:'#70cbb4'}}>psychedelic research</span></Interactive.Div>
  <Interactive.Div name="Research paper count" style={{position:'absolute',left:140,right:140,top:335,textAlign:'center',opacity:interpolate(f,[86,101,132,154],[0,1,1,0],ease)}}><div style={{fontSize:170,letterSpacing:-7,lineHeight:1}}>21,735</div><div style={{fontSize:78,marginTop:15}}>research papers</div></Interactive.Div>
  <Title opacity={p(f,154,182)} size={98}>From papers to connected knowledge</Title>
  <div style={{position:'absolute',left:140,right:140,top:917,height:88,overflow:'hidden',opacity:p(f,90,110)*(1-p(f,185,209))}}>
   <div style={{position:'absolute',display:'flex',gap:74,whiteSpace:'nowrap',translate:`${mix(0,-2100,p(f,98,205))}px 0px`}}>{broad.rows.map(c=><div key={c.key} style={{fontSize:60,color:'#a3bcb0'}}>{c.name}</div>)}</div>
   <div style={{position:'absolute',inset:0,background:'linear-gradient(90deg,#090e0d 0%, transparent 6%, transparent 92%, #090e0d 100%)'}}/>
  </div>
 </Stage>;
};
