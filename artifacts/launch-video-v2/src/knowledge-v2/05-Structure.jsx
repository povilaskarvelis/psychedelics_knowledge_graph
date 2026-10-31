import React from 'react';
import {useCurrentFrame} from 'remotion';
import {BackGrid,C,Headline,KnowledgeWeb,Stage,TopScrim,mix,p} from './shared';

const fields=[
  {from:[556,504],to:[1136,475],color:C.blue},
  {from:[556,644],to:[1190,729],color:C.mint},
  {from:[556,784],to:[1396,586],color:C.gold},
];

export const Structure=()=>{
  const f=useCurrentFrame();
  const page=p(f,8,58),sourceFocus=p(f,220,268);
  return <Stage>
    <BackGrid opacity={.08}/>
    <KnowledgeWeb frame={400} transform="translate(700 230) scale(.65)" opacity={p(f,1,35)} lit={sourceFocus>.5?3:-1}/>
    <g opacity={page} transform={`translate(${mix(-185,0,page)} 0)`}>
      <rect x="141" y="336" width="511" height="604" rx="18" fill={C.paper} filter="url(#v2-card-shadow)"/>
      <rect x="199" y="392" width="245" height="15" rx="7" fill={C.ink} opacity=".56"/>
      {[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15].map(i=><rect key={i} x="201" y={446+i*27} width={i%4===0?312:i%5===0?370:392} height="7" rx="3" fill={C.ink} opacity=".2"/>)}
      {fields.map((d,i)=><rect key={i} x="195" y={d.from[1]-21} width={i===1?332:393} height="33" rx="5" fill={d.color} opacity={.23+p(f,61+i*25,103+i*25)*.21}/>)}
    </g>
    {fields.map((d,i)=>{
      const reveal=p(f,58+i*31,132+i*31);
      const path=`M ${d.from[0]} ${d.from[1]} C 832 ${d.from[1]}, 856 ${d.to[1]}, ${d.to[0]} ${d.to[1]}`;
      return <g key={i} opacity={page}>
        <path d={path} fill="none" stroke={d.color} strokeWidth="3.5" opacity={reveal*.86} pathLength="1" strokeDasharray="1" strokeDashoffset={1-reveal}/>
        <circle cx={mix(d.from[0],d.to[0],reveal)} cy={mix(d.from[1],d.to[1],reveal)} r="9" fill={d.color} opacity={reveal*(1-p(f,137+i*31,172+i*31))}/>
      </g>;
    })}
    <g opacity={sourceFocus}>
      <path d="M 1396 586 C 1043 573, 944 784, 556 784" fill="none" stroke={C.gold} strokeWidth="17" opacity=".19" filter="url(#v2-soft-glow)"/>
      <path d="M 1396 586 C 1043 573, 944 784, 556 784" fill="none" stroke={C.gold} strokeWidth="5" opacity=".88" pathLength="1" strokeDasharray="1" strokeDashoffset={1-p(f,242,327)}/>
      <circle cx="556" cy="784" r={17+8*p(f,290,339)} fill="none" stroke={C.gold} strokeWidth="4" opacity={p(f,275,310)}/>
    </g>
    <TopScrim height={273} opacity={.97}/>
    <Headline lines={['AI can help structure','what papers report']} size={103} opacity={p(f,0,28)*(1-p(f,198,226))}/>
    <Headline lines={['Each finding can remain','traceable to its source']} size={99} opacity={p(f,229,259)*(1-p(f,326,352))} colors={[C.cream,C.gold]}/>
  </Stage>;
};
