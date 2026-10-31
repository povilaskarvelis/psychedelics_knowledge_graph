import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Paper,C,p,mix,rand,colors} from './shared';
export const Acceleration=()=>{
 const f=useCurrentFrame(),travel=mix(2.4,13.6,p(f,0,180));
 const cards=Array.from({length:264},(_,i)=>{
  const col=i%22-10.5,row=Math.floor(i/22)%4-1.5,layer=Math.floor(i/88);
  const z=3+layer*2.5+travel,scale=930/z;
  return {i,x:1030+(col*1.86+layer*.18)*scale,y:695+(row*2.3)*scale,s:scale/118,depth:layer};
 }).sort((a,b)=>b.depth-a.depth);
 return <Stage>
  <g>
   {cards.map(({i,x,y,s,depth})=><Paper key={i} x={x} y={y} s={s} r={-4+depth*.55} tone={[C.white,'#728c7f','#29473e'][depth]} opacity={p(f+25,depth*5,depth*5+20)} accent={colors[i%4]}/>)}
  </g>
  <rect width="1920" height="365" fill="url(#scrim)"/>
  <Title lines={['Research keeps','accelerating']} f={f+10} size={120} accent={1}/>
  <g opacity={p(f,105,135)}>
   <path d={`M 120 965 C 850 970 1470 940 1780 ${mix(960,475,p(f,105,194))}`} fill="none" stroke={C.gold} strokeWidth="5"/>
   <path d="M1749 490 L1780 475 L1787 512" fill="none" stroke={C.gold} strokeWidth="5" opacity={p(f,184,201)}/>
  </g>
 </Stage>
};
