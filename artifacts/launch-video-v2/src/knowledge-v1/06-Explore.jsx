import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C,Canvas,Headline,Paper,Stroke,p,mix} from './shared';
import {Network} from './05-Graph';

const stacks=[[70,50,22],[92,72,26],[64,89,49],[108,91,58],[127,111,82],[99,145,98],[148,128,116],[130,159,139]];

export const Explore=()=>{
  const f=useCurrentFrame();
  const switchToPattern=p(f,116,151);
  const question=p(f,3,29)*(1-switchToPattern);
  const chart=p(f,133,175);
  return <Canvas>
    <g opacity={p(f,1,32)}>
      <Network frame={f+205} transform="translate(25 141) scale(.53)" focusIds={switchToPattern>.72?null:[0,2,3,4,7,10]}/>
    </g>
    <g opacity={question}>
      <rect x="1034" y="324" width="790" height="116" rx="20" fill="#11251f" stroke={C.mint} strokeWidth="3"/>
      <circle cx="1090" cy="382" r="20" fill="none" stroke={C.mint} strokeWidth="5"/>
      <Stroke d="M 1105 396 L 1125 415" color={C.mint} width={5}/>
      <text x="1150" y="398" fill={C.white} fontSize="42" letterSpacing="-1.1">Which studies used this method?</text>
      {[0,1,2].map(i=>{
        const t=p(f,28+i*14,60+i*14);
        return <g key={i} opacity={t} transform={`translate(0 ${mix(66,0,t)})`}>
          <rect x={1048+i*257} y="521" width="219" height="326" rx="15" fill="#132720" stroke={[C.blue,C.gold,C.violet][i]} strokeWidth="2"/>
          <Paper x={1157+i*257} y={640} w={136} h={182} opacity={1} accent={[C.blue,C.gold,C.violet][i]}/>
          <rect x={1098+i*257} y="777" width="119" height="8" rx="4" fill={[C.blue,C.gold,C.violet][i]} opacity=".8"/>
        </g>;
      })}
    </g>
    <g opacity={chart}>
      <rect x="1035" y="315" width="787" height="582" rx="18" fill="#11231e" stroke={C.line} strokeWidth="2.5"/>
      <Stroke d="M 1086 824 H 1761" color={C.muted} width={2.5} opacity=".6"/>
      {stacks.map((segments,i)=>{
        const t=p(f,148+i*7,189+i*7);
        const x=1104+i*78;
        let accumulated=0;
        return <g key={i}>{segments.map((h,j)=>{
          const y=824-(accumulated+h)*t;
          accumulated+=h;
          return <rect key={j} x={x} y={y} width="53" height={Math.max(0,h*t-3)} rx="4" fill={[C.mint,C.blue,C.violet][j]} opacity={.88}/>;
        })}</g>;
      })}
      <g opacity={p(f,194,225)}>
        <circle cx="1090" cy="365" r="11" fill={C.mint}/><text x="1113" y="377" fill={C.white} fontSize="32">Methods</text>
        <circle cx="1308" cy="365" r="11" fill={C.blue}/><text x="1331" y="377" fill={C.white} fontSize="32">Populations</text>
        <circle cx="1584" cy="365" r="11" fill={C.violet}/><text x="1607" y="377" fill={C.white} fontSize="32">Outcomes</text>
      </g>
    </g>
    <rect x="0" y="0" width="1920" height="262" fill={C.bg} opacity=".97"/>
    <Headline lines={['Ask a specific question']} size={100} opacity={p(f,0,23)*(1-p(f,116,140))}/>
    <Headline lines={['See patterns across','many studies']} size={98} opacity={p(f,123,148)}/>
  </Canvas>;
};
