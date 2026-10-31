import React from 'react';
import {useCurrentFrame} from 'remotion';
import {BackGrid,C,Headline,KnowledgeWeb,Stage,TopScrim,mix,p} from './shared';

export const Shape=()=>{
  const f=useCurrentFrame();
  const breadth=p(f,37,235);
  const camera=`translate(${mix(-161,242,breadth)} ${mix(-141,173,breadth)}) scale(${mix(1.2,.83,breadth)})`;
  return <Stage>
    <BackGrid opacity={.08} offset={-f*.23}/>
    <KnowledgeWeb frame={f*.78} opacity={p(f,3,39)} transform={camera}/>
    <TopScrim height={297} opacity={.92}/>
    <Headline lines={['Science advances by','connecting what we learn']} size={105}
      opacity={p(f,5,37)*(1-p(f,226,252))} colors={[C.cream,C.gold]}/>
  </Stage>;
};
