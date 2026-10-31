import React from 'react';
import {staticFile,useCurrentFrame} from 'remotion';
import {BackGrid,C,Headline,KnowledgeWeb,Stage,TopScrim,mix,p} from './shared';

export const Example=()=>{
  const f=useCurrentFrame();
  const arrive=p(f,14,78),brand=p(f,42,91);
  return <Stage>
    <BackGrid opacity={.06}/>
    <KnowledgeWeb frame={440} transform={`translate(${mix(145,739,arrive)} ${mix(216,306,arrive)}) scale(${mix(.64,.54,arrive)})`} opacity={(1-p(f,38,103))*.68}/>
    <g opacity={arrive} transform={`translate(${mix(104,0,arrive)} 0)`}>
      <rect x="704" y="227" width="1081" height="725" rx="20" fill="#0b1614" stroke={C.line} strokeWidth="4"/>
      <circle cx="747" cy="263" r="8" fill={C.gold}/><circle cx="779" cy="263" r="8" fill={C.mint}/><circle cx="811" cy="263" r="8" fill={C.violet}/>
      <defs><clipPath id="knowledge-v2-site-crop"><rect x="719" y="292" width="1051" height="645" rx="7"/></clipPath></defs>
      <image href={staticFile('assets/explore-home.png')} x="719" y="292" width="1051" height="645" preserveAspectRatio="xMidYMin slice" clipPath="url(#knowledge-v2-site-crop)"/>
    </g>
    <TopScrim height={227} opacity={.97}/>
    <Headline lines={['One application']} size={100} opacity={p(f,0,25)}/>
    <g opacity={brand}>
      <text x="102" y="429" fontSize="83" fill={C.cream} letterSpacing="-3">Psychedelics</text>
      <text x="102" y="526" fontSize="83" fill={C.gold} letterSpacing="-3">Knowledge Graph</text>
      <path d="M 104 576 H 614" stroke={C.gold} strokeWidth="4" opacity=".72"/>
      <text x="104" y="941" fontSize="46" fill={C.muted}>psychedelicskg.com</text>
    </g>
  </Stage>;
};
