import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Text,Web,Line,Paper,C,p,mix,colors,points} from './shared';
export const Navigate=()=>{
 const f=useCurrentFrame(),zoom=p(f,48,115),plots=p(f,132,186);
 return <Stage>
  <g transform={`translate(960 690) scale(${mix(2.65,.83,zoom)}) translate(-960 -650)`} opacity={mix(1,.32,plots)}><Web f={f} focus={zoom<.5?2:-1}/></g>
  <g opacity={1-zoom}><Paper x={960} y={690} s={1.8} highlight/><Text x={1210} y={585} color={C.gold} size={45}>One finding</Text><Line d="M1100 650 Q1170 650 1190 590" color={C.gold} width={3}/></g>
  <rect width="1920" height="323" fill="url(#scrim)"/>
  <Title lines={['Move from a study detail','to patterns across the literature']} size={91} f={f+10} accent={1}/>
  <g opacity={plots} transform={`translate(0 ${mix(80,0,plots)})`}>
   <rect x="140" y="429" width="778" height="487" rx="10" fill={C.bg} stroke={C.mint} strokeWidth="2"/>
   <rect x="998" y="429" width="778" height="487" rx="10" fill={C.bg} stroke={C.purple} strokeWidth="2"/>
   <Text x={185} y={495} size={38} color={C.mint}>Where evidence accumulates</Text>
   <Text x={1043} y={495} size={38} color={C.purple}>Where questions remain</Text>
  </g>
  {points.slice(0,96).map((n,i)=>{
   const bar=i<48,col=Math.floor(i/3),part=i%3,j=i-48;
   const height=46+col*10+Math.sin(col*.8)*30;
   const tx=bar?188+col*43:1045+j%8*84,ty=bar?865-height*(part+1)/3:548+Math.floor(j/8)*53;
   const q=p(f,132+i%12*2,169+i%12*2),empty=!bar&&[6,7,15,23,31,39].includes(j);
   return <rect key={i} x={mix(960+(n.x-960)*.83,tx,q)} y={mix(690+(n.y-650)*.83,ty,q)} width={mix(8,bar?28:70,q)} height={mix(8,bar?height/3-3:39,q)} rx={mix(4,2,q)} fill={empty?C.bg:bar?colors[part]:colors[j%4]} stroke={empty?C.purple:'none'} opacity={p(f,130,142)*(empty?.55:bar?.85:.22+j%6*.12)}/>;
  })}
 </Stage>
};
