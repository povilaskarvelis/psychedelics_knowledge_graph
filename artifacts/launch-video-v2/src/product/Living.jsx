import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,AreaGraph,Paper,Link,Label,p,mix} from './shared';

export const Living=()=>{
 const f=useCurrentFrame();
 return <Stage><Title size={110}>Growing with the research</Title><Svg>
  <AreaGraph labelAbove x1={740} x2={1190} y1={425} gap1={220} y2={310} gap2={66}/>
  {Array.from({length:9},(_,i)=>{
   const lane=i%3,col=Math.floor(i/3),start=24+col*64+lane*11;
   const q=p(f,start,start+46),x=mix(-150-col*90,185+col*125,q),y=mix(300+lane*275,350+lane*220+col*46,q);
   return <g key={i}><Link id={`new-paper-${i}`} x1={x+26} y1={y} x2={740} y2={425+lane*220} progress={p(f,start+32,start+72)} width={2.5} opacity={.48}/><Paper x={x} y={y} w={70} color="#80b7a3" opacity={p(f,start,start+12)}/></g>;
  })}
 </Svg></Stage>;
};
