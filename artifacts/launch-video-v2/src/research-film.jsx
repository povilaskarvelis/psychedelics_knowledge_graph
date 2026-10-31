import React from 'react';
import {AbsoluteFill,Audio,staticFile,useCurrentFrame,interpolate,Easing} from 'remotion';
import corpus from './story-data.json';
import source from './v6-data.json';

// Editorial grammar: one large message; no subtitles, source records or footnotes.
// The graph is a travelling, open network. There are no radial layouts.
const BG='#09110f',FG='#f3f4ed',MINT='#8bdbbf',MUTED='#b2c9bd';
const font='FilmSpace,Arial,sans-serif';
const ease=Easing.bezier(.65,0,.18,1);
const tween=(f,a,b,x=0,y=1)=>interpolate(f,[a,b],[x,y],{extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:ease});
const linear=(f,a,b,x=0,y=1)=>interpolate(f,[a,b],[x,y],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
const mix=(x,y,p)=>x+(y-x)*p;
const show=(f,a,b)=>tween(f,a,a+12)*(1-tween(f,b-12,b));
const compounds=source.rows.filter(r=>r.name.length<22&&r.name!=='DOI');
const areas=corpus.broad[0].areas;
const cell=(key,area)=>source.cells.find(c=>c.compound===key&&c.area===area)?.count||0;
const focusNames=['Ibogaine','Mescaline','5-MeO-DMT'];
const focusAreas=['Targets','Molecular effects','Cognition','Subjective effects'];
function Label({children,x=960,y=150,size=96,fill=FG,anchor='middle',opacity=1}){return <text x={x} y={y} fontSize={size} fill={fill} textAnchor={anchor} letterSpacing={size>=80?-3:-1} opacity={opacity}>{children}</text>}
function Head({f,start,end,children,y=150,size=96}){return <g opacity={show(f,start,end)} transform={`translate(0,${tween(f,start,start+22,24,0)})`}><Label y={y} size={size}>{children}</Label></g>}
function Edge({a,b,color=MINT,width=3,opacity=1,p=1}){return <path d={`M ${a.x} ${a.y} C ${mix(a.x,b.x,.47)} ${a.y},${mix(a.x,b.x,.53)} ${b.y},${b.x} ${b.y}`} pathLength="1" strokeDasharray="1" strokeDashoffset={1-p} stroke={color} strokeWidth={width} fill="none" strokeLinecap="round" opacity={opacity}/>}
function Document({x,y,s=1,opacity=1,r=0}){return <g transform={`translate(${x} ${y}) rotate(${r}) scale(${s})`} opacity={opacity}><rect x="-55" y="-75" width="110" height="150" rx="7" fill="#e6ecdf"/><rect x="-33" y="-49" width="44" height="8" rx="3" fill="#709485"/>{[0,1,2,3].map(i=><rect key={i} x="-33" y={-20+i*19} width={i===3?39:66} height="4" rx="2" fill="#8fa89a"/>)}</g>}

function Opening({f}){const z=tween(f,0,135,1.9,.80),form=tween(f,139,176);return <g>
 {Array.from({length:180},(_,i)=>{const x=960+((i%20)-9.5)*153*z,y=550+(Math.floor(i/20)-4)*189*z;return <Document key={i} x={mix(x,-400+(i%3)*70,form)} y={mix(y,240+i%8*100,form)} s={mix(z,.3,form)} r={(i%5-2)*2} opacity={.12*(1-form)}/>})}
 <Head f={f} start={-12} end={86} y={550} size={134}>Psychedelic research.</Head>
 <g opacity={show(f,82,168)}><Label y={505} size={200}>21,735</Label><Label y={621} size={91} fill={MINT}>research papers</Label></g>
 </g>}

function Network({f}){
 const focus=tween(f,349,404),scroll=tween(f,180,345,0,1840),grow=tween(f,556,648);
 const areaPos=(a,j)=>{
  const idx=focusAreas.indexOf(a.name);return {x:mix(1135,1210,focus),y:mix(265+j*76,idx>=0?345+idx*181:1460+j*70,focus)};
 };
 const compoundPos=(c,i)=>{
  const idx=focusNames.indexOf(c.name);return {x:mix(460,430,focus),y:mix(300+i*112-scroll,idx>=0?380+idx*255:-350-i*70,focus)};
 };
 const opacity=tween(f,164,190)*(1-tween(f,680,705));
 return <g opacity={opacity}>
 <defs><clipPath id="network-viewport"><rect x="0" y="235" width="1920" height="795"/></clipPath><linearGradient id="network-fade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="black"/><stop offset=".065" stopColor="white"/><stop offset=".94" stopColor="white"/><stop offset="1" stopColor="black"/></linearGradient><mask id="network-mask"><rect x="0" y="235" width="1920" height="795" fill="url(#network-fade)"/></mask></defs>
 <g clipPath="url(#network-viewport)" mask="url(#network-mask)">
 {compounds.flatMap((c,i)=>areas.map((a,j)=>{const count=cell(c.key,a.name),p=compoundPos(c,i),q=areaPos(a,j),selected=focusNames.includes(c.name)&&focusAreas.includes(a.name);return count?<Edge key={`${c.key}-${a.name}`} a={{x:p.x+190,y:p.y}} b={q} color={a.color} width={1.2+Math.sqrt(count)/20} p={tween(f,180+i*1.3+j,214+i*1.3+j)} opacity={selected?.68:.20*(1-focus)}/>:null;}))}
 {compounds.map((c,i)=>{const p=compoundPos(c,i),active=focusNames.includes(c.name);return <g key={c.key} opacity={active?1:1-focus}>
 <rect x={p.x-270} y={p.y-42} width="540" height="84" rx="42" fill="#0f251d" stroke="#74b397" strokeWidth="2"/>
 <Label x={p.x} y={p.y+19} size={56}>{c.name}</Label>
 {Array.from({length:5},(_,j)=><g key={j}><Edge a={{x:27+j*21,y:p.y-37+j*18}} b={{x:p.x-271,y:p.y}} color={MINT} width={1} opacity={.4}/><circle cx={27+j*21} cy={p.y-37+j*18} r="4" fill={MINT}/></g>)}
 </g>})}
 {areas.map((a,j)=>{const p=areaPos(a,j);return <g key={a.name}><circle cx={p.x} cy={p.y} r="10" fill={a.color}/><Label x={p.x+28} y={p.y+18} size={50} anchor="start">{a.name}</Label></g>})}
 {/* Existing nodes stay put; additional source branches extend the network. */}
 {focusAreas.map((name,j)=>{const a=areas.find(x=>x.name===name),base=areaPos(a,areas.indexOf(a));return <g key={name}>{Array.from({length:8},(_,k)=>{const q={x:1530+(k%4)*76,y:base.y+90+Math.floor(k/4)*27},start=555+j*10+k*4,p=tween(f,start,start+37);return <g key={k}><path d={`M ${base.x} ${base.y+12} L ${base.x} ${base.y+55} C ${base.x+60} ${q.y},${q.x-160} ${q.y},${q.x} ${q.y}`} pathLength="1" strokeDasharray="1" strokeDashoffset={1-p} fill="none" stroke={a.color} opacity={.55*grow} strokeWidth="2"/><rect x={q.x-7*p} y={q.y-7*p} width={14*p} height={14*p} rx="3" fill={a.color}/></g>})}</g>})}
 </g>
 <Head f={f} start={167} end={354} size={96}>One connected knowledge graph.</Head>
 <Head f={f} start={355} end={541} size={83}>From molecules to lived experience.</Head>
 <Head f={f} start={541} end={696} size={99}>Grows with the research.</Head>
 </g>
}

function MiniGraph({f,x=0,y=0,scale=1,opacity=1}){const ns=[{x:70,y:230},{x:250,y:80},{x:260,y:350},{x:480,y:185},{x:630,y:70},{x:645,y:340},{x:800,y:210}];const links=[[0,1],[0,2],[1,3],[2,3],[3,4],[3,5],[4,6],[5,6]];return <g transform={`translate(${x} ${y}) scale(${scale})`} opacity={opacity}>{links.map(([a,b],i)=><Edge key={i} a={ns[a]} b={ns[b]} color={areas[i%10].color} width={5} p={tween(f,i*4,i*4+27)}/>)}{ns.map((n,i)=><g key={i}><circle cx={n.x} cy={n.y} r={13} fill={areas[i%10].color}/>{[0,1,2].map(j=><g key={j}><Edge a={n} b={{x:n.x+35+j*18,y:n.y+45+j*20}} color={areas[i%10].color} p={tween(f,35+i*3+j*3,58+i*3+j*3)} opacity={.45}/><circle cx={n.x+35+j*18} cy={n.y+45+j*20} r="4" fill={areas[i%10].color}/></g>)}</g>)}</g>}

function ToolDock({f,active=0,y=945}){return <g opacity={tween(f,699,724)}>
 <rect x="435" y={y-56} width="1050" height="98" rx="49" fill="#10291f" stroke="#517966" strokeWidth="2"/>
 <rect x={451+active*342} y={y-46} width="334" height="78" rx="39" fill={MINT}/>
 {['Graph','Trends','Coverage'].map((name,i)=><Label key={name} x={618+i*342} y={y+12} size={48} fill={active===i?BG:FG}>{name}</Label>)}
 </g>}

function Tools({f}){return <g opacity={show(f,690,817)}>
 <Head f={f} start={690} end={817} y={171} size={113}>Built-in tools to explore.</Head>
 <MiniGraph f={f-691} x={260} y={296} scale={1.45}/>
 <ToolDock f={f}/>
 </g>}

function Trends({f}){const rows=corpus.timeline.filter(r=>r.year<=2025),max=Math.max(...rows.map(r=>r.total));const scan=linear(f,869,987,0,25);return <g opacity={show(f,807,1058)}>
 <Head f={f} start={807} end={1058} y={164} size={109}>Spot research trends.</Head>
 <g opacity={tween(f,819,840)}>{[0,900,1800].map(n=><g key={n}><line x1="280" x2="1750" y1={793-n/max*410} y2={793-n/max*410} stroke="#284735" strokeWidth="2"/><Label x={240} y={809-n/max*410} size={48} anchor="end" fill={MUTED}>{n.toLocaleString()}</Label></g>)}<Label x={280} y={311} size={54} anchor="start" fill={MINT}>Papers</Label></g>
 {rows.map((r,i)=>{const p=tween(f,820+i,853+i);return <g key={r.year}><rect x={280+i*55} y={793-r.total/max*410*p} width="40" height={r.total/max*410*p} rx="5" fill={i<=scan?MINT:'#37584b'}/>{[2000,2010,2020,2025].includes(r.year)&&<Label x={299+i*55} y={858} size={48} fill={MUTED}>{r.year}</Label>}</g>})}
 <ToolDock f={f} active={1} y={982}/>
 </g>}

const matrixNames=['Psilocybin','Ibogaine','Mescaline','5-MeO-DMT'];
const matrixAreas=['Safety','Cognition','Brain regions'];
function Coverage({f}){const focus=tween(f,1190,1223),values=matrixNames.flatMap(name=>matrixAreas.map(area=>cell(source.rows.find(r=>r.name===name).key,area))),max=Math.max(...values);return <g opacity={show(f,1050,1328)}>
 <Head f={f} start={1050} end={1328} size={106} y={157}>Find gaps in coverage.</Head>
 {matrixAreas.map((name,j)=><Label key={name} x={740+j*360} y={313} size={53} opacity={tween(f,1065+j*7,1085+j*7)}>{name}</Label>)}
 {matrixNames.map((name,i)=><g key={name}><Label x={515} y={424+i*130} size={57} anchor="end" opacity={tween(f,1070+i*9,1095+i*9)}>{name}</Label>{matrixAreas.map((area,j)=>{const n=values[i*3+j],p=tween(f,1070+i*8+j*6,1105+i*8+j*6),selected=(i===1&&j===1)||(i===2&&j===2),alpha=selected?1:1-focus*.42;return <g key={area} opacity={p*alpha}>
 <rect x={585+j*360} y={356+i*130} width="310" height="106" rx="14" fill={MINT} fillOpacity={.08+.80*Math.sqrt(n/max)} stroke={selected?MINT:'#395545'} strokeWidth={selected?2+focus*3:1}/>
 <Label x={740+j*360} y={427+i*130} size={62} fill={n>max*.5?BG:FG}>{n}</Label>
 </g>})}</g>)}
 <ToolDock f={f} active={2} y={982}/>
 </g>}

function AI({f}){const p=tween(f,1320,1360),pulse=((f-1370)%65)/65;return <g opacity={show(f,1320,1538)}>
 <Head f={f} start={1320} end={1538} size={108} y={157}>Connect your AI tools.</Head>
 <MiniGraph f={f-1320} x={80} y={355} scale={1.3}/>
 <Edge a={{x:1120,y:628}} b={{x:1500,y:468}} p={tween(f,1365,1400)} color={MINT} width={5}/>
 <Edge a={{x:1120,y:628}} b={{x:1500,y:775}} p={tween(f,1380,1415)} color={MINT} width={5}/>
 {['API','MCP'].map((name,i)=><g key={name} opacity={tween(f,1390+i*15,1410+i*15)}><rect x="1490" y={398+i*307} width="280" height="141" rx="26" fill="#143226" stroke={MINT} strokeWidth="2"/><Label x={1630} y={494+i*307} size={81}>{name}</Label></g>)}
 {f>1415&&[0,1].map(i=>{const u=pulse,v=1-u,x=v*v*v*1120+3*v*v*u*1298.6+3*v*u*u*1321.4+u*u*u*1500,y=v*v*v*628+3*v*v*u*628+3*v*u*u*(i?775:468)+u*u*u*(i?775:468);return <circle key={i} cx={x} cy={y} r="9" fill={MINT}/>})}
 </g>}

function End({f}){return <g opacity={tween(f,1530,1553)}>
 <image href={staticFile('story/favicon.svg')} x="870" y="160" width="180" height="180"/>
 <Label y={532} size={118}>Psychedelics</Label><Label y={670} size={118} fill={MINT}>Knowledge Graph</Label>
 <Label y={850} size={69} opacity={tween(f,1552,1580)}>psychedelicskg.com</Label>
 </g>}

export function ResearchFilm(){const f=useCurrentFrame();return <AbsoluteFill style={{background:BG,overflow:'hidden'}}>
 <style>{`@font-face{font-family:FilmSpace;src:url('${staticFile('landscape/space-bold.ttf')}')}`}</style>
 <AbsoluteFill style={{background:'radial-gradient(ellipse at 55% 70%,#123c2d66,transparent 72%)'}}/>
 <Audio src={staticFile('story/research-soundtrack.wav')} volume={.42}/>
 <svg width="1920" height="1080" style={{fontFamily:font,fontWeight:700}}>
 {f<180&&<Opening f={f}/>}{f>=164&&f<705&&<Network f={f}/>}
 {f>=690&&f<817&&<Tools f={f}/>}{f>=807&&f<1058&&<Trends f={f}/>}
 {f>=1050&&f<1328&&<Coverage f={f}/>}{f>=1320&&f<1538&&<AI f={f}/>}{f>=1530&&<End f={f}/>}
 </svg>
 </AbsoluteFill>}
