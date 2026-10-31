import React from 'react';
import {useCurrentFrame} from 'remotion';
import {BackGrid,C,Headline,KnowledgeWeb,Paper,Stage,Stroke,TopScrim,mix,p} from './shared';

const chartBars=[83,115,143,151,195,217,239];
const additions=[[577,797],[850,519],[1265,789],[1490,488],[1140,946],[492,446],[1651,658]];

export const Living=()=>{
  const f=useCurrentFrame();
  const entry=p(f,22,89),ingest=p(f,93,126),grow=p(f,111,202),charts=p(f,174,255);
  return <Stage>
    <BackGrid opacity={.08}/>
    <KnowledgeWeb frame={440} transform="translate(145 216) scale(.64)" opacity={.91} lit={ingest>.25&&f<177?0:-1}/>
    <g opacity={grow}>
      {additions.map(([x,y],i)=>{
        const t=p(f,112+i*10,165+i*10),tx=mix(368,x,t),ty=mix(585,y,t);
        return <g key={i} opacity={t}>
          <Stroke d={`M 368 585 Q ${(368+x)/2} ${(585+y)/2-69} ${tx} ${ty}`} color={[C.mint,C.blue,C.gold,C.violet][i%4]} width={2.7} opacity=".66"/>
          <circle cx={tx} cy={ty} r={i%3===0?12:8} fill={[C.mint,C.blue,C.gold,C.violet][i%4]}/>
        </g>;
      })}
    </g>
    <g>
      <Paper x={mix(-154,293,entry)} y={585} w={143} h={188} rotation={mix(-14,1,entry)} opacity={1-p(f,102,124)} accent={C.gold} marked/>
      <circle cx={mix(303,368,ingest)} cy="585" r={mix(8,19,ingest)} fill={C.gold} opacity={p(f,93,104)*(1-p(f,119,145))}/>
      <Stroke d="M 312 585 Q 340 568, 368 585" color={C.gold} width={5} opacity={p(f,96,111)*(1-p(f,128,149))}/>
    </g>
    <g opacity={p(f,37,87)}>
      <rect x="1285" y="355" width="546" height="543" rx="18" fill={C.panel} stroke={C.line} strokeWidth="2.5"/>
      <text x="1323" y="419" fill={C.cream} fontSize="45">Visualizations</text>
      <Stroke d="M 1322 829 H 1794" color={C.muted} width={2} opacity=".58"/>
      {chartBars.map((n,i)=>{
        const h=n+(i>4?47*charts:0),t=p(f,58+i*9,91+i*9);
        return <rect key={i} x={1335+i*62} y={829-h*t} width="43" height={h*t} rx="4" fill={[C.mint,C.blue,C.violet,C.mint,C.gold,C.blue,C.gold][i]} opacity=".88"/>;
      })}
      <path d={`M 1340 714 C 1440 711, 1523 685, 1610 ${619-32*charts} S 1722 ${580-51*charts}, 1790 ${493-83*charts}`}
        fill="none" stroke={C.gold} strokeWidth="5" opacity={p(f,174,256)}/>
    </g>
    <TopScrim height={276} opacity={.97}/>
    <Headline lines={['And the map can grow','as research does']} size={108} opacity={p(f,0,25)*(1-p(f,184,208))}/>
    <Headline lines={['A living memory','for science']} size={116} opacity={p(f,211,240)*(1-p(f,286,312))} colors={[C.cream,C.gold]}/>
  </Stage>;
};
