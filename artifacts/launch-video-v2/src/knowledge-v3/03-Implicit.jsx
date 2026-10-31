import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Paper,Text,Line,C,p,mix,colors,Particle} from './shared';
export const Implicit=()=>{
 const f=useCurrentFrame();const coords=[[320,520],[750,450],[1200,510],[1610,490],[530,860],[1020,825],[1520,850]];
 return <Stage>
  <Title lines={f<112?['The connections are often implicit']:['Each reader has to','piece them together']} f={f<112?f+10:f-112} size={96} accent={f<112?-1:1}/>
  {coords.map(([x,y],i)=><Paper key={i} x={x+Math.sin(f*.018+i)*12} y={y+Math.cos(f*.013+i)*10} s={1.04} r={(i%3-1)*6} accent={colors[i%4]} highlight/>)}
  {[[0,1],[1,2],[0,4],[1,5],[2,5],[3,6],[5,6]].map(([a,b],i)=>{
   const s=26+i*8,t=p(f,s,s+28),[x,y]=coords[a],[xx,yy]=coords[b];
   return <g key={i}><Line d={`M${x+40} ${y} Q${(x+xx)/2} ${(y+yy)/2-80} ${xx-30} ${yy}`} color={colors[i%4]} width={3} progress={t} opacity={f<112?.24:.8}/>{f>112&&<Particle x={mix(x,xx,p((f-112+i*11)%90,0,70))} y={mix(y,yy,p((f-112+i*11)%90,0,70))-Math.sin(p((f-112+i*11)%90,0,70)*Math.PI)*70} color={colors[i%4]}/>}</g>
  })}
 </Stage>
};
