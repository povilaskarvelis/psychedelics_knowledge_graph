import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Paper,Text,C,p,mix,colors,Line} from './shared';
export const Unit=()=>{
 const f=useCurrentFrame(),open=p(f,85,145),question=p(f,152,168);
 return <Stage light>
  <Title lines={['But knowledge is still','stored paper by paper']} f={f+10} light size={102}/>
  <g transform={`translate(960 628) scale(${mix(.76,1,p(f,0,150))})`}>
   {[-3,-2,-1,1,2,3].map(i=><Paper key={i} x={i*260} y={Math.abs(i)*23} r={i*4} s={1.7} tone="#d1d7c9" opacity={mix(.75,.3,open)} accent={C.ink}/>)}
   <rect x="-268" y="-266" width="536" height="532" rx="7" fill={C.ink}/>
   <rect x="-214" y="-214" width="305" height="15" rx="3" fill={C.white}/>
   {['Methods','Participants','Findings','Context'].map((t,i)=><g key={t} opacity={p(f,25+i*15,49+i*15)}>
    <rect x="-217" y={-161+i*93} width="429" height="47" rx="4" fill={colors[i]} opacity=".16"/>
    <Text x={-200} y={-127+i*93} size={32} color={colors[i]}>{t}</Text>
    <rect x="-211" y={-96+i*93} width={345+i%2*65} height="5" rx="2" fill={C.white} opacity=".25"/>
   </g>)}
  </g>
  <g opacity={question}><rect x="80" y="900" width="1760" height="105" fill={C.white}/><Text x={960} y={967} size={53} color={C.ink} anchor="middle">Is the paper the best unit for using knowledge?</Text></g>
 </Stage>
};
