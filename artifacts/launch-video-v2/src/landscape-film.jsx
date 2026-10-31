import React from 'react';
import {AbsoluteFill, Audio, Easing, interpolate, spring, staticFile, useCurrentFrame} from 'remotion';
import data from './landscape-data.json';

// The connection geometry, topic colors and publication counts come from the live
// site's Analyze view. Only their presentation and timing are changed for the film.
const C={bg:'#09110f',paper:'#f2f1e9',ink:'#14251f',mint:'#8bdbbf',white:'#f3f4ed',muted:'#9daea5'};
const font='FilmSpace, Arial, sans-serif';
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'};
const ease=Easing.bezier(.22,.8,.2,1);
const tween=(f,a,b,x=0,y=1)=>interpolate(f,[a,b],[x,y],{...clamp,easing:ease});
const linear=(f,a,b,x=0,y=1)=>interpolate(f,[a,b],[x,y],clamp);
const enter=(f,at=0)=>spring({frame:f-at,fps:30,config:{damping:24,stiffness:110,mass:.8}});
const windowOpacity=(f,a,b)=>Math.min(linear(f,a,a+12),linear(f,b-12,b,1,0));
const scene=(f,a,b)=>f>=a&&f<b;
const topics=['Depression','Ego dissolution','Alcohol use disorder'];
const paperColors=['#82a9d8','#55b7ab','#9bab62'];
const series=[['Conditions','#82a9d8'],['Safety','#d6a84f'],['Real-world use','#9bab62'],['Subjective effects','#55b7ab'],['Treatment context','#d1846f'],['Other','#7f8c8a']];

function Backdrop({light=false}){
 return <AbsoluteFill style={{background:light?C.paper:C.bg}}>
  {!light&&<div style={{position:'absolute',inset:0,background:'radial-gradient(ellipse at 25% 90%, #17423565, transparent 65%)'}}/>}
  <div style={{position:'absolute',inset:0,opacity:light?.08:.1,backgroundImage:`radial-gradient(${light?'#31463c':'#9bbbab'} 1px,transparent 1px)`,backgroundSize:'32px 32px',maskImage:'linear-gradient(transparent,black)'}}/>
 </AbsoluteFill>;
}
function Head({children,f,at=0,style={}}){const p=enter(f,at);return <div style={{fontFamily:font,fontWeight:700,fontSize:90,lineHeight:1.06,letterSpacing:-4,color:C.white,opacity:p,transform:`translateY(${(1-p)*45}px)`,...style}}>{children}</div>}
function Curve({d,color=C.mint,p=1,width=3,opacity=1}){return <path d={d} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" pathLength={1} strokeDasharray="1" strokeDashoffset={1-p} opacity={opacity}/>}
function Pill({x,y,text,color=C.mint,p=1,width=280,size=36}){return <div style={{position:'absolute',left:x-width/2,top:y-39,width,height:78,display:'flex',alignItems:'center',justifyContent:'center',borderRadius:50,border:`2px solid ${color}`,background:C.bg,color,fontFamily:font,fontSize:size,fontWeight:700,opacity:p,boxShadow:`0 12px 50px ${C.bg}55`}}>{text}</div>}

function Opening({f}){
 const out=tween(f,99,135,1,0);
 return <AbsoluteFill style={{opacity:out}}>
  <Backdrop/>
  <svg width="1920" height="1080" style={{position:'absolute',inset:0}}>
   {Array.from({length:22},(_,i)=>{const y=100+i*43;return <Curve key={i} d={`M 1040 ${y} C 1290 ${y}, 1250 570, 1730 570`} color={series[i%6][1]} width={1.5+(i%3)} p={tween(f,8+i,75+i)} opacity={.22}/>})}
  </svg>
  <div style={{position:'absolute',left:142,top:265}}>
   <Head f={f+18} style={{fontSize:132,letterSpacing:-7}}>Psychedelic<br/>research.</Head>
   <Head f={f} at={21} style={{fontSize:132,letterSpacing:-7,color:C.mint}}>Connected.</Head>
  </div>
  <div style={{position:'absolute',left:1300,top:220,width:420,height:570,transform:`perspective(1800px) rotateY(-14deg) rotateZ(${tween(f,0,120,9,3)}deg) translateY(${(1-enter(f,12))*90}px)`,opacity:enter(f,12)}}>
   {[2,1,0].map(i=><div key={i} style={{position:'absolute',inset:0,transform:`translate(${i*26}px,${i*23}px) rotate(${i*4}deg)`,background:i===0?C.paper:'#8aa398',borderRadius:8,boxShadow:'0 30px 80px #0006',padding:42}}>
    {i===0&&<><div style={{fontFamily:font,color:'#597065',fontSize:19,marginBottom:28}}>JAMA Psychiatry · 2020</div><div style={{fontFamily:font,fontWeight:700,fontSize:34,lineHeight:1.25,color:C.ink}}>Effects of <span style={{background:'#a5daca'}}>Psilocybin</span>-Assisted Therapy on Major Depressive Disorder</div><div style={{marginTop:35}}>{[100,90,96,83,92,65].map((w,j)=><div key={j} style={{width:`${w}%`,height:5,background:'#c0c9bf',marginBottom:13}}/>)}</div></>}
   </div>)}
  </div>
 </AbsoluteFill>
}

export function PapersToGraph({f,example=false}){
 const gather=tween(f,90,158);
 const heading1=1-tween(f,71,87);
 const heading2=windowOpacity(f,83,235);
 const line=tween(f,135,192);
 return <AbsoluteFill style={{opacity:linear(f,0,12)}}>
  <Backdrop light/>
  <div style={{position:'absolute',left:140,top:90,right:140}}>
   <div style={{opacity:heading1}}><Head f={f} style={{color:C.ink,fontSize:92}}>{example?'One example: psilocybin.':'Findings scattered across papers.'}</Head></div>
   <div style={{position:'absolute',top:0,opacity:heading2}}><Head f={f} at={83} style={{color:C.ink,fontSize:92}}>Connected by what they study.</Head></div>
   <div style={{position:'absolute',top:0,opacity:tween(f,223,242)}}><Head f={f} at={223} style={{color:C.ink,fontSize:example?83:92}}>{example?'Findings stay connected to their papers.':'Psychedelic research, connected.'}</Head></div>
  </div>
  <svg width="1920" height="1080" style={{position:'absolute',inset:0}}>
   {topics.map((_,i)=>{const y=340+i*225;return <g key={i}><Curve d={`M 562 565 C 690 565, 685 ${y}, 806 ${y}`} color={paperColors[i]} width={7} p={line}/><Curve d={`M 1166 ${y} C 1220 ${y}, 1220 ${y}, 1300 ${y}`} color={paperColors[i]} width={3} p={tween(f,168+i*7,195+i*7)}/></g>})}
  </svg>
  {data.papers.map((p,i)=>{
   const x=interpolate(gather,[0,1],[140+i*550,1295]);
   const y=interpolate(gather,[0,1],[340,253+i*225]);
   const scale=interpolate(gather,[0,1],[1,.84]);
   const height=interpolate(gather,[0,1],[505,236]);
   const ip=enter(f,7+i*6);
   return <div key={p.doi} style={{position:'absolute',left:x,top:y+(1-ip)*100,width:510,height,padding:`${36-gather*12}px ${34-gather*10}px`,background:'#fffef8',borderRadius:12,border:'1px solid #b5c4b7',boxShadow:`0 ${28-gather*18}px ${65-gather*25}px #12372217`,transform:`scale(${scale}) rotate(${(1-gather)*[1,-1.4,1.2][i]}deg)`,transformOrigin:'left top',opacity:ip,overflow:'hidden'}}>
    <div style={{fontFamily:font,fontSize:22,color:'#60796b',marginBottom:22-gather*10}}>{p.journal} · {p.year}</div>
    <div style={{fontFamily:font,fontSize:interpolate(gather,[0,1],[33,26]),lineHeight:1.24,fontWeight:700,color:C.ink}}>{p.title}</div>
    <div style={{opacity:1-gather,marginTop:32}}>{[100,94,100,82,96].map((w,j)=><div key={j} style={{width:`${w}%`,height:5,background:'#d2dbd1',marginBottom:13}}/>)}</div>
   </div>;
  })}
  {/* Identical compound labels physically converge into one node. */}
  {[0,1,2].map(i=>{
    const sx=395+i*550,sy=287;
    return <Pill key={i} text="Psilocybin" x={interpolate(gather,[0,1],[sx,420])} y={interpolate(gather,[0,1],[sy,565])} p={enter(f,33+i*5)*(i?1-tween(f,151,159):1)} color={C.mint}/>;
  })}
  {topics.map((topic,i)=><Pill key={topic} text={topic} x={interpolate(gather,[0,1],[395+i*550,985])} y={interpolate(gather,[0,1],[920,340+i*225])} width={360} size={31} color={paperColors[i]} p={enter(f,48+i*6)}/>)}
  <div style={{position:'absolute',left:305,top:667,fontFamily:font,fontSize:28,color:'#52675a',opacity:tween(f,173,191)}}>One compound</div>
  <div style={{position:'absolute',left:869,top:920,fontFamily:font,fontSize:28,color:'#52675a',opacity:tween(f,182,200)}}>Different questions</div>
  <div style={{position:'absolute',left:1360,top:920,fontFamily:font,fontSize:28,color:'#52675a',opacity:tween(f,191,209)}}>Connected papers</div>
 </AbsoluteFill>
}

function ActualGraph({f}){
 // SVG geometry is from the product; the camera, draws and attention cues are editorial.
 const selected=f<75?-1:f<103?0:f<132?1:f<160?4:-1;
 const sx=2.25,sy=1.66,ox=650,oy=120;
 const branchP=i=>tween(f,17+i*3,49+i*3);
 return <AbsoluteFill>
  <Backdrop/>
  <div style={{position:'absolute',left:130,top:190,width:610}}>
   <div style={{fontFamily:font,color:C.mint,fontSize:27,marginBottom:28,opacity:enter(f)}}>Psychedelics Knowledge Graph</div>
   <Head f={f} at={6} style={{fontSize:79}}>What does<br/>psilocybin<br/>research cover?</Head>
   <div style={{fontFamily:font,fontSize:33,lineHeight:1.4,color:C.muted,marginTop:40,opacity:enter(f,58)}}>Follow a compound<br/>across research topics.</div>
  </div>
  <svg width="1920" height="1080" style={{position:'absolute',inset:0,fontFamily:font}}>
   <g transform={`translate(${ox},${oy}) scale(${sx},${sy})`}>
    {data.connections.paths.map((p,i)=><Curve key={i} d={p.d} color={p.stroke} width={+p.width} p={branchP(i)} opacity={selected<0?.6:selected===i?1:.12}/>)}
   </g>
   {data.connections.circles.map((n,i)=>{
    const x=ox+n.cx*sx,y=oy+n.cy*sy,cp=i?branchP(i-1):enter(f,3);
    const color=i?data.connections.paths[i-1].stroke:C.mint;
    const active=selected<0||selected===i-1||i===0;
    return <g key={i} opacity={cp*(active?1:.22)}>
     {i===0&&<circle cx={x} cy={y} r={55+Math.sin(f/15)*3} fill="none" stroke={C.mint} strokeWidth="1" opacity=".17"/>}
     <circle cx={x} cy={y} r={(i?n.r*1.65:37)*cp} fill={n.fill} stroke={color} strokeWidth={2.4}/>
     <text x={i?x+35:x} y={i?y:y-67} dominantBaseline="middle" textAnchor={i?'start':'middle'} fill={i?C.white:C.mint} fontSize={i?35:38} fontWeight="700">{data.connections.texts[i].text}</text>
    </g>;
   })}
  </svg>
 </AbsoluteFill>
}

function Chart({f}){
 const rows=data.timeline.filter(d=>d.year<=2025);
 const base=820,left=785,width=985,step=width/rows.length;
 const morph=tween(f,0,43);
 const focus=tween(f,135,153);
 return <AbsoluteFill>
  <Backdrop/>
  <div style={{position:'absolute',left:130,top:183,width:650}}>
   <div style={{display:'inline-flex',alignItems:'center',gap:14,fontFamily:font,color:C.mint,fontSize:27,opacity:enter(f,6),marginBottom:30}}><span style={{background:'#18392e',border:'1px solid #5e9e87',borderRadius:26,padding:'9px 23px'}}>Analyze</span><span style={{fontSize:23,color:C.muted}}>New in v2</span></div>
   <Head f={f} at={11} style={{fontSize:85}}>How has<br/>the research<br/>changed?</Head>
   <div style={{fontFamily:font,fontSize:34,color:C.muted,lineHeight:1.4,marginTop:42,opacity:enter(f,65)}}>Psilocybin publications<br/>by year and topic.</div>
  </div>
  <svg width="1920" height="1080" style={{position:'absolute',inset:0,fontFamily:font}}>
   {f<52&&data.connections.paths.map((path,i)=>{
    const v=path.d.match(/[-+]?[0-9]*\.?[0-9]+/g).map(Number);
    const points=Array.from({length:4},(_,j)=>[650+v[j*2]*2.25,120+v[j*2+1]*1.66]);
    const yy=base-12*i;
    const target=[[left,yy],[left+width/3,yy],[left+width*2/3,yy],[left+width,yy]];
    const coords=points.map((p,j)=>p.map((n,k)=>interpolate(morph,[0,1],[n,target[j][k]])));
    return <path key={i} d={`M ${coords[0]} C ${coords[1]},${coords[2]},${coords[3]}`} fill="none" stroke={path.stroke} strokeWidth={+path.width} opacity={linear(f,25,51,.6,0)}/>;
   })}
   <text x={left} y="227" fill={C.white} fontSize="34" fontWeight="700" opacity={morph}>Publications per year</text>
   {[0,200,400].map(n=><g key={n} opacity={morph}><line x1={left} x2={1790} y1={base-n*1.14} y2={base-n*1.14} stroke="#345044" strokeWidth="1"/><text x={left-20} y={base-n*1.14+9} fill={C.muted} fontSize="25" textAnchor="end">{n}</text></g>)}
   {rows.map((row,i)=>{
    let bottom=base;
    const grow=tween(f,38+i*1.7,68+i*1.7);
    const x=left+i*step;
    return <g key={row.year}>{series.map(([label,color],j)=>{
      const count=+(row.label.match(new RegExp(label+': (\\d+)'))?.[1]||0);
      const h=count*1.14*grow;
      bottom-=h;
      return <rect key={label} x={x} y={bottom} width={step-9} height={Math.max(0,h)} rx="2" fill={color} opacity={interpolate(focus,[0,1],[.94,j===1?1:.22])}/>;
    })}
    {[2000,2010,2020,2025].includes(row.year)&&<text x={x+12} y={base+47} fill={C.muted} fontSize="27" textAnchor="middle" opacity={morph}>{row.year}</text>}
    </g>;
   })}
   <text x="1790" y="920" textAnchor="end" fill={C.muted} fontSize="23" opacity={morph}>Indexed publications · complete years 2000–2025</text>
   <g opacity={focus}><rect x="1435" y="245" width="312" height="72" rx="14" fill="#382f1b" stroke="#d6a84f"/><text x="1591" y="292" textAnchor="middle" fill="#e9c779" fontSize="31" fontWeight="700">Highlight: Safety</text><path d="M 1590 317 L 1590 377 L 1745 515" fill="none" stroke="#d6a84f" strokeWidth="2"/></g>
  </svg>
  <div style={{position:'absolute',left:785,top:955,width:1000,display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:14,opacity:morph,fontFamily:font,fontSize:23,color:C.white}}>
   {series.map(([label,color])=><div key={label} style={{display:'flex',gap:10,alignItems:'center',opacity:focus&&label!=='Safety'?.35:1}}><span style={{width:13,height:13,borderRadius:3,background:color}}/>{label}</div>)}
  </div>
 </AbsoluteFill>
}

function Close({f}){
 const gather=tween(f,0,49);
 return <AbsoluteFill>
  <Backdrop/>
  <svg width="1920" height="1080" style={{position:'absolute',inset:0}}>
   {Array.from({length:36},(_,i)=>{
    const a=i*Math.PI*2/36;
    const x=960+Math.cos(a)*830,y=540+Math.sin(a)*470;
    const xx=interpolate(gather,[0,1],[x,960+Math.cos(a)*190]);
    const yy=interpolate(gather,[0,1],[y,290+Math.sin(a)*90]);
    return <g key={i} opacity={.22*(1-tween(f,36,74))}><line x1={xx} y1={yy} x2="960" y2="290" stroke={series[i%6][1]} strokeWidth="2"/><circle cx={xx} cy={yy} r="5" fill={series[i%6][1]}/></g>;
   })}
   <g opacity={enter(f,25)}><path d="M 894 275 C 940 275, 940 235, 1000 235 M 894 275 C 940 275, 940 315, 1000 315" fill="none" stroke={C.mint} strokeWidth="5"/>{[[894,275],[1000,235],[1000,315]].map(([x,y],i)=><circle key={i} cx={x} cy={y} r={i?12:17} fill={C.bg} stroke={C.mint} strokeWidth="3"/>)}</g>
  </svg>
  <div style={{position:'absolute',left:110,right:110,top:385,textAlign:'center'}}>
   <Head f={f} at={30} style={{fontSize:105,lineHeight:1.04}}>Psychedelics<br/><span style={{color:C.mint}}>Knowledge Graph</span></Head>
   <div style={{fontFamily:font,fontSize:35,color:C.muted,marginTop:34,opacity:enter(f,46)}}>21,735 publications. 99,100 structured findings.</div>
   <div style={{fontFamily:font,fontSize:41,color:C.white,marginTop:48,opacity:enter(f,61)}}>psychedelicskg.com <span style={{color:C.mint,marginLeft:14}}>↗</span></div>
   <div style={{fontFamily:font,fontSize:26,color:C.muted,marginTop:28,opacity:enter(f,70)}}>Updated literature · New Analyze mode</div>
  </div>
 </AbsoluteFill>
}

export function LandscapeFilm(){
 const f=useCurrentFrame();
 return <AbsoluteFill style={{background:C.bg,overflow:'hidden'}}>
  <style>{`@font-face{font-family:FilmSpace;src:url('${staticFile('landscape/space-bold.ttf')}')}*{box-sizing:border-box}`}</style>
  <Audio src={staticFile('landscape/soundtrack.wav')} volume={.45}/>
  {scene(f,0,135)&&<Opening f={f}/>}
  {scene(f,120,430)&&<div style={{position:'absolute',inset:0,opacity:linear(f,411,430,1,0)}}><PapersToGraph f={f-120}/></div>}
  {scene(f,416,633)&&<div style={{position:'absolute',inset:0,opacity:Math.min(linear(f,416,433),linear(f,615,633,1,0))}}><ActualGraph f={f-416}/></div>}
  {scene(f,620,862)&&<div style={{position:'absolute',inset:0,opacity:Math.min(linear(f,620,637),linear(f,845,862,1,0))}}><Chart f={f-620}/></div>}
  {scene(f,850,1050)&&<div style={{position:'absolute',inset:0,opacity:linear(f,850,865)}}><Close f={f-850}/></div>}
 </AbsoluteFill>
}
