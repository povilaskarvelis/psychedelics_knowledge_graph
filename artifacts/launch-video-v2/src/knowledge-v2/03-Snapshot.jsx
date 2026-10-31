import React from 'react';
import {useCurrentFrame} from 'remotion';
import {BackGrid,C,Headline,Paper,Stage,Stroke,TopScrim,mix,p} from './shared';

const sources=Array.from({length:12},(_,i)=>({
  x:178+(i%4)*162,
  y:385+Math.floor(i/4)*205+((i*13)%27),
  r:(i%4-1.5)*7,
  color:[C.mint,C.blue,C.violet,C.gold][i%4],
}));

export const Snapshot=()=>{
  const f=useCurrentFrame();
  const gather=p(f,16,120);
  const shift=p(f,134,217);
  const later=p(f,146,185);
  const reviewX=mix(1115,820,shift);
  const questionFade=p(f,12,42)*(1-p(f,117,140));
  return <Stage>
    <BackGrid opacity={.09} offset={-f*.2}/>
    <g transform={`translate(${-175*shift} 0)`}>
      {sources.map((d,i)=>{
        const sx=mix(d.x,d.x+79,gather),sy=mix(d.y,560+(d.y-560)*.79,gather);
        const t=p(f,28+i*2,106+i*2);
        return <g key={i}>
          <path d={`M ${sx+48} ${sy} C ${sx+222} ${sy}, 790 ${600+(i-5.5)*10}, 1008 ${600+(i-5.5)*10}`}
            fill="none" stroke={d.color} strokeWidth="2.7" opacity={t*.51} pathLength="1" strokeDasharray="1" strokeDashoffset={1-t}/>
          <Paper x={sx} y={sy} w={126} h={168} rotation={d.r*(1-gather*.45)} scale={mix(1,.79,gather)} opacity={mix(.74,.52,gather)} accent={d.color}/>
        </g>;
      })}
      <g opacity={gather}>
        <circle cx="1115" cy="612" r="303" fill="none" stroke={C.gold} strokeWidth="2" opacity=".33"/>
        <circle cx="1115" cy="612" r="330" fill="none" stroke={C.gold} strokeWidth="2" opacity=".1"/>
        <rect x="936" y="339" width="358" height="545" rx="17" fill={C.paper} filter="url(#v2-card-shadow)"/>
        <rect x="992" y="393" width="191" height="15" rx="7" fill={C.ink} opacity=".64"/>
        <text x="992" y="493" fontSize="58" fill={C.ink} letterSpacing="-2">REVIEW</text>
        {[0,1,2,3,4,5,6,7].map(i=><rect key={i} x="992" y={546+i*36} width={i%3===0?202:253} height="8" rx="4" fill={C.ink} opacity=".24"/>)}
        <rect x="992" y="839" width="147" height="8" rx="4" fill={C.gold}/>
      </g>
    </g>
    <g opacity={later}>
      <Stroke d="M 1115 920 H 1782" color={C.gold} width={3} opacity=".6" dash="8 17"/>
      {[0,1,2,3,4,5,6].map(i=>{
        const t=p(f,151+i*12,190+i*12);
        const x=mix(1990,1270+(i%3)*193,t),y=365+Math.floor(i/3)*185+((i*13)%36);
        return <Paper key={i} x={x} y={y} w={128} h={169} rotation={-14+i*4} opacity={t*.84} accent={i%2?C.blue:C.gold}/>;
      })}
    </g>
    <TopScrim height={275} opacity={.97}/>
    <Headline lines={['Reviews connect the pieces','around a question']} size={96} opacity={questionFade}/>
    <Headline lines={['But each synthesis','is a snapshot']} size={106} opacity={p(f,142,168)*(1-p(f,256,282))}/>
  </Stage>;
};
