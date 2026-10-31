import React from 'react';
import {AbsoluteFill,Audio,Img,staticFile,useCurrentFrame,interpolate,Easing} from 'remotion';
import data from './story-data.json';
import analysis from './motion-data.json';

const BG='#09110f',FG='#f3f4ed',MINT='#8bdbbf',DIM='#a3b5ac';
const font='FilmSpace,Arial,sans-serif';
const ease=Easing.bezier(.65,0,.2,1);
const t=(f,a,b,x=0,y=1)=>interpolate(f,[a,b],[x,y],{extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:ease});
const lerp=(a,b,p)=>a+(b-a)*p;
const win=(f,a,b)=>t(f,a,a+13)*(1-t(f,b-13,b));
const colors=data.broad[0].areas.map(a=>a.color);
const papers=data.papers;
const nodes=[...data.broad.map((d,i)=>({name:d.compound,color:MINT,type:'compound',i})),...data.broad[0].areas.map((d,i)=>({...d,type:'area',i}))];
const route=(a,b)=>`M ${a.x} ${a.y} C ${lerp(a.x,b.x,.48)} ${a.y},${lerp(a.x,b.x,.52)} ${b.y},${b.x} ${b.y}`;
function Stroke({d,p=1,color=MINT,w=2,opacity=1}){return <path d={d} fill="none" stroke={color} strokeWidth={w} strokeLinecap="round" pathLength="1" strokeDasharray="1" strokeDashoffset={1-p} opacity={opacity}/>}
function Text({children,x=960,y=130,size=80,color=FG,anchor='middle',opacity=1}){return <text x={x} y={y} fill={color} fontSize={size} letterSpacing={size>60?-2:0} textAnchor={anchor} opacity={opacity}>{children}</text>}
function Caption({f,a,b,children,sub,size=82,y=150}){const p=win(f,a,b);return <g opacity={p} transform={`translate(0,${(1-t(f,a,a+20))*22})`}><Text y={y} size={size}>{children}</Text>{sub&&<Text y={y+59} size={31} color={DIM}>{sub}</Text>}</g>}
function Paper({p,x,y,s=1,opacity=1,rotate=0}){return <g transform={`translate(${x} ${y}) rotate(${rotate}) scale(${s})`} opacity={opacity}>
 <rect x="-160" y="-110" width="320" height="220" rx="8" fill="#edf0e4"/>
 <rect x="-138" y="-85" width="56" height="5" rx="2" fill={colors[papers.indexOf(p)%10]||MINT}/>
 <foreignObject x="-138" y="-65" width="278" height="151"><div xmlns="http://www.w3.org/1999/xhtml" style={{color:'#14251f',fontFamily:font,fontSize:22,lineHeight:1.2,display:'-webkit-box',WebkitLineClamp:5,WebkitBoxOrient:'vertical',overflow:'hidden'}}>{p.title}</div></foreignObject>
 <text x="-138" y="93" fontSize="16" fill="#52685b">{p.compound} · {p.year}</text>
 </g>}

function coord(n,radial=0){
 const a=n.type==='compound'?{x:460,y:330+n.i*110}:{x:1290,y:300+n.i*66};
 const j=n.type==='compound'?n.i:n.i+6,theta=j/16*Math.PI*2-Math.PI/2;
 const b={x:960+Math.cos(theta)*610,y:625+Math.sin(theta)*295};
 return {x:lerp(a.x,b.x,radial),y:lerp(a.y,b.y,radial)};
}
function paperCoord(i,radial){const c=Math.floor(i/24),k=i%24;const a={x:145+k%4*44,y:330+c*110+(Math.floor(k/4)-2.5)*14};const angle=i/144*Math.PI*2;const b={x:960+Math.cos(angle)*(390+(i%4)*27),y:625+Math.sin(angle)*(175+(i%4)*17)};return {x:lerp(a.x,b.x,radial),y:lerp(a.y,b.y,radial)}}
function Graph({f,radial=0,opacity=1,labels=1,paperOpacity=1,edges=1,spot=-1,arriving=0}){return <g opacity={opacity}>
 {data.broad.flatMap((c,i)=>c.areas.map((area,j)=>{const a=coord(nodes[i],radial),b=coord(nodes[j+6],radial);return <Stroke key={`${i}-${j}`} d={route(a,b)} color={area.color} p={t(f,30+i*5+j*2,88+i*5+j*2)*edges} w={area.width*.4} opacity={spot<0?.40:spot===i?.8:.035}/>;}))}
 {papers.map((p,i)=>{const a=paperCoord(i,radial),b=coord(nodes[Math.floor(i/24)],radial),future=Array.from({length:12},(_,j)=>(j*13+22)%144).indexOf(i),growth=arriving&&future>=0?t(arriving,653+future*15+63,653+future*15+75):1;return <g key={p.doi} opacity={paperOpacity*growth}><Stroke d={route(a,b)} color={colors[Math.floor(i/24)]} p={t(f,12+i/3,53+i/3)} w={.8} opacity={.18}/><circle cx={a.x} cy={a.y} r={3.6} fill={colors[Math.floor(i/24)]}/></g>})}
 {nodes.map((n,j)=>{const a=coord(n,radial);return <g key={n.name} opacity={t(f,j*2,j*2+24)}>
 <circle cx={a.x} cy={a.y} r={n.type==='compound'?12:8} fill={n.color} stroke={BG} strokeWidth="3"/>
 <g opacity={labels*(1-radial)}>{n.type==='compound'?<><rect x={a.x-150} y={a.y-27} width="300" height="54" rx="27" fill="#10291f" stroke="#6baf96"/><Text x={a.x} y={a.y+11} size={33}>{n.name}</Text></>:<Text x={a.x+24} y={a.y+11} size={30} anchor="start">{n.name}</Text>}</g>
 </g>})}
 </g>}

function Opening({f}){
 const zoom=t(f,0,92,1.6,.33),out=t(f,104,180),formation=t(f,125,265);
 return <g>{papers.map((p,i)=>{const row=Math.floor(i/16),col=i%16;
 const start={x:960+(col-7.5)*355*zoom,y:550+(row-4)*255*zoom};const end=paperCoord(i,0);
 return <Paper key={p.doi} p={p} x={lerp(start.x,end.x,formation)} y={lerp(start.y,end.y,formation)} s={lerp(zoom,.025,formation)} opacity={lerp(.26,.75,out)} rotate={(i%5-2)*(1-formation)*2}/>})}
 <Caption f={f} a={-12} b={65} size={113} y={505} sub="Decades of discovery.">Psychedelic research.</Caption>
 <g opacity={win(f,61,133)}><Text y={500} size={160}>21,735</Text><Text y={578} size={57} color={MINT}>research papers</Text><Text y={635} size={28} color={DIM}>brought together in one resource</Text></g>
 </g>
}

function SourceCards({f}){const rows=[papers[29],papers[61]];return <g opacity={win(f,450,633)}>
 {rows.map((p,i)=>{const q=t(f,461+i*24,489+i*24),a=paperCoord(papers.indexOf(p),0),sx=20+a.x*.65,sy=150+a.y*.65;return <g key={p.doi} opacity={q}>
 <Stroke d={route({x:sx,y:sy},{x:1100,y:453+i*267})} p={t(f,480+i*24,520+i*24)} color={colors[i+1]} w={3}/><circle cx={sx} cy={sy} r="9" fill={colors[i+1]}/>
 <g transform={`translate(${lerp(1810,1130,q)} ${370+i*267})`}>
 <rect width="650" height="233" rx="12" fill="#eef0e6"/>
 <text x="28" y="36" fontSize="22" fill="#536c5e">{p.compound} · {p.year}</text>
 <foreignObject x="28" y="57" width="594" height="116"><div xmlns="http://www.w3.org/1999/xhtml" style={{fontFamily:font,fontSize:29,lineHeight:1.2,color:'#14251f',display:'-webkit-box',WebkitLineClamp:3,WebkitBoxOrient:'vertical',overflow:'hidden'}}>{p.title}</div></foreignObject>
 <text x="28" y="206" fontSize="18" fill="#52685b">DOI: {p.doi}</text>
 </g></g>})}
 </g>}

function Incoming({f}){return <g>{Array.from({length:12},(_,i)=>{
 const a=653+i*15,p=t(f,a,a+69),q=t(f,a+43,a+69),idx=(i*13+22)%144;
 const target=paperCoord(idx,1),theta=i*Math.PI/6;
 const x=lerp(960+Math.cos(theta)*1300,target.x,p),y=lerp(610+Math.sin(theta)*880,target.y,p);
 const visible=t(f,a,a+9)*(1-t(f,a+115,a+135));
 return <g key={i} opacity={visible}><Paper p={papers[idx]} x={x} y={y} s={lerp(.62,.035,q)} rotate={lerp((i%3-1)*9,0,p)}/>
 <circle cx={target.x} cy={target.y} r={lerp(8,49,t(f,a+68,a+108))} stroke={MINT} strokeWidth="2" fill="none" opacity={t(f,a+63,a+70)*(1-t(f,a+70,a+108))}/>
 <Stroke d={route(target,coord(nodes[Math.floor(idx/24)],1))} p={t(f,a+65,a+105)} color={MINT} w={2} opacity={.8}/>
 </g>})}</g>}

function GraphStory({f}){
 const radial=f<630?0:f<900?t(f,630,686):f<990?1-t(f,909,968):t(f,990,1050);
 const source=t(f,451,480)*(1-t(f,604,630));
 const graphAlpha=t(f,180,251)*(1-t(f,1055,1093));
 const scale=1-source*.35;
 return <>
 {f<270&&<Opening f={f}/>}
 <g transform={`translate(${20*source},${150*source}) scale(${scale})`}><Graph f={f-170} radial={radial} opacity={graphAlpha*(1-source*.5)} labels={1-source} paperOpacity={f<270?0:1} edges={t(f,245,320)} arriving={f>=630&&f<900?f:0} spot={f>345&&f<450?Math.floor((f-345)/17)%6:-1}/></g>
 <Caption f={f} a={134} b={273} sub="Across compounds, questions and disciplines." size={77}>From molecules to lived experience.</Caption>
 <Caption f={f} a={273} b={450} size={81}>Across compounds and research areas.</Caption>
 <Caption f={f} a={450} b={630} sub="Structured knowledge, with its sources intact." size={84}>Findings linked to their papers.</Caption>
 <SourceCards f={f}/>
 <Caption f={f} a={633} b={900} sub="New papers become part of the graph." size={102}>A living map.</Caption>
 {f>=633&&f<900&&<Incoming f={f}/>}
 <Caption f={f} a={900} b={1080} sub="Many ways to see it." size={108}>One graph.</Caption>
 {f>=900&&f<1080&&<g opacity={win(f,919,1079)}><rect x="820" y="965" width="280" height="54" rx="27" stroke={MINT} fill="#10271e"/><Text y={1000} size={27}>Explore</Text></g>}
 </>
}

const timeline=data.timeline.filter(r=>r.year<=2025);
const areas=analysis.points.map(p=>({...p,count:analysis.areas.find(a=>a.name===p.name)?.count||0})).sort((a,b)=>b.count-a.count);
function Timeline({f}){
 const keys=['primary','reviews','meta'],cs=['#82a9d8','#d6a84f','#55b7ab'],max=Math.max(...timeline.map(r=>r.total));
 return <g opacity={win(f,1080,1269)}>
 <Caption f={f} a={1080} b={1269} y={166} sub="Research over time." size={91}>New: Analyze</Caption>
 <g opacity={t(f,1094,1120)}>{[0,600,1200,1800].map(v=><g key={v}><line x1="250" x2="1720" y1={854-v/max*510} y2={854-v/max*510} stroke="#334a3e"/><Text x={218} y={863-v/max*510} size={25} color={DIM} anchor="end">{v.toLocaleString()}</Text></g>)}</g>
 {timeline.map((r,i)=>{let y=854;const p=t(f,1091+i,1129+i);return <g key={r.year}>{keys.map((k,j)=>{const h=r[k]/max*510*p;y-=h;return <rect key={k} x={250+i*55} y={y} width="39" height={h} fill={cs[j]} rx="3"/>})}{[2000,2010,2020,2025].includes(r.year)&&<Text x={269+i*55} y={900} size={28} color={DIM}>{r.year}</Text>}</g>})}
 <Text x={250} y={310} anchor="start" size={28} color={DIM}>Research papers</Text>
 <Text x={1720} y={310} anchor="end" size={24} color={DIM}>2000–2025 · complete years</Text>
 {['Primary studies','Reviews','Meta-analyses'].map((s,i)=><g key={s} opacity={t(f,1143+i*9,1163+i*9)}><circle cx={567+i*340} cy="970" r="7" fill={cs[i]}/><Text x={590+i*340} y={980} size={27} anchor="start">{s}</Text></g>)}
 </g>}

function Areas({f}){const morph=t(f,1260,1303);return <g opacity={win(f,1260,1449)}>
 <Caption f={f} a={1260} b={1449} y={155} sub="See what the research covers." size={91}>Across research areas.</Caption>
 {areas.map((a,i)=>{const x=lerp(285+i*136,610,morph),y=lerp(854-a.count/5579*490,320+i*61,morph);
 const w=lerp(42,a.count/5579*900,morph),h=lerp(a.count/5579*490,34,morph);
 return <g key={a.name}><rect x={x} y={y} width={w} height={h} rx="5" fill={a.color} opacity={.9}/><Text x={575} y={y+26} size={29} anchor="end" opacity={morph}>{a.name}</Text><Text x={x+w+24} y={y+26} size={28} anchor="start" opacity={morph}>{a.count.toLocaleString()}</Text></g>})}
 <Text y={1000} size={25} color={DIM} opacity={morph}>Papers can cover more than one research area.</Text>
 </g>}

function Scatter({f}){const m=t(f,1440,1490),max=Math.max(...analysis.points.flatMap(p=>[p.primary,p.synthesis])),lx=v=>Math.log1p(v)/Math.log1p(max);
 const active=Math.floor((f-1510)/39)%3;
 return <g opacity={win(f,1440,1650)}>
 <Caption f={f} a={1440} b={1650} y={143} sub="Compare how research areas are represented." size={83}>Studies and reviews, side by side.</Caption>
 <g opacity={m}>{[0,.33,.66,1].map(r=><g key={r}><line x1={340+r*1110} x2={340+r*1110} y1="335" y2="856" stroke="#2b4136"/><line x1="340" x2="1450" y1={856-r*521} y2={856-r*521} stroke="#2b4136"/><Text x={340+r*1110} y={897} size={25} color={DIM}>{Math.round(Math.expm1(Math.log1p(max)*r)).toLocaleString()}</Text><Text x={310} y={866-r*521} size={25} color={DIM} anchor="end">{Math.round(Math.expm1(Math.log1p(max)*r)).toLocaleString()}</Text></g>)}
 <Text x={895} y={963} size={30}>Primary studies</Text><g transform="rotate(-90 169 595)"><Text x={169} y={595} size={30}>Reviews + meta-analyses</Text></g>
 <Text x={1450} y={1015} size={22} color={DIM} anchor="end">Log scales · papers grouped by research area</Text></g>
 {areas.map((p,i)=>{const a={x:610+p.count/5579*450,y:337+i*61},b={x:340+lx(p.primary)*1110,y:856-lx(p.synthesis)*521};const x=lerp(a.x,b.x,m),y=lerp(a.y,b.y,m);const focus=i===[0,3,7][Math.max(0,active)];return <g key={p.name}>
 <rect x={x-lerp(p.count/5579*450,13,m)} y={y-17} width={lerp(p.count/5579*900,26,m)} height="34" rx={lerp(5,17,m)} fill={p.color} opacity={focus?1:.62}/>
 {focus&&<g opacity={t(f,1496,1510)}><circle cx={x} cy={y} r={28} stroke={p.color} fill="none"/><line x1={x+27} y1={y} x2="1540" y2={420+active*144} stroke={p.color}/><Text x="1570" y={428+active*144} size={28} anchor="start">{p.name}</Text></g>}
 </g>})}
 </g>}

function Access({f}){const p=t(f,1650,1700),pulse=(f-1700)%85/85;return <g opacity={win(f,1650,1897)}>
 <Caption f={f} a={1650} b={1897} y={150} sub="Explore visually. Build with API + MCP." size={86}>For researchers. And AI tools.</Caption>
 <g transform={`translate(${lerp(0,-150,p)},${lerp(0,240,p)}) scale(${lerp(1,.67,p)})`}><Graph f={f} radial={1} labels={0}/></g>
 <Stroke d="M 907 657 C 1000 657,1030 657,1100 657" w={3} p={t(f,1687,1722)}/>
 <circle cx={907+pulse*193} cy="657" r="7" fill={MINT} opacity={t(f,1700,1710)}/>
 <g transform={`translate(${lerp(1630,1130,p)},345)`} opacity={p}>
 <Text x={0} y={0} size={30} color={MINT} anchor="start">STRUCTURED KNOWLEDGE</Text>
 <line x1="0" x2="640" y1="33" y2="33" stroke="#416352"/>
 {['COMPOUND','PAPER','YEAR','SOURCE'].map((s,i)=>{const q=t(f,1710+i*16,1730+i*16),values=[papers[29].compound,papers[29].title,String(papers[29].year),papers[29].doi];return <g key={s} opacity={q} transform={`translate(${(1-q)*45},${84+i*130})`}><Text x={0} y={0} size={22} color={DIM} anchor="start">{s}</Text><foreignObject x="0" y="19" width="655" height="81"><div xmlns="http://www.w3.org/1999/xhtml" style={{fontFamily:font,fontSize:i===1?26:30,lineHeight:1.23,color:FG,display:'-webkit-box',WebkitLineClamp:2,WebkitBoxOrient:'vertical',overflow:'hidden'}}>{values[i]}</div></foreignObject><line x1="0" x2="640" y1="107" y2="107" stroke="#253d30"/></g>})}
 </g>
 <Text x={495} y={951} size={32} color={MINT} opacity={p}>Explore the connections</Text>
 </g>}

function End({f}){const p=t(f,1890,1925);return <g opacity={p}>
 <image href={staticFile('story/favicon.svg')} x="889" y="157" width="142" height="142"/>
 <Text y={473} size={108}>Psychedelics</Text><Text y={590} size={108} color={MINT}>Knowledge Graph</Text>
 <Text y={674} size={38} color={DIM} opacity={t(f,1906,1935)}>A living map of psychedelic research.</Text>
 <Text y={790} size={46} opacity={t(f,1930,1955)}>psychedelicskg.com</Text>
 <Text y={858} size={28} color={DIM} opacity={t(f,1940,1965)}>Updated literature · New Analyze mode</Text>
 </g>}

export function MotionFilm(){const f=useCurrentFrame();return <AbsoluteFill style={{background:BG,overflow:'hidden'}}>
 <style>{`@font-face{font-family:FilmSpace;src:url('${staticFile('landscape/space-bold.ttf')}')}*{box-sizing:border-box}`}</style>
 <AbsoluteFill style={{background:'radial-gradient(ellipse at 50% 70%,#17423555,transparent 70%)'}}/>
 <Audio src={staticFile('story/motion-soundtrack.wav')} volume={.42}/>
 <svg width="1920" height="1080" style={{position:'absolute',inset:0,fontFamily:font,fontWeight:700}}>
 {f<1093&&<GraphStory f={f}/>}
 {f>=1080&&f<1269&&<Timeline f={f}/>}
 {f>=1260&&f<1449&&<Areas f={f}/>}
 {f>=1440&&f<1650&&<Scatter f={f}/>}
 {f>=1650&&f<1897&&<Access f={f}/>}
 {f>=1890&&<End f={f}/>}
 </svg>
 </AbsoluteFill>}
