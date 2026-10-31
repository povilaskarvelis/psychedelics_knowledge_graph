import React from 'react';
import {useCurrentFrame,staticFile} from 'remotion';
import {Stage,Title,Text,Web,C,p,mix} from './shared';
export const Horizon=()=>{
 const f=useCurrentFrame(),end=p(f,130,155);
 return <Stage>
  <g opacity={1-end}>
   <Title lines={['Already taking shape in','Psychedelics Knowledge Graph']} size={91} f={f+10} accent={1}/>
   <g transform={`translate(960 730) scale(${mix(.95,1.03,p(f,0,130))}) translate(-960 -730)`}>
    <rect x="220" y="351" width="1480" height="624" rx="12" fill={C.ink} stroke={C.mint} strokeWidth="2"/>
    <defs><clipPath id="site3"><rect x="234" y="365" width="1452" height="596" rx="8"/></clipPath></defs>
    <image href={staticFile('assets/explore-home.png')} x="234" y="365" width="1452" height="880" preserveAspectRatio="xMidYMin slice" clipPath="url(#site3)"/>
   </g>
  </g>
  <g opacity={end}>
   <g transform={`translate(960 670) scale(${mix(.7,1.25,p(f,132,265))}) translate(-960 -650)`} opacity=".45"><Web f={f}/></g>
   <rect width="1920" height="1080" fill={C.bg} opacity=".25"/>
   <Title lines={['What could science become','with a living, connected memory?']} f={f-136} center y={417} size={97} accent={1}/>
   <Text x={960} y={797} size={45} anchor="middle" color={C.white} opacity={p(f,179,201)}>Rethink knowledge storage and synthesis</Text>
   <Text x={960} y={948} size={35} anchor="middle" color={C.gold} opacity={p(f,202,218)}>psychedelicskg.com</Text>
  </g>
 </Stage>
};
