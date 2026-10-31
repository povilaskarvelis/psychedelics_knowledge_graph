import React from 'react';
import {useCurrentFrame} from 'remotion';
import {BackGrid,C,Headline,KnowledgeWeb,Stage,Stroke,TopScrim,mix,p} from './shared';

const bars=[[39,44,17],[53,35,31],[67,62,29],[52,83,42],[71,92,46],[103,78,62],[93,111,73],[120,133,75]];

export const Scale=()=>{
  const f=useCurrentFrame();
  const approach=p(f,0,101),recede=p(f,145,229);
  const tx=mix(mix(700,-16,approach),145,recede);
  const ty=mix(mix(230,63,approach),216,recede);
  const s=mix(mix(.65,1.32,approach),.64,recede);
  const focus=p(f,77,124)*(1-p(f,161,220));
  const broad=p(f,176,226);
  return <Stage>
    <BackGrid opacity={.08} offset={-f*.19}/>
    <KnowledgeWeb frame={420} transform={`translate(${tx} ${ty}) scale(${s})`} opacity={.93} lit={focus>.42?1:-1}/>
    <g opacity={focus}>
      <circle cx="870" cy="561" r={75+18*p(f,104,151)} fill="none" stroke={C.blue} strokeWidth="3" opacity=".75"/>
      <circle cx="870" cy="561" r="105" fill="none" stroke={C.blue} strokeWidth="2" opacity=".25"/>
      <Stroke d="M 963 559 C 1070 529, 1118 504, 1191 503" color={C.blue} width={4}/>
      <rect x="1181" y="422" width="562" height="239" rx="18" fill={C.panel} stroke={C.blue} strokeWidth="3"/>
      <text x="1224" y="487" fill={C.blue} fontSize="35">STUDY DETAIL</text>
      <text x="1224" y="558" fill={C.cream} fontSize="49">Follow-up period</text>
      <Stroke d="M 1223 593 H 1688" color={C.line} width={2}/>
      <rect x="1246" y="605" width="41" height="51" rx="4" fill={C.paper}/>
      <rect x="1253" y="615" width="23" height="3" rx="1.5" fill={C.blue}/>
      <rect x="1253" y="625" width="27" height="3" rx="1.5" fill={C.ink} opacity=".3"/>
      <rect x="1253" y="635" width="21" height="3" rx="1.5" fill={C.ink} opacity=".3"/>
      <text x="1318" y="641" fill={C.muted} fontSize="34">Source paper</text>
    </g>
    <g opacity={broad}>
      <rect x="1285" y="355" width="546" height="543" rx="20" fill={C.panel} stroke={C.line} strokeWidth="2.5"/>
      <text x="1323" y="419" fill={C.cream} fontSize="45">Patterns</text>
      <Stroke d="M 1322 829 H 1794" color={C.muted} width={2.5} opacity=".65"/>
      {bars.map((segments,i)=>{
        const h=p(f,212+i*7,264+i*7);
        let sum=0;
        return <g key={i}>{segments.map((n,j)=>{
          const y=829-(sum+n)*h;sum+=n;
          return <rect key={j} x={1335+i*58} y={y} width="42" height={Math.max(0,n*h-3)} rx="4" fill={[C.mint,C.blue,C.violet][j]} opacity=".87"/>;
        })}</g>;
      })}
      <path d="M 1335 726 C 1441 687, 1485 742, 1578 615 S 1721 638, 1796 506" fill="none" stroke={C.gold} strokeWidth="5" opacity={p(f,249,339)}/>
    </g>
    <TopScrim height={270} opacity={.97}/>
    <Headline lines={['Find a single','study detail']} size={109} opacity={p(f,0,27)*(1-p(f,159,185))}/>
    <Headline lines={['See patterns across','the literature']} size={109} opacity={p(f,187,218)*(1-p(f,346,372))} colors={[C.cream,C.gold]}/>
  </Stage>;
};
