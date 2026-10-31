import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C,Canvas,Headline,Paper,Stroke,p,mix} from './shared';

const sources=Array.from({length:12},(_,i)=>({
  x:169+(i%4)*176,
  y:361+Math.floor(i/4)*218+((i*17)%33),
  angle:(i%4-1.5)*7,
  color:[C.mint,C.blue,C.violet,C.gold][i%4],
}));

export const Reviews=()=>{
  const f=useCurrentFrame();
  const gather=p(f,21,105);
  const later=p(f,134,176);
  return <Canvas>
    <g opacity={p(f,2,34)}>
      {sources.map((d,i)=>{
        const t=p(f,20+i*3,91+i*3);
        const x=mix(d.x,d.x+45,t),y=mix(d.y,d.y+(618-d.y)*.08,t);
        return <g key={i}>
          <Stroke d={`M ${x+52} ${y} C 846 ${y}, 818 ${610+(i%4-1.5)*31}, 999 ${610+(i%4-1.5)*31}`} color={d.color} width={2.5} opacity={t*.46}/>
          <Paper x={x} y={y} w={114} h={151} rotation={d.angle*(1-t)} opacity={mix(.77,.57,t)} scale={mix(1,.86,t)} accent={d.color}/>
        </g>;
      })}
      <g opacity={gather}>
        <rect x="1000" y="337" width="366" height="549" rx="15" fill={C.paper}/>
        <rect x="1053" y="392" width="204" height="15" rx="7" fill={C.ink} opacity=".7"/>
        <text x="1053" y="482" fill={C.ink} fontSize="55" letterSpacing="-2">REVIEW</text>
        {[0,1,2,3,4,5,6,7].map(i=><rect key={i} x="1053" y={536+i*38} width={i%3===0?220:263} height="8" rx="4" fill={C.ink} opacity=".23"/>)}
        <rect x="1053" y="838" width="156" height="8" rx="4" fill={C.gold}/>
      </g>
    </g>
    <g opacity={later}>
      <Stroke d="M 1380 605 H 1755" color={C.gold} width={3} dash="6 18" opacity=".7"/>
      {[0,1,2,3].map(i=>{
        const t=p(f,139+i*13,184+i*13);
        return <Paper key={i} x={mix(1990,1505+(i%2)*174,t)} y={423+Math.floor(i/2)*212} w={128} h={168} rotation={-7+i*4} opacity={t*.85} accent={C.gold}/>;
      })}
    </g>
    <rect x="0" y="0" width="1920" height="279" fill={C.bg} opacity=".95"/>
    <Headline lines={['Reviews bring evidence','together for a question']} size={91} opacity={p(f,0,19)*(1-p(f,126,147))}/>
    <Headline lines={['Then new papers arrive']} size={101} opacity={p(f,140,162)}/>
  </Canvas>;
};
