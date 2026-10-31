import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Text,Web,Line,Chip,Particle,C,p,mix,colors} from './shared';
export const Reuse=()=>{
 const f=useCurrentFrame();
 return <Stage>
  <Title lines={f<115?['Make synthesis cumulative']:['New questions build','on a shared foundation']} size={107} f={f<115?f+10:f-115} accent={f<115?0:1}/>
  <g transform="translate(-345 195) scale(.82)"><Web f={f}/></g>
  {['Compare methods','Track an outcome','Plan a review'].map((lab,i)=>{
   const y=431+i*199,q=p(f,18+i*23,60+i*23),t=((f+i*24)%100)/100;
   return <g key={lab} opacity={q}><Line d={`M870 700 C1150 700 1040 ${y+42} 1240 ${y+42}`} color={colors[i]} width={3} progress={q}/><Particle x={mix(870,1240,t)} y={mix(700,y+42,p(t,0,1))} color={colors[i]}/><Chip x={1240} y={y} w={520} label={lab} color={colors[i]}/></g>;
  })}
  <Text x={104} y={1010} color={C.muted} size={39} opacity={p(f,166,188)}>Expert judgment still matters. The groundwork becomes reusable.</Text>
 </Stage>
};
