import React from 'react';
import {staticFile,useCurrentFrame} from 'remotion';
import {C,Canvas,Headline,Node,Stroke,p,mix} from './shared';

export const Example=()=>{
  const f=useCurrentFrame();
  const show=p(f,16,66);
  const mark=p(f,74,129);
  return <Canvas>
    <g opacity={show}>
      <rect x="739" y="245" width="1025" height="699" rx="21" fill="#101915" stroke={C.line} strokeWidth="4"/>
      <circle cx="780" cy="278" r="8" fill={C.gold}/><circle cx="809" cy="278" r="8" fill={C.teal}/><circle cx="838" cy="278" r="8" fill={C.violet}/>
      <defs><clipPath id="site-crop"><rect x="751" y="304" width="1001" height="626" rx="6"/></clipPath></defs>
      <image href={staticFile('assets/explore-home.png')} x="751" y="304" width="1001" height="626" preserveAspectRatio="xMidYMin slice" clipPath="url(#site-crop)"/>
    </g>
    <g opacity={mark}>
      <Stroke d="M 186 827 C 319 701, 449 713, 631 821" color={C.teal} width={4}/>
      <Node x={186} y={827} r={27} color={C.gold}/>
      <Node x={421} y={733} r={23} color={C.mint}/>
      <Node x={631} y={821} r={27} color={C.blue}/>
    </g>
    <rect x="72" y="39" width="1780" height="210" fill={C.bg} opacity=".94"/>
    <Headline lines={['One working example']} size={93} opacity={p(f,0,23)}/>
    <g opacity={p(f,45,82)}>
      <text x="106" y="431" fontSize="92" fill={C.white} letterSpacing={-4}>Psychedelics</text>
      <text x="106" y="535" fontSize="92" fill={C.mint} letterSpacing={-4}>Knowledge Graph</text>
      <text x="108" y="965" fontSize="50" fill={C.muted} letterSpacing={-1}>psychedelicskg.com</text>
    </g>
  </Canvas>;
};
