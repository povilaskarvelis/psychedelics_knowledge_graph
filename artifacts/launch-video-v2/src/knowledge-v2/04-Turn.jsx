import React from 'react';
import {useCurrentFrame} from 'remotion';
import {BackGrid,C,Headline,KnowledgeWeb,Paper,Stage,TopScrim,webCenters,mix,p} from './shared';

const bits=Array.from({length:144},(_,i)=>{
  const row=Math.floor(i/18),col=i%18;
  return {
    x:50+col*108+((row*23)%41),
    y:330+row*87+((i*17)%43-21),
    target:webCenters[(i*7+Math.floor(i/9))%6],
    color:[C.mint,C.blue,C.violet,C.gold][i%4],
    delay:(i*13)%79,
    width:20+((i*19)%45),
  };
});

export const Turn=()=>{
  const f=useCurrentFrame();
  const camera=p(f,228,354);
  const transform=`translate(${mix(0,700,camera)} ${mix(0,230,camera)}) scale(${mix(1,.65,camera)})`;
  const graph=p(f,92,175);
  return <Stage>
    <BackGrid opacity={mix(.18,.07,graph)} offset={-f*.37}/>
    <g opacity={1-p(f,60,164)}>
      {Array.from({length:34},(_,i)=><Paper key={i} x={121+(i%9)*208} y={371+Math.floor(i/9)*168}
        w={128} h={173} rotation={((i*31)%25)-12} opacity={.21} accent={[C.gold,C.mint,C.blue,C.violet][i%4]}/>)}
    </g>
    {bits.map((d,i)=>{
      const t=p(f,19+d.delay*.62,112+d.delay*.62);
      const depart=p(f,8+d.delay*.45,42+d.delay*.45);
      const x=mix(d.x,d.target.x,t)+Math.sin(Math.PI*t)*((i%2)?-87:95);
      const y=mix(d.y,d.target.y,t)-Math.sin(Math.PI*t)*(87+(i%5)*22);
      const gone=p(f,130+d.delay*.37,171+d.delay*.37);
      return <g key={i} opacity={depart*(1-gone)} transform={`translate(${x} ${y}) rotate(${mix((i%5-2)*8,0,t)})`}>
        <rect x={-d.width/2} y="-4" width={d.width} height="8" rx="4" fill={d.color}/>
        {i%5===0&&<circle cx="0" cy="0" r="12" fill={d.color} opacity=".17" filter="url(#v2-soft-glow)"/>}
      </g>;
    })}
    <KnowledgeWeb frame={(f-89)*1.19} progress={graph} opacity={graph} transform={transform}/>
    <TopScrim height={285} opacity={.95}/>
    <Headline lines={['Now the connections','can be stored too']} size={110} opacity={p(f,50,82)*(1-p(f,336,362))} colors={[C.cream,C.gold]}/>
  </Stage>;
};
