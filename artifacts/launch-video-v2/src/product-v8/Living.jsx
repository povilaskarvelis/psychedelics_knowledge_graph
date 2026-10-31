import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Stage,Title,Svg,AreaGraph,Paper,Link,p,mix} from '../product/shared';
export const Living=()=>{
 const f=useCurrentFrame();
 return <Stage><Title size={112}>Living knowledge synthesis</Title><Svg>
  <AreaGraph labelAbove x1={740} x2={1190} y1={425} gap1={220} y2={310} gap2={66}/>
  {Array.from({length:12},(_,i)=>{const lane=i%3,col=Math.floor(i/3),start=18+col*53+lane*9,q=p(f,start,start+43),x=mix(-110,175+col*100,q),y=350+lane*220+col*31;return <g key={i}><Link id={`living-v8-${i}`} x1={x+26} y1={y} x2={740} y2={425+lane*220} progress={p(f,start+32,start+64)} width={2.5} opacity={.48}/><Paper x={x} y={y} w={65} color="#80b7a3" opacity={p(f,start,start+12)}/></g>;})}
 </Svg></Stage>;
};
