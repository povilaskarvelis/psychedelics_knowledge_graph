import React from 'react';
import {useCurrentFrame,staticFile} from 'remotion';
import {C,colors,papers,nodes,edges,p,mix,rnd,band,paperPose,pose} from './model';

const captions=[
 [0,162,['Research output','is outgrowing our capacity','to make sense of it'],104],
 [162,342,['The paper remains the main','unit of research output'],104],
 [342,522,['Connections among findings','remain largely implicit'],104],
 [522,762,['Knowledge synthesis struggles','to keep pace'],108],
 [762,972,['What if these connections were','explicit, searchable, navigable?'],96],
 [972,1122,['This is now possible with AI'],112],
 [1122,1392,['Compare findings across studies','in seconds'],105],
 [1392,1632,['See where results converge,','differ, or leave gaps'],106],
 [1632,1872,['Trace findings and conclusions','back to the papers'],104],
 [1872,2112,['Build new syntheses','without starting from scratch'],106],
 [2112,2412,['New papers update the graph','and its connected analyses'],104],
 [2412,2652,['Give researchers and AI','direct access to structured evidence'],94],
 [2652,2850,['Rethink how knowledge is stored','Transform how it is synthesized'],100],
];

const Page=({x,y,s=1,color=C.gold,opacity=1})=><g transform={`translate(${x} ${y}) scale(${s})`} opacity={opacity}>
 <rect x="-66" y="-85" width="132" height="170" rx="4" fill={C.paper}/>
 <rect x="-45" y="-62" width="74" height="7" rx="2" fill={color}/>
 {[0,1,2,3,4,5].map(j=><path key={j} d={`M-45 ${-36+j*18} H${j%3?44:20}`} stroke={C.bg} strokeWidth="4" opacity=".3"/>)}
</g>;

const Caption=({f})=><g>{captions.map(([a,b,lines,size])=>{
 const alpha=band(f,a-8,a+18,b-17,b+1);if(!alpha)return null;
 const intro=a===0;
 return <g key={a} opacity={alpha}>{lines.map((line,i)=><text key={line} x={intro?960:110} y={(intro?345:150)+i*size*1.13+mix(20,0,p(f,a+i*3,a+19+i*3))} textAnchor={intro?'middle':'start'} fontSize={size} letterSpacing="-3.5" fill={i===lines.length-1?C.gold:C.paper}>{line}</text>)}</g>;
})}</g>;

const Archive=({f})=>{
 const synthesis=band(f,514,574,724,790),opening=1-p(f,105,164),fade=1-p(f,804,899);
 return <g opacity={fade}>
  {papers.map(r=>{const a=paperPose(r.i,f),emerging=r.i%30>=20?p(f,608+(r.i%30-20)*10,639+(r.i%30-20)*10):1;
   return <Page key={r.i} {...a} color={r.color} opacity={mix(.66,1,p(f,60,164))*mix(1,emerging,synthesis)}/>;
  })}
  <g opacity={band(f,360,402,504,538)}>
   {[0,1,2,3,4,5,6,7].map(i=>{const a=paperPose(17+i*9,f),b=paperPose(82+i*3,f),draw=p(f,365+i*7,411+i*7);return <path key={i} d={`M${a.x} ${a.y} C${a.x+100} ${a.y-50} ${b.x-100} ${b.y+40} ${b.x} ${b.y}`} fill="none" stroke={colors[i%4]} strokeWidth="3" strokeDasharray="5 13" opacity={draw*.72}/>;})}
  </g>
  <g opacity={synthesis}>
   <text x="170" y="369" fill={C.paper} fontSize="40">Published research</text>
   <path d="M170 596 H1795" stroke={C.muted} strokeWidth="2" opacity=".45"/>
   <path d={`M${mix(1110,1795,p(f,605,731))} 402 V612`} stroke={C.gold} strokeWidth="3"/>
   {['Review','Meta-analysis'].map((label,i)=>{
    const reveal=p(f,566+i*28,611+i*28),x=440+i*560;
    return <g key={label} opacity={reveal}>
     <path d={`M${x} 580 V650`} stroke={colors[i]} strokeWidth="3" strokeDasharray="6 8"/>
     <rect x={x-220} y="656" width="440" height="278" rx="9" fill={C.bg} stroke={colors[i]} strokeWidth="3"/>
     <text x={x-182} y="716" fill={C.paper} fontSize="43">{label}</text>
     {[0,1,2,3].map(j=><g key={j}><path d={`M${x-177} ${760+j*35} H${x+174}`} stroke={colors[i]} strokeWidth="3" opacity=".4"/><circle cx={x-70+(j%3)*60} cy={760+j*35} r="7" fill={colors[i]}/></g>)}
    </g>;
   })}
   <text x="1500" y="783" fill={C.gold} fontSize="43" textAnchor="middle" opacity={p(f,642,674)}>New papers</text>
   <text x="1500" y="840" fill={C.paper} fontSize="43" textAnchor="middle" opacity={p(f,659,691)}>beyond the snapshot</text>
  </g>
 </g>;
};

const Connected=({f})=>{
 const positions=nodes.map(n=>pose(n,f)),alpha=p(f,800,846),closing=p(f,2630,2710);
 return <g opacity={alpha*mix(1,.35,closing)}>
  {edges.map((e,i)=>{const a=positions[e.a],b=positions[e.b],plots=Math.max(a.compare,a.patterns,a.synthesis),split=a.update*(e.a<240&&e.b>=240?1:0);
   return <path key={i} d={`M${a.x} ${a.y} Q${(a.x+b.x)/2+9} ${(a.y+b.y)/2-12} ${b.x} ${b.y}`} fill="none" stroke={nodes[e.a].c} strokeWidth="1.7" opacity={p(f,852+i%23,947+i%23)*(.24+.08*Math.sin(f*.014+i))*(1-plots)* (1-split)}/>;
  })}
  {nodes.map((n,i)=>{const a=positions[i],matrix=a.patterns,plots=Math.max(a.compare,a.synthesis,a.update*(i>=240?1:0));
   const gap=matrix&&i%24>15&&Math.floor(i/24)>7?mix(1,.08,matrix):1;
   return <rect key={i} x={a.x-mix(5,15,matrix)} y={a.y-mix(5,10,plots)} width={mix(10,30,matrix)} height={mix(10,20,plots)} rx={mix(5,2,Math.max(matrix,plots))} fill={n.c} opacity={gap*mix(1,.55,matrix*rnd(i))}/>;
  })}
 </g>;
};

const Demonstrations=({f})=>{
 const compare=band(f,1135,1181,1350,1405),patterns=band(f,1405,1455,1595,1650),trace=band(f,1640,1700,1818,1880),synth=band(f,1870,1930,2065,2125),update=band(f,2120,2180,2385,2445),access=band(f,2420,2480,2635,2690);
 return <g>
  <g opacity={compare}>
   {['Different methods','Different contexts','Different results'].map((label,i)=><g key={label}>
    <text x={389+i*590} y="382" textAnchor="middle" fill={colors[i]} fontSize="40">{label}</text>
    <path d={`M${205+i*590} 899 H${591+i*590}`} stroke={C.muted} strokeWidth="2"/>
   </g>)}
   <rect x={mix(206,1386,p(f,1210,1300))} y="435" width="75" height="447" rx="15" fill={C.paper} opacity=".09"/>
  </g>
  <g opacity={patterns}>
   <text x="288" y="383" fill={C.paper} fontSize="39">Findings across research questions</text>
   <rect x="1218" y="664" width="450" height="245" rx="17" fill="none" stroke={C.gold} strokeWidth="3" strokeDasharray="10 12" opacity={p(f,1500,1540)}/>
   <text x="1443" y="957" textAnchor="middle" fill={C.gold} fontSize="38" opacity={p(f,1515,1560)}>Where evidence is missing</text>
  </g>
  <g opacity={trace}>
   {[0,1,2].map(i=><g key={i} opacity={p(f,1655+i*18,1688+i*18)}>
    <Page x={260+i*175} y={610+i%2*192} s={1.08} color={colors[i]}/>
    <path d={`M${320+i*175} ${610+i%2*192} C810 ${610+i%2*192} 820 672 1130 672`} fill="none" stroke={colors[i]} strokeWidth="3" pathLength="1" strokeDasharray="1" strokeDashoffset={1-p(f,1683+i*16,1746+i*16)}/>
   </g>)}
   <circle cx="1130" cy="672" r="34" fill={C.bg} stroke={C.gold} strokeWidth="4"/>
   <circle cx="1130" cy="672" r={mix(34,68,p(f,1720,1800))} fill="none" stroke={C.gold} strokeWidth="2" opacity={1-p(f,1720,1800)}/>
   <text x="218" y="972" fill={C.paper} fontSize="41">Inspect the original evidence</text>
  </g>
  <g opacity={synth}>
   {['Method','Context','Time'].map((label,i)=>{const selected=i===(f<1985?0:2);return <g key={label}><rect x={470+i*338} y="369" width="296" height="76" rx="38" fill={selected?C.gold:C.bg} stroke={C.gold} strokeWidth="2"/><text x={618+i*338} y="419" fill={selected?C.bg:C.paper} fontSize="38" textAnchor="middle">{label}</text></g>;})}
   <path d="M190 927 H1760" stroke={C.muted} strokeWidth="2"/>
  </g>
  <g opacity={update}>
   <text x="562" y="386" textAnchor="middle" fill={C.paper} fontSize="43">Connected findings</text>
   <text x="1460" y="386" textAnchor="middle" fill={C.paper} fontSize="43">Updated analyses</text>
   <path d="M945 680 C1040 680 1080 680 1175 680" fill="none" stroke={C.gold} strokeWidth="3" opacity=".4"/>
   {[0,1,2].map(i=>{const t=p(f,2190+i*61,2245+i*61),pulse=band(f,2190+i*61,2200+i*61,2239+i*61,2254+i*61);return <g key={i}>
    <Page x={mix(130,510,t)} y={mix(935,685,t)} s={mix(.55,.04,t)} opacity={1-p(t,.8,1)} color={colors[i]}/>
    <circle cx="565" cy="680" r={mix(10,190,t)} fill="none" stroke={colors[i]} strokeWidth="3" opacity={pulse*(1-t)}/>
    <circle cx={mix(950,1180,t)} cy="680" r="10" fill={colors[i]} opacity={pulse}/>
    {[0,1,2,3,4,5].map(j=><rect key={j} x={1230+j*79} y={mix(890,690-j*32,p(f,2240+i*61,2270+i*61))} width="42" height={mix(0,200+j*32,p(f,2240+i*61,2270+i*61))} rx="3" fill={colors[i]} opacity={pulse*.65}/>)}
   </g>;})}
  </g>
  <g opacity={access}>
   <rect x="132" y="481" width="390" height="376" rx="17" fill={C.bg} stroke={C.blue} strokeWidth="2"/>
   <text x="169" y="541" fill={C.paper} fontSize="36">Visual exploration</text>
   {[0,1,2,3,4].map(i=><rect key={i} x={178+i*59} y={762-i*29} width="35" height={44+i*29} rx="4" fill={colors[i%4]}/>)}
   <path d="M415 607 l-27 55 28-10 17 25 13-9-17-25 25-7z" fill={C.paper} transform={`translate(${mix(-80,0,p(f,2460,2520))} ${mix(80,0,p(f,2460,2520))})`}/>
   <rect x="1400" y="481" width="390" height="376" rx="17" fill={C.bg} stroke={C.purple} strokeWidth="2"/>
   <text x="1437" y="541" fill={C.paper} fontSize="36">Automated analysis</text>
   {[0,1,2,3].map(i=><g key={i} opacity={p(f,2480+i*17,2510+i*17)}><rect x="1442" y={590+i*51} width="53" height="24" rx="4" fill={colors[i]}/><path d={`M1520 ${602+i*51} H1745`} stroke={C.paper} strokeWidth="5" opacity=".55"/></g>)}
   {[0,1].map(i=><path key={i} d={i?'M1240 666 H1398':'M522 666 H690'} stroke={i?C.purple:C.blue} strokeWidth="3" strokeDasharray="6 9" strokeDashoffset={-f*.6} fill="none"/>)}
  </g>
 </g>;
};

export const KnowledgeSynthesisFilmV7=()=>{
 const f=useCurrentFrame();
 return <>
  <style>{`@font-face{font-family:KnowledgeV7;src:url('${staticFile('landscape/space-bold.ttf')}')}`}</style>
  <svg viewBox="0 0 1920 1080" width="1920" height="1080" style={{position:'absolute',inset:0,fontFamily:'KnowledgeV7,Arial,sans-serif',fontWeight:700}}>
   <defs><linearGradient id="v7bg" x2="1" y2="1"><stop stopColor="#191722"/><stop offset="1" stopColor="#0a121a"/></linearGradient><linearGradient id="v7header" x2="0" y2="1"><stop offset=".8" stopColor={C.bg}/><stop offset="1" stopColor={C.bg} stopOpacity="0"/></linearGradient></defs>
   <rect width="1920" height="1080" fill="url(#v7bg)"/>
   {f<902&&<Archive f={f}/>}
   {f>800&&<Connected f={f}/>}
   <Demonstrations f={f}/>
   <rect width="1920" height="324" fill="url(#v7header)" opacity={p(f,110,163)}/>
   <rect width="1920" height="1080" fill={C.bg} opacity={.52*(1-p(f,108,163))}/>
   <Caption f={f}/>
  </svg>
 </>;
};
