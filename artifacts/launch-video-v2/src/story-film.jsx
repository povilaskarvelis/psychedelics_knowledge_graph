import React from 'react';
import {AbsoluteFill,Audio,Img,interpolate,Easing,staticFile,useCurrentFrame} from 'remotion';
import corpus from './story-data.json';
import {PapersToGraph} from './landscape-film';
const bg='#09110f',white='#f3f4ed',mint='#8bdbbf',muted='#a3b5ac',font='FilmSpace,Arial,sans-serif';
const cols=['#82a9d8','#d6a84f','#a88bd1','#55b7ab','#9bab62','#d1846f'];
const mix=(f,a,b,x=0,y=1)=>interpolate(f,[a,b],[x,y],{extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:Easing.bezier(.22,.8,.2,1)});
function Back(){return <AbsoluteFill style={{background:bg,backgroundImage:'radial-gradient(ellipse at 20% 85%,#17423570,transparent 65%)'}}/>}
function Title({children,f,delay=0,size=86,style={}}){return <div style={{fontFamily:font,fontSize:size,lineHeight:1.08,letterSpacing:-3,fontWeight:700,color:white,opacity:mix(f,delay,delay+23),transform:`translateY(${mix(f,delay,delay+23,32,0)}px)`,...style}}>{children}</div>}
function Note({children,style={}}){return <div style={{fontFamily:font,fontSize:32,lineHeight:1.4,color:muted,...style}}>{children}</div>}
function Logo({size=120,style={}}){return <Img src={staticFile('story/favicon.svg')} style={{width:size,height:size,...style}}/>}
function Lines({children}){return <svg width="1920" height="1080" style={{position:'absolute',inset:0,fontFamily:font}}>{children}</svg>}
function Edge({d,color=mint,p=1,w=3,opacity=1}){return <path d={d} fill="none" stroke={color} strokeWidth={w} strokeLinecap="round" pathLength="1" strokeDasharray="1" strokeDashoffset={1-p} opacity={opacity}/>}

function Wall({f,scale,opacity=1}){return <div style={{position:'absolute',left:960,top:560,opacity,transform:`scale(${scale})`,transformOrigin:'0 0'}}>
 {corpus.papers.map((p,i)=>{const row=Math.floor(i/16),col=i%16;return <div key={i} style={{position:'absolute',left:(col-7.5)*355-160,top:(row-4)*260-110,width:320,height:220,background:'#e5eae0',color:'#152a22',borderRadius:7,padding:24,transform:`rotate(${(i*7%5)-2}deg) translateY(${Math.sin(f/90+i)*4}px)`,boxShadow:'0 15px 40px #0004',fontFamily:font,overflow:'hidden'}}>
 <div style={{fontSize:18,color:'#4f7463',marginBottom:10}}>{p.compound} · {p.year}</div><div style={{fontSize:23,lineHeight:1.17,display:'-webkit-box',WebkitLineClamp:5,WebkitBoxOrient:'vertical',overflow:'hidden'}}>{p.title}</div>
 </div>})}
 </div>}

function Vast({f}){
 const zoom=mix(f,35,230,1.9,.34);
 return <AbsoluteFill><Back/><Wall f={f} scale={zoom} opacity={.68}/>
 <div style={{position:'absolute',inset:0,background:'linear-gradient(180deg,#09110feb 0%,#09110f40 55%,#09110fea 100%)'}}/>
 <div style={{position:'absolute',left:130,top:115,right:120}}>
 <Title f={f+20} size={116}>Psychedelic research.</Title>
 <div style={{opacity:1-mix(f,160,183)}}><Title f={f} delay={30} size={74} style={{color:mint,marginTop:22}}>Thousands of papers.<br/>Decades of work.</Title></div>
 </div>
 <div style={{position:'absolute',left:130,bottom:95,opacity:mix(f,170,205)}}><Title f={f} delay={170} size={98}>21,735 publications indexed.</Title><Note style={{marginTop:18}}>A vast body of research—published one paper at a time.</Note></div>
 </AbsoluteFill>;
}

function Breadth({f,connected=false}){
 const labels=corpus.broad[0].areas.map(a=>a.name);
 const progress=mix(f,30,105);
 return <AbsoluteFill><Back/>
 <div style={{position:'absolute',left:130,top:92}}><Title f={f} size={79}>{connected?'Across compounds and research areas.':'From molecules to lived experience.'}</Title><Note style={{marginTop:16}}>{connected?'The same structure brings the wider literature together.':'Psychedelic science reaches across many disciplines.'}</Note></div>
 <Lines>
 {connected&&corpus.broad.flatMap((c,i)=>c.areas.map((a,j)=>{
 const yy=330+i*114,ty=280+j*70;const active=f<155||i===Math.floor((f-155)/23)%6;
 return <Edge key={i+'-'+j} d={`M 570 ${yy} C 865 ${yy}, 975 ${ty}, 1280 ${ty}`} color={a.color} w={Math.max(1,a.width*.55)} p={mix(f,22+i*9+j*2,77+i*9+j*2)} opacity={active?.53:.055}/>;
 }))}
 {corpus.broad.map((c,i)=>{const p=mix(f,i*7,28+i*7);const y=330+i*114;return <g key={c.compound} opacity={p} transform={`translate(${(1-p)*-80},0)`}><rect x="200" y={y-39} width="370" height="78" rx="39" fill="#122a22" stroke={mint} strokeWidth="1.5"/><text x="385" y={y+12} fill={white} fontSize="38" textAnchor="middle">{c.compound}</text></g>})}
 {labels.map((label,j)=>{const y=280+j*70,p=mix(f,12+j*5,37+j*5);return <g key={label} opacity={p}><circle cx="1280" cy={y} r="10" fill={corpus.broad[0].areas[j].color}/><text x="1310" y={y+11} fontSize="33" fill={white}>{label}</text></g>})}
 {!connected&&[0,1,2,3,4,5].map(i=><g key={i} opacity={progress*.7} transform={`translate(${780+(i%2)*195},${330+Math.floor(i/2)*190}) rotate(${i%2?5:-5})`}><rect width="125" height="153" rx="5" fill="#d6dfd3"/>{[0,1,2,3,4].map(j=><line key={j} x1="17" x2={j===4?70:106} y1={26+j*21} y2={26+j*21} stroke="#698474" strokeWidth={j?3:6}/>)}</g>)}
 </Lines></AbsoluteFill>;
}

function Organize({f}){
 const collapse=mix(f,53,119);
 return <AbsoluteFill><Back/>
 <div style={{position:'absolute',inset:0,opacity:1-collapse}}><Wall f={f} scale={mix(f,0,120,.35,.16)} opacity={.2}/></div>
 <div style={{position:'absolute',left:130,top:125,right:130}}><Title f={f} size={90}>How do we bring<br/>these findings together?</Title></div>
 <div style={{position:'absolute',left:130,top:480,display:'flex',alignItems:'center',gap:55,opacity:mix(f,62,95)}}><Logo size={180}/><div><Title f={f} delay={64} size={77}>Psychedelics<br/><span style={{color:mint}}>Knowledge Graph</span></Title></div></div>
 <Note style={{position:'absolute',left:370,top:755,width:1240,fontSize:39,opacity:mix(f,98,123)}}>Organizes findings from selected papers into<br/>structured, connected knowledge.</Note>
 </AbsoluteFill>;
}

function Access({f}){return <AbsoluteFill><Back/>
 <div style={{position:'absolute',left:130,top:115}}><Title f={f} size={88}>For researchers. For AI tools.</Title><Note style={{marginTop:20}}>Two ways to work with the same knowledge.</Note></div>
 <Lines>{[0,1].map(i=><Edge key={i} d={i?'M 1025 570 C 1190 570, 1180 570, 1315 570':'M 605 570 C 755 570, 740 570, 895 570'} color={mint} p={mix(f,45+i*13,90+i*13)} w={4}/>)}</Lines>
 <Logo size={146} style={{position:'absolute',left:887,top:497,opacity:mix(f,25,48)}}/>
 {[['Browse the website','Follow compounds, topics\nand individual papers.','Explore'],['Query the graph','Access the structured knowledge\nthrough API or MCP.','API / MCP']].map(([title,body,badge],i)=><div key={title} style={{position:'absolute',left:i?1230:130,top:375,width:560,height:425,padding:45,border:'1px solid #416858',borderRadius:24,background:'#10241c',opacity:mix(f,25+i*22,50+i*22),transform:`translateY(${mix(f,25+i*22,50+i*22,45,0)}px)`}}><div style={{display:'inline-block',padding:'10px 22px',background:'#244b3b',color:mint,borderRadius:25,fontFamily:font,fontSize:26}}>{badge}</div><Title f={f} delay={30+i*22} size={43} style={{marginTop:32,letterSpacing:-1}}>{title}</Title><Note style={{fontSize:30,whiteSpace:'pre-line',marginTop:25}}>{body}</Note></div>)}
 <Note style={{position:'absolute',left:130,bottom:105,opacity:mix(f,115,145)}}>Built to support new research questions, analyses and syntheses.</Note>
 </AbsoluteFill>}

function Living({f}){return <AbsoluteFill><Back/>
 <div style={{position:'absolute',left:130,top:110}}><Title f={f} size={90}>A living knowledge graph.</Title><Note style={{marginTop:22,fontSize:36}}>Designed to grow as new research is added.</Note></div>
 <Lines>{[0,1].map(i=><g key={i}><Edge d={`M ${625+i*580} 570 L ${700+i*580} 570`} color={mint} p={mix(f,48+i*43,78+i*43)} w={4}/><circle cx={625+i*580+mix(f,48+i*43,78+i*43)*75} cy="570" r="6" fill={mint} opacity={mix(f,48+i*43,58+i*43)*(1-mix(f,77+i*43,87+i*43))}/></g>)}</Lines>
 {['New publications','Structured findings','Updated connections'].map((label,i)=><div key={label} style={{position:'absolute',left:130+i*580,top:385,width:495,height:410,border:'1px solid #416858',background:'#10251c',borderRadius:22,padding:30,opacity:mix(f,15+i*36,40+i*36),transform:`translateY(${mix(f,15+i*36,40+i*36,35,0)}px)`}}>
 <div style={{fontFamily:font,fontSize:32,color:white}}>{label}</div>
 {i===0?<div style={{position:'relative',height:260,marginTop:35}}>{[2,1,0].map(j=><div key={j} style={{position:'absolute',left:95+j*20,top:j*13,width:190,height:230,background:j?'#819f8f':'#e8eee1',borderRadius:6,transform:`rotate(${j*5}deg)`,padding:23}}>{[0,1,2,3,4,5].map(k=><div key={k} style={{height:k?4:8,width:`${k===5?60:100}%`,background:'#60796d',marginBottom:16}}/>)}</div>)}</div>:i===1?<div style={{marginTop:39}}>{['Compound','Research topic','Source paper'].map((s,j)=><div key={s} style={{fontFamily:font,color:cols[j],padding:'15px 18px',border:'1px solid #3d5649',borderRadius:10,fontSize:28,marginBottom:13,opacity:mix(f,70+j*15,90+j*15)}}>{s}</div>)}</div>:<svg width="430" height="280" style={{marginTop:20}}>{[0,1,2].map(j=><g key={j}><Edge d={`M 75 140 C 165 140,170 ${50+j*90},295 ${50+j*90}`} color={cols[j]} p={mix(f,100+j*20,135+j*20)} w={5}/><circle cx="295" cy={50+j*90} r="13" stroke={cols[j]} strokeWidth="3" fill="#18372a" opacity={mix(f,120+j*20,140+j*20)}/></g>)}<circle cx="75" cy="140" r="23" fill="#18372a" stroke={mint} strokeWidth="3"/></svg>}
 </div>)}
 <Note style={{position:'absolute',left:130,top:895,fontSize:35,opacity:mix(f,170,195)}}>Every update adds to a resource that remains connected to its sources.</Note>
 </AbsoluteFill>}

function Update({f}){return <AbsoluteFill><Back/>
 <div style={{position:'absolute',left:130,top:120}}><Note style={{color:mint,fontSize:28}}>NEW IN V2 · 01</Note><Title f={f} delay={8} size={98} style={{marginTop:22}}>Updated literature.</Title><Note style={{marginTop:26,fontSize:38}}>The research resource grows as new papers are added.</Note></div>
 <div style={{position:'absolute',left:130,top:490}}><Note style={{fontSize:29}}>Literature updated</Note><Title f={f} delay={34} size={99} style={{color:mint,marginTop:15}}>15 September 2026</Title></div>
 <div style={{position:'absolute',left:130,right:130,top:770,display:'flex',gap:150}}>{[['21,735','publications'],['99,100','structured findings']].map(([n,label],i)=><div key={n} style={{opacity:mix(f,70+i*23,95+i*23),display:'flex',alignItems:'baseline',gap:23}}><Title f={f} delay={70+i*23} size={83}>{n}</Title><Note style={{fontSize:31}}>{label}</Note></div>)}</div>
 </AbsoluteFill>}

function AnalyzeAll({f}){
 const rows=corpus.timeline.filter(x=>x.year<=2025),max=Math.max(...rows.map(x=>x.total));
 const colors=['#82a9d8','#d6a84f','#55b7ab'],keys=['primary','reviews','meta'];const base=810,left=790,step=1000/rows.length;
 const selected=f<185?-1:f<245?1:-1;
 return <AbsoluteFill><Back/>
 <div style={{position:'absolute',left:130,top:120,width:610}}><Note style={{color:mint,fontSize:28}}>NEW IN V2 · 02</Note><Title f={f} delay={8} size={94} style={{marginTop:25}}>Analyze.</Title><Title f={f} delay={23} size={72} style={{marginTop:32}}>See how<br/>the literature<br/>has developed.</Title><Note style={{fontSize:33,marginTop:35}}>Publication trends across<br/>the indexed research.</Note></div>
 <Lines><text x={left} y="200" fill={white} fontSize="37">Publications per year · all compounds</text>
 {[0,.5,1].map(n=><g key={n} opacity={mix(f,20,47)}><line x1={left} x2="1800" y1={base-n*490} y2={base-n*490} stroke="#3c5449"/><text x={left-24} y={base-n*490+10} fontSize="25" textAnchor="end" fill={muted}>{Math.round(max*n).toLocaleString()}</text></g>)}
 {rows.map((r,i)=>{let y=base;const p=mix(f,38+i*2,85+i*2);return <g key={r.year}>{keys.map((k,j)=>{const h=r[k]/max*490*p;y-=h;return <rect key={k} x={left+i*step} y={y} width={step-9} height={h} rx="2" fill={colors[j]} opacity={selected<0||selected===j?1:.2}/>})}{[2000,2010,2020,2025].includes(r.year)&&<text x={left+i*step+13} y="854" fill={muted} fontSize="28" textAnchor="middle">{r.year}</text>}</g>})}
 </Lines>
 <div style={{position:'absolute',left:790,top:904,display:'flex',gap:35,fontFamily:font,fontSize:27,color:white}}>{['Primary studies','Reviews','Meta-analyses'].map((label,i)=><div key={label} style={{display:'flex',alignItems:'center',gap:12,opacity:selected<0||selected===i?1:.3}}><span style={{width:15,height:15,borderRadius:3,background:colors[i]}}/>{label}</div>)}</div>
 <Note style={{position:'absolute',left:790,top:968,fontSize:24}}>Complete years 2000–2025 · indexed publications</Note>
 <div style={{position:'absolute',left:130,top:860,color:'#e6c07a',fontFamily:font,fontSize:34,opacity:mix(f,183,204)*(1-mix(f,241,260))}}>Highlight a publication type.</div>
 </AbsoluteFill>;
}

function Coverage({f}){
 const chosen=mix(f,90,123);
 return <AbsoluteFill><Back/>
 <div style={{position:'absolute',left:130,top:110}}><Title f={f} size={84}>Find the studies behind a question.</Title><Note style={{marginTop:20}}>Narrow the literature by compound, population and study design.</Note></div>
 <div style={{position:'absolute',left:130,top:345,display:'flex',gap:22,fontFamily:font,fontSize:30}}>{['Psilocybin','Human participants'].map((label,i)=><div key={label} style={{color:mint,padding:'15px 26px',borderRadius:32,border:'1px solid #5b9b82',background:'#17392b',opacity:mix(f,20+i*20,44+i*20)}}>{label}</div>)}</div>
 <div style={{position:'absolute',left:130,top:487,display:'flex',gap:25}}>{[['Observational studies',416],['Open-label trials',93],['Randomized controlled trials',172]].map(([label,n],i)=><div key={label} style={{width:535,height:277,padding:35,borderRadius:16,border:`2px solid ${i===2&&chosen?mint:'#43554d'}`,background:i===2?'#1d4836':'#142b21',opacity:mix(f,45+i*9,65+i*9)*(i===2?1:1-chosen*.6),transform:`translateY(${i===2?-chosen*15:0}px)`}}><Note style={{fontSize:30,color:white,height:75}}>{label}</Note><Title f={f} delay={55+i*9} size={86} style={{color:i===2?mint:white,marginTop:12}}>{n}</Title><Note style={{fontSize:24}}>matching publications</Note></div>)}</div>
 <div style={{position:'absolute',left:130,top:850,opacity:mix(f,137,160)}}><Title f={f} delay={137} size={55}>Choose a cell. Open its findings and papers.</Title><Note style={{fontSize:26,marginTop:18}}>Example from the Psilocybin coverage view · publications may appear in more than one category.</Note></div>
 </AbsoluteFill>;
}

function End({f}){return <AbsoluteFill><Back/>
 <Logo size={142} style={{position:'absolute',left:889,top:157,opacity:mix(f,0,24)}}/>
 <div style={{position:'absolute',left:130,right:130,top:361,textAlign:'center'}}><Title f={f} delay={10} size={108}>Psychedelics<br/><span style={{color:mint}}>Knowledge Graph</span></Title><Note style={{fontSize:38,marginTop:34,opacity:mix(f,37,62)}}>A living map of psychedelic research.</Note><div style={{fontFamily:font,fontSize:46,color:white,marginTop:51,opacity:mix(f,60,83)}}>psychedelicskg.com</div><Note style={{fontSize:28,marginTop:26,opacity:mix(f,76,98)}}>Updated literature · New Analyze mode</Note></div>
 </AbsoluteFill>}

const scenes=[
 [0,330,Vast],[330,540,Breadth],[540,720,Organize],
 [720,1070,({f})=><PapersToGraph f={f*.9} example/>],
 [1070,1330,({f})=><Breadth f={f} connected/>],
 [1330,1570,Living],[1570,1780,Access],[1780,2010,Update],[2010,2340,AnalyzeAll],
 [2340,2610,Coverage],[2610,2820,End],
];
export function StoryFilm(){const f=useCurrentFrame();return <AbsoluteFill style={{background:bg,overflow:'hidden'}}>
 <style>{`@font-face{font-family:FilmSpace;src:url('${staticFile('landscape/space-bold.ttf')}')}*{box-sizing:border-box}`}</style>
 <Audio src={staticFile('story/soundtrack.wav')} volume={.40}/>
 {scenes.map(([a,b,Component],i)=>f>=a&&f<b?<AbsoluteFill key={a} style={{opacity:i===0?1:mix(f,a,a+12)}}><Component f={f-a}/></AbsoluteFill>:null)}
 </AbsoluteFill>}
