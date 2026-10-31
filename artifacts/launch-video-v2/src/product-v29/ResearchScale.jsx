import React from 'react';
import {Dna,Brain,BrainCircuit,Eye,Stethoscope,ShieldCheck,UsersRound,Earth} from 'lucide-react';
import {Label,p,mix} from '../product/shared';

const areas=[
 {label:['Molecular','mechanisms'],x:300,y:430,color:'#72a77c',Icon:Dna},
 {label:['Brain','function'],x:740,y:430,color:'#5f9eb5',Icon:Brain},
 {label:['Cognition &','behavior'],x:1180,y:430,color:'#a88bd1',Icon:BrainCircuit},
 {label:['Subjective','experience'],x:1620,y:430,color:'#55b7ab',Icon:Eye},
 {label:['Clinical','outcomes'],x:300,y:755,color:'#d1846f',Icon:Stethoscope},
 {label:['Safety'],x:740,y:755,color:'#d6a84f',Icon:ShieldCheck},
 {label:['Real-world','use'],x:1180,y:755,color:'#9bab62',Icon:UsersRound},
 {label:['Public','health'],x:1620,y:755,color:'#82a9d8',Icon:Earth},
];

export const ResearchScale=({frame,continuousTransform=false,constructFromParticles=false})=><g>
 {areas.map(({label,x,y,color,Icon},index)=>{
  const reveal=p(frame,constructFromParticles?178+index*6:continuousTransform?156+index*5:170+index*7,constructFromParticles?196+index*6:continuousTransform?180+index*5:190+index*7);
  const exit=continuousTransform?p(frame,270+index*2,306+index*2):p(frame,294,316);
  const iconSize=constructFromParticles?98:mix(76,98,reveal);
  return <g key={label.join(' ')} opacity={reveal*(1-exit)}>
   <circle cx={x} cy={y} r={mix(constructFromParticles?72:mix(46,72,reveal),22,exit)} fill={color} fillOpacity=".075" stroke={color} strokeWidth="2.5" opacity=".62"/>
   <Icon x={x-iconSize/2} y={y-iconSize/2} width={iconSize} height={iconSize} color={color} strokeWidth={1.8} absoluteStrokeWidth/>
   {label.length===1?<Label x={x} y={y+132} size={46} anchor="middle" opacity={reveal}>{label[0]}</Label>:<>
    <Label x={x} y={y+120} size={46} anchor="middle" opacity={reveal}>{label[0]}</Label>
    <Label x={x} y={y+173} size={46} anchor="middle" opacity={reveal}>{label[1]}</Label>
   </>}
  </g>;
 })}
</g>;
