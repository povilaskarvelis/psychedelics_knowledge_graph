import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Paper,Text,C,p,mix,colors,Line} from './shared';
export const Synthesis=()=>{
 const f=useCurrentFrame(),gather=p(f,15,80),late=p(f,110,180);
 return <Stage>
  <Title lines={f<115?['Reviews bring evidence together']:['But each synthesis has','a scope. And a date.']} f={f<115?f+10:f-115} size={99} accent={f<115?-1:1}/>
  {Array.from({length:28},(_,i)=>{
   const x=180+(i%7)*245,y=440+Math.floor(i/7)*155,inside=i%3===0;
   return <Paper key={i} x={mix(x,inside?790+(i%3)*25:x,gather)} y={mix(y,inside?650:y,gather)} s={mix(.43,inside?.48:.35,gather)} opacity={inside?1:mix(.64,.2,gather)} accent={colors[i%4]}/>;
  })}
  <g opacity={gather} transform={`translate(${mix(0,-235,late)} 0)`}>
   <rect x="690" y="433" width="540" height="426" rx="8" fill={C.ink} stroke={C.gold} strokeWidth="2"/>
   <Text x={740} y={507} size={42} color={C.gold}>A focused synthesis</Text>
   {[0,1,2,3].map(i=><g key={i}><Line d={`M750 ${565+i*64} H1160`} color={C.mint} width={3} opacity={.35}/><circle cx={860+i%2*100} cy={565+i*64} r="9" fill={C.mint}/></g>)}
  </g>
  {Array.from({length:12},(_,i)=>{const q=p(f,123+i*5,150+i*5);return <Paper key={i} x={mix(2080,1220+(i%4)*148,q)} y={425+Math.floor(i/4)*188} s={.58} opacity={q} accent={C.blue}/>})}
  <Text x={1460} y={998} size={39} anchor="middle" opacity={late}>New research keeps arriving</Text>
 </Stage>
};
