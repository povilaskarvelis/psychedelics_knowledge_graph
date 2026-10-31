import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Paper,Text,Web,Chip,C,p,mix,points,colors} from './shared';
export const Reframe=()=>{
 const f=useCurrentFrame(),turn=p(f,84,163),reveal=p(f,135,205);
 return <Stage>
  <g transform={`translate(960 700) scale(${mix(.96,1,turn)}) translate(-960 -650)`}>
   {Array.from({length:15},(_,i)=><rect key={i} x={170+(i%5)*345} y={383+Math.floor(i/5)*180} width="200" height="155" rx="4" fill={C.white} opacity={(1-p(f,80,125))*.12}/>)}
   <Web f={f} assemble={reveal}/>
   {points.map((n,i)=>{
    const paper=Math.floor(i/10),line=i%10;
    const q=p(f,84+(i%15)*1.7,145+(i%15)*1.7),sx=270+(paper%5)*345,sy=402+Math.floor(paper/5)*180+line*13;
    return <g key={i} transform={`translate(${mix(sx,n.x,q)} ${mix(sy,n.y,q)}) rotate(${mix((i%5-2)*9,0,q)})`}>
     <rect x={-mix(72,n.r,q)} y={-mix(2,n.r,q)} width={mix(144-line%3*18,n.r*2,q)} height={mix(4,n.r*2,q)} rx={mix(1,n.r,q)} fill={n.c} opacity={.7}/>
    </g>;
   })}
  </g>
  <rect width="1920" height="330" fill="url(#scrim)"/>
  <Title lines={f<85?['What if the connections','became part of the record?']:['Rethink how knowledge','is stored. And synthesized.']} f={f<85?f+10:f-85} size={103} accent={1}/>
  <Text x={960} y={1000} anchor="middle" size={45} color={C.gold} opacity={p(f,190,212)}>A living knowledge graph</Text>
 </Stage>
};
