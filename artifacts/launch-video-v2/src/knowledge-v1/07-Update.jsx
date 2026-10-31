import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C,Canvas,Headline,Paper,Stroke,p,mix} from './shared';
import {Network} from './05-Graph';

const heights=[133,197,168,260,225,318];

export const Update=()=>{
  const f=useCurrentFrame();
  const ingest=p(f,26,98);
  const graphPulse=p(f,94,143);
  const chartRise=p(f,130,196);
  const paperX=mix(164,381,ingest);
  return <Canvas>
    <rect x="495" y="298" width="850" height="625" rx="19" fill="#10231e" stroke={C.line} strokeWidth="3"/>
    <rect x="1414" y="298" width="399" height="625" rx="19" fill="#10231e" stroke={C.line} strokeWidth="3"/>
    <text x="537" y="365" fontSize="46" fill={C.white}>Knowledge graph</text>
    <text x="1453" y="365" fontSize="46" fill={C.white}>Visualizations</text>
    <Stroke d="M 531 394 H 1309 M 1448 394 H 1779" color={C.line} width={2}/>
    <Network frame={f+230} transform="translate(440 350) scale(.5)" opacity={.88}/>
    <circle cx="890" cy="605" r={35+108*graphPulse} fill="none" stroke={C.gold} strokeWidth={mix(8,1,graphPulse)} opacity={graphPulse*(1-p(f,126,155))*.65}/>
    <g>
      <Paper x={paperX} y={592} w={150} h={200} rotation={mix(-14,0,ingest)} opacity={1-p(f,94,113)} accent={C.gold}/>
      <circle cx={mix(395,500,p(f,95,132))} cy="592" r={mix(10,21,p(f,95,132))} fill={C.gold}
        opacity={p(f,94,107)*(1-p(f,125,144))}/>
      <Stroke d="M 429 592 H 495" color={C.gold} width={5} opacity={p(f,92,111)*(1-p(f,131,149))}/>
    </g>
    <g>
      <Stroke d="M 1460 839 H 1768" color={C.muted} width={2.5} opacity=".6"/>
      {heights.map((h,i)=>{
        const t=p(f,34+i*9,71+i*9);
        const extra=i===5?64*chartRise:i===4?28*chartRise:0;
        const height=(h+extra)*t;
        return <rect key={i} x={1471+i*49} y={839-height} width="34" height={height} rx="4" fill={[C.mint,C.blue,C.violet,C.mint,C.blue,C.gold][i]} opacity=".9"/>;
      })}
      <path d={`M 1717 ${614-28*chartRise} L 1745 ${577-52*chartRise} L 1770 ${602-75*chartRise}`}
        fill="none" stroke={C.gold} strokeWidth="4" strokeLinecap="round" opacity={chartRise}/>
    </g>
    <g opacity={p(f,53,113)*(1-p(f,126,169))}>
      {[0,1,2,3,4].map(i=><circle key={i} cx={1350+i*11} cy={507+(i%3)*44} r={4+i%2*3} fill={[C.mint,C.blue,C.gold][i%3]}/>)}
    </g>
    <rect x="0" y="0" width="1920" height="264" fill={C.bg} opacity=".97"/>
    <Headline lines={['Built to grow with','the literature']} size={100} opacity={p(f,0,23)}/>
  </Canvas>;
};
