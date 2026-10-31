import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C,Canvas,Headline,Paper,p,mix} from './shared';

const colors=[C.mint,C.blue,C.violet,C.gold];
const papers=Array.from({length:78},(_,i)=>{
  const row=Math.floor(i/13),col=i%13;
  return {
    x:102+col*143+(row%2)*49+((i*19)%17-8),
    y:347+row*114+((i*13)%29-14),
    rotation:((i*29)%23)-11,
    color:colors[(col+row*2)%4],
    order:row*11+((col*7)%13),
  };
});

export const Papers=()=>{
  const f=useCurrentFrame();
  const depth=p(f,18,204);
  return <Canvas>
    <g transform={`translate(${mix(-130,0,depth)} ${mix(-100,0,depth)}) scale(${mix(1.15,1,depth)})`}>
      {papers.map((paper,i)=>{
        const t=p(f,5+paper.order*1.7,43+paper.order*1.7);
        const drift=Math.sin(i*2.14+f*.027)*7;
        return <Paper key={i} x={paper.x} y={paper.y+drift} w={118} h={154}
          rotation={paper.rotation*(.25+.75*t)} opacity={t*.78}
          scale={mix(1.25,1,t)} accent={paper.color}/>;
      })}
    </g>
    <rect x="0" y="0" width="1920" height="287" fill={C.bg} opacity=".94"/>
    <Headline lines={['Research keeps growing']} x={103} y={157} size={105} opacity={p(f,4,25)}/>
    <path d="M 104 230 H 1665" stroke={C.line} strokeWidth="2" opacity={p(f,20,65)*.75}/>
  </Canvas>;
};
