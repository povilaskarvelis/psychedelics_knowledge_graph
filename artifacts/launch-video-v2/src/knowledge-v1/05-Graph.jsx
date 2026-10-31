import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C,Canvas,Headline,Paper,p,mix} from './shared';

// The categories are deliberately generic: this is the structure, not a claim
// about a particular finding or a particular research field.
export const graphNodes=[
  {x:226,y:438,w:203,label:'Study',kind:'paper',color:C.paper},
  {x:245,y:766,w:203,label:'Study',kind:'paper',color:C.paper},
  {x:638,y:348,w:230,label:'Method',color:C.blue},
  {x:680,y:625,w:275,label:'Population',color:C.mint},
  {x:1012,y:475,w:228,label:'Finding',color:C.gold},
  {x:1041,y:790,w:230,label:'Finding',color:C.gold},
  {x:1410,y:341,w:204,label:'Topic',color:C.violet},
  {x:1419,y:664,w:235,label:'Outcome',color:C.teal},
  {x:1664,y:875,w:205,label:'Study',kind:'paper',color:C.paper},
  {x:736,y:897,w:228,label:'Context',color:C.violet},
  {x:1687,y:488,w:225,label:'Comparator',color:C.blue},
];
export const graphEdges=[[0,2],[0,3],[0,4],[1,3],[1,5],[1,9],[2,4],[2,6],[3,4],[3,5],[4,6],[4,7],[4,10],[5,7],[5,9],[5,8],[6,7],[7,8],[7,10],[8,10]];

const Card=({d,opacity=1,focus=1})=><g opacity={opacity*focus} transform={`translate(${d.x} ${d.y})`}>
  <rect x={-d.w/2} y="-46" width={d.w} height="92" rx="15"
    fill={d.kind==='paper'?C.paper:'#11251f'} stroke={d.kind==='paper'?C.paper:d.color} strokeWidth="3"/>
  <rect x={-d.w/2} y="-46" width="9" height="92" rx="4.5" fill={d.color}/>
  {d.kind==='paper'&&<g opacity=".46" fill={C.ink}><rect x={-d.w/2+25} y="-25" width="26" height="5" rx="2"/><rect x={-d.w/2+25} y="-7" width="26" height="5" rx="2"/><rect x={-d.w/2+25} y="11" width="26" height="5" rx="2"/></g>}
  <text x={d.kind==='paper'?13:0} y="14" fill={d.kind==='paper'?C.ink:C.white} textAnchor="middle" fontSize={d.label.length>9?31:37} letterSpacing="-1.1">{d.label}</text>
</g>;

export const Network=({frame,focusIds=null,transform='',edgeStart=34,opacity=1})=><g transform={transform} opacity={opacity}>
  {graphEdges.map(([a,b],i)=>{
    const from=graphNodes[a],to=graphNodes[b];
    const t=p(frame,edgeStart+i*3.7,edgeStart+47+i*3.7);
    const chosen=!focusIds||focusIds.includes(a)&&focusIds.includes(b);
    const bend=(i%2===0?-1:1)*(22+i%3*12);
    const path=`M ${from.x} ${from.y} Q ${(from.x+to.x)/2+bend} ${(from.y+to.y)/2-bend} ${to.x} ${to.y}`;
    return <path key={i} d={path} fill="none" stroke={chosen?(i%4===0?C.gold:C.teal):C.line}
      strokeWidth={chosen?3.5:2} opacity={t*(chosen?.72:.13)} pathLength="1"
      strokeDasharray="1" strokeDashoffset={1-t} strokeLinecap="round"/>;
  })}
  {graphNodes.map((d,i)=><Card key={i} d={d} opacity={p(frame,11+i*6.2,46+i*6.2)} focus={!focusIds||focusIds.includes(i)?1:.19}/>)}
  {[0,1,2,3,4,5,6,7].map(i=>{
    const x=334+i*182,y=298+((i*7)%4)*176;
    return <circle key={i} cx={x} cy={y} r={5+(i%3)*3} fill={[C.mint,C.blue,C.violet,C.gold][i%4]} opacity={p(frame,89+i*8,131+i*8)*.5}/>;
  })}
</g>;

export const Graph=()=>{
  const f=useCurrentFrame();
  const intro=p(f,0,36);
  return <Canvas>
    {[0,1,2].map(i=>{
      const t=p(f,9+i*10,81+i*10);
      return <Paper key={i} x={mix(1085+i*60,250+i*35,t)} y={mix(500+i*45,805+i*15,t)}
        w={105} h={143} opacity={(1-p(f,77,128))*.58} rotation={mix(14,-5+i*5,t)} accent={[C.mint,C.blue,C.gold][i]}/>;
    })}
    <Network frame={f}/>
    <rect x="0" y="0" width="1920" height="263" fill={C.bg} opacity=".96"/>
    <Headline lines={['Study details become','connected knowledge']} size={100} opacity={intro}/>
  </Canvas>;
};
