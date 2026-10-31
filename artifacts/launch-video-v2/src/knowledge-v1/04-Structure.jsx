import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C,Canvas,Headline,Paper,Node,Stroke,p,mix} from './shared';

const fields=[
  {label:'Population',color:C.mint,from:488,to:405},
  {label:'Method',color:C.blue,from:622,to:584},
  {label:'Finding',color:C.gold,from:756,to:763},
];

export const Structure=()=>{
  const f=useCurrentFrame();
  const open=p(f,10,48);
  return <Canvas>
    <g opacity={open}>
      <rect x="185" y="295" width="640" height="628" rx="15" fill={C.paper}/>
      <rect x="248" y="352" width="315" height="14" rx="7" fill={C.ink} opacity=".55"/>
      {[0,1,2,3,4,5,6,7,8,9,10,11,12,13].map(i=><rect key={i} x="248" y={414+i*33} width={i%4===0?431:520} height="7" rx="4" fill={C.ink} opacity=".18"/>)}
      {fields.map((d,i)=><rect key={i} x="237" y={d.from-27} width={550-(i%2)*70} height="38" rx="6" fill={d.color} opacity={.23}/>)}
    </g>
    {fields.map((d,i)=>{
      const t=p(f,74+i*37,119+i*37);
      const beam=p(f,60+i*37,115+i*37);
      const tipX=mix(745,1110,beam);
      const tipY=mix(d.from,d.to,beam);
      return <g key={d.label}>
        <Stroke d={`M 745 ${d.from} C 906 ${d.from}, 952 ${d.to}, ${tipX} ${tipY}`} color={d.color} width={3.5} opacity={beam*.8}/>
        <circle cx={tipX} cy={tipY} r={9} fill={d.color} opacity={beam*(1-p(f,119+i*37,139+i*37))}/>
        <g opacity={t}>
          <rect x="1085" y={d.to-62} width="650" height="124" rx="16" fill="#10231e" stroke={d.color} strokeWidth="2.5"/>
          <rect x="1085" y={d.to-62} width="12" height="124" rx="6" fill={d.color}/>
          <Node x={1145} y={d.to} r={14} color={d.color}/>
          <text x="1192" y={d.to+16} fontSize="52" fill={C.white} letterSpacing={-1.7}>{d.label}</text>
          <rect x="1560" y={d.to-22} width={i===0?114:144} height="9" rx="4" fill={d.color} opacity=".35"/>
          <rect x="1560" y={d.to+10} width={i===2?84:124} height="9" rx="4" fill={d.color} opacity=".25"/>
        </g>
      </g>;
    })}
    <rect x="78" y="44" width="1765" height="211" fill={C.bg} opacity=".95"/>
    <Headline lines={['AI can help structure','what papers report']} size={94} opacity={p(f,0,26)}/>
  </Canvas>;
};
