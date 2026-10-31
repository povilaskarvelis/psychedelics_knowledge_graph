import React from 'react';
import {useCurrentFrame} from 'remotion';
import {BackGrid,C,Headline,KnowledgeWeb,Paper,Stage,TopScrim,webCenters,mix,p} from './shared';

const papers=Array.from({length:77},(_,i)=>{
  const row=Math.floor(i/11),col=i%11;
  const depth=.63+row*.105;
  return {
    x:960+(col-5)*163*depth+(row%2)*23,
    y:385+row*111+((i*17)%31-15),
    depth,
    r:((i*19)%23)-11,
    color:[C.mint,C.blue,C.violet,C.gold][(row+col)%4],
  };
});

export const Papers=()=>{
  const f=useCurrentFrame();
  const paperBuild=p(f,11,176);
  return <Stage>
    <BackGrid opacity={.07}/>
    <KnowledgeWeb frame={260} transform="translate(242 173) scale(.83)" opacity={(1-p(f,9,83))*.75}/>
    <g transform={`translate(0 ${mix(-36,0,paperBuild)})`}>
      {papers.map((d,i)=>{
        const t=p(f,9+i*1.4,49+i*1.4);
        const source=webCenters[i%6];
        const wobble=Math.sin(f*.021+i*1.73)*5;
        return <Paper key={i} x={mix(242+source.x*.83,d.x,t)} y={mix(173+source.y*.83,d.y,t)+wobble}
          w={132} h={172} rotation={mix(d.r*2,d.r,t)} opacity={t*mix(.48,.85,d.depth/1.3)}
          scale={mix(.38,d.depth,t)} accent={d.color}/>;
      })}
    </g>
    <TopScrim height={284} opacity={.96}/>
    <Headline lines={['But much of it is stored','paper by paper']} size={105} opacity={p(f,3,31)*(1-p(f,226,252))} colors={[C.cream,C.cream]}/>
  </Stage>;
};
