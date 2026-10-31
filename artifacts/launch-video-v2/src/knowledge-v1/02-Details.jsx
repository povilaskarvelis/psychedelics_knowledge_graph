import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C,Canvas,Headline,Paper,Stroke,p,mix} from './shared';

const fragments=[
  {word:'WHO',color:C.mint,y:420,x:1320},
  {word:'HOW',color:C.blue,y:595,x:1390},
  {word:'WHAT HAPPENED',color:C.gold,y:770,x:1220},
];

export const Details=()=>{
  const f=useCurrentFrame();
  const focus=p(f,6,72);
  const extract=p(f,91,172);
  return <Canvas>
    {[0,1,2,3,4,5].map((i)=><Paper key={i} x={210+i*295-(1-focus)*(i%2?150:-200)} y={545+(i%3-1)*130} w={180} h={238} rotation={-14+i*5} opacity={(1-focus)*.72} accent={[C.mint,C.blue,C.violet][i%3]}/>)}
    <g opacity={focus}>
      <rect x="280" y="315" width="750" height="600" rx="15" fill={C.paper}/>
      <rect x="355" y="383" width="340" height="14" rx="7" fill={C.ink} opacity=".65"/>
      {[0,1,2,3,4,5,6,7,8,9,10,11,12,13].map(i=><rect key={i} x="355" y={436+i*31} width={i%4===0?530:i%5===0?385:590} height="8" rx="4" fill={C.ink} opacity=".19"/>)}
      <rect x="345" y="518" width="635" height="35" rx="6" fill={C.mint} opacity=".35"/>
      <rect x="345" y="643" width="570" height="35" rx="6" fill={C.blue} opacity=".35"/>
      <rect x="345" y="767" width="615" height="35" rx="6" fill={C.gold} opacity=".35"/>
    </g>
    {fragments.map((d,i)=>{
      const t=p(f,95+i*16,150+i*16);
      const startY=[536,659,784][i];
      const x=mix(845,d.x,t);
      const y=mix(startY,d.y,t);
      return <g key={i} opacity={focus*t}>
        <Stroke d={`M ${Math.min(974,x)} ${startY} C 1110 ${startY}, 1110 ${y}, ${x-24} ${y}`} color={d.color} opacity={t*.55} width={3}/>
        <rect x={x-24} y={y-47} width={d.word.length>9?405:255} height="94" rx="47" fill={C.bg} stroke={d.color} strokeWidth="3"/>
        <text x={x+22} y={y+13} fontSize={d.word.length>9?35:42} fill={C.white} letterSpacing={-1}>{d.word}</text>
      </g>;
    })}
    <rect x="82" y="39" width="1670" height="218" fill={C.bg} opacity=".91"/>
    <Headline lines={['The details we need','live inside the papers']} x={108} y={145} size={94} opacity={p(f,0,25)}/>
  </Canvas>;
};
