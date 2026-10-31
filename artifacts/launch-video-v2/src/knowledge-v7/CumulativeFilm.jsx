import React from 'react';
import {useCurrentFrame,staticFile} from 'remotion';
import {C,colors,papers,nodes,edges,p,mix,band,paperPose,pose,projection} from './model';

const captions=[
 [0,162,['Research output','is outgrowing our capacity','to make sense of it'],104],
 [162,342,['The paper remains the main','unit of research output'],104],
 [342,522,['Connections among findings','remain largely implicit'],104],
 [522,762,['Knowledge synthesis repeatedly','reconstructs these relationships'],97],
 [762,972,['What if this work','became cumulative?'],114],
 [972,1122,['AI can structure findings','and make their connections explicit'],96],
 [1122,1392,['Organized knowledge supports','many forms of synthesis'],103],
 [1392,1632,['Explore patterns, differences,','and gaps interactively'],104],
 [1632,1872,['New questions build on','knowledge already organized'],105],
 [1872,2112,['Change the scope of a synthesis','without rebuilding its foundation'],97],
 [2112,2412,['As new research is incorporated,','knowledge and syntheses evolve'],98],
 [2412,2652,['Open to visual exploration','and automated analysis'],106],
 [2652,2880,['Rethink knowledge storage','Transform knowledge synthesis'],106],
];

const Page=({x,y,s=1,color=C.gold,opacity=1})=><g transform={`translate(${x} ${y}) scale(${s})`} opacity={opacity}>
 <rect x="-66" y="-85" width="132" height="170" rx="4" fill={C.paper}/>
 <rect x="-45" y="-62" width="74" height="7" rx="2" fill={color}/>
 {[0,1,2,3,4,5].map(j=><path key={j} d={`M-45 ${-36+j*18} H${j%3?44:20}`} stroke={C.bg} strokeWidth="4" opacity=".3"/>)}
</g>;

const Caption=({f})=><g>{captions.map(([a,b,lines,size])=>{
 const alpha=band(f,a-6,a+20,b-18,b+1);if(!alpha)return null;
 return <g key={a} opacity={alpha}>{lines.map((line,i)=><text key={line} x={a===0?960:108} y={(a===0?345:150)+i*size*1.13+mix(18,0,p(f,a+i*3,a+20+i*3))} textAnchor={a===0?'middle':'start'} fontSize={size} letterSpacing="-3.5" fill={i===lines.length-1?C.gold:C.paper}>{line}</text>)}</g>;
})}</g>;

const Publications=({f})=>{
 const reconstruct=band(f,516,572,783,833),dissolve=1-p(f,804,928);
 return <g>
  <g opacity={dissolve}>
   {papers.map(r=>{const a=paperPose(r.i,f),newPaper=r.i%30>=21?p(f,628+(r.i%30-21)*12,663+(r.i%30-21)*12):1;
    return <Page key={r.i} {...a} color={r.color} opacity={mix(.65,1,p(f,70,164))*mix(1,newPaper,reconstruct)}/>;
   })}
   <g opacity={band(f,354,405,503,546)}>
    {[0,1,2,3,4,5,6,7].map(i=>{const a=paperPose(17+i*9,f),b=paperPose(82+i*3,f);return <path key={i} d={`M${a.x} ${a.y} C${a.x+100} ${a.y-50} ${b.x-100} ${b.y+40} ${b.x} ${b.y}`} fill="none" stroke={colors[i%4]} strokeWidth="3" strokeDasharray="5 13" opacity={p(f,365+i*8,420+i*8)*.7}/>;})}
   </g>
  </g>
  <g opacity={reconstruct}>
   <text x="168" y="365" fill={C.paper} fontSize="43">The published literature</text>
   <path d="M168 590 H1790" stroke={C.muted} strokeWidth="2" opacity=".45"/>
   <path d={`M${mix(1240,1790,p(f,636,750))} 401 V605`} stroke={C.gold} strokeWidth="3"/>
   {['Review','Meta-analysis'].map((label,k)=>{
    const x=440+k*560,start=561+k*65;
    return <g key={label} opacity={p(f,start,start+25)}>
     <rect x={x-215} y="654" width="440" height="284" rx="9" fill={C.bg} stroke={colors[k]} strokeWidth="2"/>
     <text x={x-177} y="717" fill={C.paper} fontSize="44">{label}</text>
     {Array.from({length:40},(_,j)=>{
      const source=paperPose((j*7+k*11)%80,f),q=p(f,start+j%10*2,start+56+j%10*2),tx=305+k*560+j%10*30,ty=776+Math.floor(j/10)*33;
      return <g key={j}><path d={`M${tx-10} ${ty} H${tx+22}`} stroke={colors[k]} strokeWidth="2" opacity={p(f,start+49+j%10,start+74+j%10)*.4}/><rect x={mix(source.x,tx,q)-4} y={mix(source.y,ty,q)-4} width="8" height="8" rx="3" fill={colors[j%4]} opacity={p(f,start+j%10*2,start+20+j%10*2)}/></g>;
     })}
    </g>;
   })}
   <text x="1490" y="774" textAnchor="middle" fill={C.gold} fontSize="44" opacity={p(f,677,704)}>Focused questions</text>
   <text x="1490" y="831" textAnchor="middle" fill={C.paper} fontSize="44" opacity={p(f,700,727)}>Temporary snapshots</text>
  </g>
 </g>;
};

const Knowledge=({f})=>{
 const positions=nodes.map(n=>pose(n,f)),alpha=p(f,798,847),ending=p(f,2630,2740);
 const fresh=i=>i<324?1:p(f,2150+Math.floor((i-324)/12)*62,2220+Math.floor((i-324)/12)*62);
 const highlight=band(f,1410,1450,1570,1610);
 return <g opacity={alpha*mix(1,.42,ending)}>
  {edges.map((e,i)=>{const a=positions[e.a],b=positions[e.b];return <path key={i} d={`M${a.x} ${a.y} Q${(a.x+b.x)/2+8} ${(a.y+b.y)/2-9} ${b.x} ${b.y}`} fill="none" stroke={nodes[e.a].c} strokeWidth={1.6+highlight*(e.a%6===2?1.3:0)} opacity={p(f,862+i%23,969+i%23)*.3*fresh(e.a)*fresh(e.b)}/>;})}
  {nodes.map((n,i)=>{const a=positions[i],r=mix(5.5,7.5,highlight*(n.group===2?1:0));return <circle key={i} cx={a.x} cy={a.y} r={r} fill={n.c} opacity={fresh(i)}/>;})}
  <text x="474" y="393" fill={C.paper} textAnchor="middle" fontSize="44" opacity={band(f,1185,1230,2620,2690)}>Organized findings</text>
 </g>;
};

const Syntheses=({f})=>{
 const visible=band(f,1140,1185,2620,2690),views=p(f,1180,1255),active=band(f,1405,1440,1590,1630),growth=p(f,2150,2370);
 const context=p(f,1660,1720)*(1-p(f,1880,1940)),time=p(f,1880,1940),access=p(f,2412,2490);
 return <g opacity={visible}>
  <g opacity={views}>
   <path d="M967 404 V984" stroke={C.muted} strokeWidth="2" opacity=".24"/>
   <text x="1410" y="396" textAnchor="middle" fontSize="44" fill={C.paper} opacity={1-access}>Research patterns</text>
   <text x="1410" y="396" textAnchor="middle" fontSize="44" fill={C.paper} opacity={access}>Visual exploration</text>
   <text x="1410" y="735" textAnchor="middle" fontSize="44" fill={C.paper} opacity={1-access}>Evidence coverage</text>
   <text x="1410" y="711" textAnchor="middle" fontSize="44" fill={C.paper} opacity={access}>Programmatic access</text>
   <path d="M1011 663 H1785" stroke={C.muted} strokeWidth="2"/>
  </g>
  {Array.from({length:180},(_,i)=>{const a=projection(i,f);return <g key={i}>
   <path d={`M${a.source.x} ${a.source.y} Q970 ${a.source.y} ${a.x} ${a.y}`} fill="none" stroke={a.c} strokeWidth="1" opacity={Math.sin(a.travel*Math.PI)*.14}/>
   <rect x={a.x-mix(9,87,a.lower?a.access:0)} y={a.y-5} width={mix(18,174,a.lower?a.access:0)} height={a.lower?mix(15,8,a.access):10} rx="3" fill={a.c} opacity={a.travel*a.filled}/>
  </g>;})}
  <g opacity={active}>
   <rect x={mix(1115,1510,p(f,1450,1525))} y="443" width="140" height="210" rx="9" fill="none" stroke={C.gold} strokeWidth="3"/>
   <rect x="1514" y="838" width="241" height="100" rx="8" fill="none" stroke={C.gold} strokeWidth="3" strokeDasharray="8 10" opacity={p(f,1510,1540)}/>
  </g>
  <g opacity={band(f,1630,1680,2060,2115)}>
   {['Methods','Contexts','Time'].map((label,i)=>{
    const selected=i===0?1-context-time:i===1?context:time;
    return <g key={label}><rect x={168+i*206} y="953" width="188" height="66" rx="33" fill={C.bg} stroke={colors[i]} strokeWidth="2"/><rect x={168+i*206} y="953" width="188" height="66" rx="33" fill={colors[i]} opacity={selected}/><text x={262+i*206} y="998" textAnchor="middle" fill={selected>.5?C.bg:C.paper} fontSize="35">{label}</text></g>;
   })}
   <path d="M0 0 L0 35 10 26 19 44 29 38 20 20 33 20Z" fill={C.paper} transform={`translate(${mix(450,684,time)} ${mix(1050,1000,p(f,1635,1690))})`}/>
  </g>
  <g opacity={band(f,2120,2170,2380,2420)}>
   {[0,1,2].map(i=>{
    const start=2140+i*62,t=p(f,start,start+75),dest=pose(nodes[324+i*12],f),pulse=band(f,start+35,start+55,start+89,start+110);
    return <g key={i}>
     <Page x={mix(35,dest.x,t)} y={mix(965,dest.y,t)} s={mix(.6,.04,t)} color={colors[i]} opacity={1-p(t,.75,1)}/>
     <circle cx={dest.x} cy={dest.y} r={mix(9,88,p(f,start+55,start+106))} fill="none" stroke={colors[i]} strokeWidth="3" opacity={pulse*(1-p(f,start+65,start+110))}/>
     <path d={`M${dest.x} ${dest.y} C880 ${dest.y} 929 620 1040 620`} fill="none" stroke={colors[i]} strokeWidth="3" pathLength="1" strokeDasharray=".12 .88" strokeDashoffset={-p(f,start+64,start+111)} opacity={pulse}/>
    </g>;
   })}
  </g>
  <g opacity={access}>
   {['Finding','Context','Relation'].map((label,i)=><text key={label} x={1110+i*246} y="767" textAnchor="middle" fill={colors[i]} fontSize="38">{label}</text>)}
   <path d="M794 793 C922 793 912 906 1011 906" stroke={C.purple} strokeWidth="3" strokeDasharray="6 9" strokeDashoffset={-f*.4} fill="none"/>
  </g>
 </g>;
};

export const KnowledgeSynthesisFilmV7=()=>{
 const f=useCurrentFrame();
 return <>
  <style>{`@font-face{font-family:KnowledgeV7;src:url('${staticFile('landscape/space-bold.ttf')}')}`}</style>
  <svg viewBox="0 0 1920 1080" width="1920" height="1080" style={{position:'absolute',inset:0,fontFamily:'KnowledgeV7,Arial,sans-serif',fontWeight:700}}>
   <defs><linearGradient id="cumulative-bg" x2="1" y2="1"><stop stopColor="#191722"/><stop offset="1" stopColor="#0a121a"/></linearGradient><linearGradient id="cumulative-header" x2="0" y2="1"><stop offset=".83" stopColor={C.bg}/><stop offset="1" stopColor={C.bg} stopOpacity="0"/></linearGradient></defs>
   <rect width="1920" height="1080" fill="url(#cumulative-bg)"/>
   {f<930&&<Publications f={f}/>}
   {f>797&&<Knowledge f={f}/>}
   {f>1130&&<Syntheses f={f}/>}
   <rect width="1920" height="325" fill="url(#cumulative-header)" opacity={p(f,110,163)}/>
   <rect width="1920" height="1080" fill={C.bg} opacity={.55*(1-p(f,108,163))}/>
   <Caption f={f}/>
  </svg>
 </>;
};
