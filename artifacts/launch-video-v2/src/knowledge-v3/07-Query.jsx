import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Text,Web,Chip,C,p,mix,colors,Paper} from './shared';
export const Query=()=>{
 const f=useCurrentFrame(),filter=p(f,63,116),result=p(f,125,174);
 return <Stage>
  <g transform={`translate(${mix(0,-280,result)} ${mix(200,325,result)}) scale(${mix(.83,.7,result)})`}><Web f={f} focus={filter>.7?2:-1}/></g>
  <rect width="1920" height="320" fill="url(#scrim)"/>
  <Title lines={f<77?['Change the structure.','Change what you can ask.']:['Ask across studies','by the details that matter']} size={104} f={f<77?f+10:f-77} accent={1}/>
  {['Population','Study design','Follow-up'].map((lab,i)=><Chip key={lab} x={230+i*490} y={326} w={420} label={f>58+i*13?['Adults','Randomized trials','6+ months'][i]:lab} color={colors[i]} opacity={p(f,8+i*17,28+i*17)}/>)}
  <g opacity={result} transform={`translate(${mix(120,0,result)} 0)`}>
   <rect x="1110" y="461" width="672" height="420" rx="10" fill={C.ink} stroke={C.mint} strokeWidth="2"/>
   <Text x={1150} y={526} size={40} color={C.white}>Relevant study details</Text>
   {[0,1,2].map(i=><g key={i} opacity={p(f,149+i*12,166+i*12)}><Paper x={1170} y={605+i*95} s={.26} accent={colors[i]}/><rect x="1224" y={580+i*95} width={422-i*54} height="12" rx="6" fill={colors[i]}/><rect x="1224" y={609+i*95} width="292" height="7" rx="3" fill={C.muted} opacity=".4"/></g>)}
  </g>
  <Text x={960} y={1010} anchor="middle" size={43} opacity={p(f,182,201)}>Methods and findings become directly queryable</Text>
 </Stage>
};
