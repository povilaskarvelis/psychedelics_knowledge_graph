import React from 'react';
import {staticFile} from 'remotion';

export const C={
  bg:'#071012', deep:'#061013', panel:'#102621', cream:'#f1eee5', muted:'#a9bdb7',
  mint:'#64c6aa', teal:'#67aa9c', blue:'#83b0db', violet:'#aa91d1', gold:'#e3b65f',
  line:'#385f57', ink:'#263830', paper:'#eeece2', coral:'#d89285',
};
export const clamp=(x)=>Math.min(1,Math.max(0,x));
export const ease=(x)=>{const t=clamp(x);return t*t*(3-2*t);};
export const p=(f,a,b)=>ease((f-a)/(b-a));
export const mix=(a,b,t)=>a+(b-a)*t;

export const Stage=({children})=><>
  <style>{`@font-face{font-family:FilmSpace;src:url('${staticFile('landscape/space-bold.ttf')}')}`}</style>
  <svg width="1920" height="1080" viewBox="0 0 1920 1080" style={{position:'absolute',inset:0,fontFamily:'FilmSpace,Arial,sans-serif',fontWeight:700}}>
    <defs>
      <linearGradient id="v2-bg" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#071316"/><stop offset=".52" stopColor="#071012"/><stop offset="1" stopColor="#0e1716"/></linearGradient>
      <linearGradient id="v2-gold" x1="0" x2="1"><stop stopColor="#e7c47f"/><stop offset="1" stopColor="#b99246"/></linearGradient>
      <linearGradient id="v2-beam" x1="0" x2="1"><stop stopColor="#64c6aa" stopOpacity="0"/><stop offset=".5" stopColor="#e3b65f" stopOpacity=".9"/><stop offset="1" stopColor="#aa91d1" stopOpacity="0"/></linearGradient>
      <filter id="v2-soft-glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="13"/></filter>
      <filter id="v2-card-shadow" x="-30%" y="-30%" width="180%" height="180%"><feDropShadow dx="0" dy="11" stdDeviation="13" floodColor="#020605" floodOpacity=".7"/></filter>
    </defs>
    <rect width="1920" height="1080" fill="url(#v2-bg)"/>
    {children}
  </svg>
</>;

export const BackGrid=({opacity=.19,offset=0})=><g opacity={opacity} stroke={C.line} strokeWidth="1">
  {Array.from({length:24},(_,i)=><path key={`v${i}`} d={`M ${i*90-60+offset} 0 V 1080`}/>)}
  {Array.from({length:15},(_,i)=><path key={`h${i}`} d={`M 0 ${i*81-45} H 1920`}/>)}
</g>;

export const Headline=({lines,x=108,y=156,size=107,opacity=1,colors,align='start',leading=1.11})=><g opacity={opacity} textAnchor={align} fontSize={size} letterSpacing={-3.5}>
  {lines.map((line,i)=><text key={i} x={x} y={y+i*size*leading} fill={colors?.[i]||C.cream}>{line}</text>)}
</g>;

export const Paper=({x,y,w=152,h=201,rotation=0,scale=1,opacity=1,accent=C.mint,marked=false})=><g opacity={opacity} transform={`translate(${x} ${y}) rotate(${rotation}) scale(${scale})`} filter="url(#v2-card-shadow)">
  <path d={`M ${-w/2} ${-h/2} H ${w/2-25} L ${w/2} ${-h/2+25} V ${h/2} H ${-w/2} Z`} fill={C.paper}/>
  <path d={`M ${w/2-25} ${-h/2} V ${-h/2+25} H ${w/2}`} fill="#c5c9bc"/>
  <rect x={-w/2+16} y={-h/2+20} width={w*.47} height="6" rx="3" fill={accent}/>
  {[0,1,2,3,4,5].map((i)=><rect key={i} x={-w/2+16} y={-h/2+48+i*22} width={(w-32)*(i===1?.69:i===4?.54:.88)} height="5" rx="2.5" fill={C.ink} opacity={marked&&i===3?.72:.22}/>)}
  {marked&&<rect x={-w/2+12} y={-h/2+105} width={w-24} height="24" rx="3" fill={accent} opacity=".26"/>}
</g>;

export const Stroke=({d,color=C.teal,width=3,opacity=1,dash})=><path d={d} fill="none" stroke={color} strokeWidth={width} opacity={opacity} strokeDasharray={dash} strokeLinecap="round" strokeLinejoin="round"/>;

const centers=[
  {x:348,y:577,label:'Study',color:C.cream},
  {x:671,y:377,label:'Method',color:C.blue},
  {x:754,y:768,label:'Population',color:C.mint},
  {x:1071,y:547,label:'Finding',color:C.gold},
  {x:1390,y:360,label:'Topic',color:C.violet},
  {x:1480,y:746,label:'Outcome',color:C.teal},
];
export const webCenters=centers;
const arcs=[[0,1],[0,2],[0,3],[1,3],[1,4],[2,3],[2,5],[3,4],[3,5],[4,5]];
const colorCycle=[C.mint,C.blue,C.violet,C.gold,C.teal];
const satellite=(i,j)=>{
  const d=centers[i],angle=j*2.399963+i*.63,r=92+((j*73+i*41)%162);
  return {x:d.x+Math.cos(angle)*r,y:d.y+Math.sin(angle)*r*.72};
};

export const KnowledgeWeb=({frame=200,progress=1,opacity=1,transform='',labels=true,lit=-1})=><g opacity={opacity} transform={transform}>
  {centers.map((d,i)=>Array.from({length:18},(_,j)=>{
    if(j%3!==0||i===5)return null;
    const u=satellite(i,j),v=satellite(i+1,(j*5+3)%18),e=p(frame,69+i*13+j*2.3,121+i*13+j*2.3)*progress;
    return <path key={`cross-${i}-${j}`} d={`M ${u.x} ${u.y} Q ${(u.x+v.x)/2} ${(u.y+v.y)/2-27} ${v.x} ${v.y}`}
      fill="none" stroke={colorCycle[(i+j)%5]} strokeWidth="1.7" opacity={e*.23} pathLength="1" strokeDasharray="1" strokeDashoffset={1-e}/>;
  }))}
  {arcs.map(([a,b],i)=>{
    const u=centers[a],v=centers[b],e=p(frame,18+i*8,70+i*8)*progress;
    const d=`M ${u.x} ${u.y} Q ${(u.x+v.x)/2} ${(u.y+v.y)/2+(i%2?58:-58)} ${v.x} ${v.y}`;
    return <g key={i}>
      <path d={d} fill="none" stroke={i%3===0?C.gold:C.mint} strokeWidth={lit===a||lit===b?7:3} opacity={e*(lit===-1?.58:lit===a||lit===b?.92:.12)} pathLength="1" strokeDasharray="1" strokeDashoffset={1-e} strokeLinecap="round"/>
      {(lit===a||lit===b)&&<path d={d} fill="none" stroke={C.gold} strokeWidth="17" opacity={e*.13} filter="url(#v2-soft-glow)"/>}
    </g>;
  })}
  {centers.map((d,i)=>{
    const e=p(frame,12+i*17,59+i*17)*progress;
    return <g key={i} opacity={e*(lit===-1||lit===i?1:.42)}>
      {Array.from({length:18},(_,j)=>{
        const {x,y}=satellite(i,j),next=satellite(i,(j+5)%18);
        const a2=p(frame,57+i*9+j*1.7,102+i*9+j*1.7);
        return <g key={j} opacity={a2}>
          <Stroke d={`M ${d.x} ${d.y} Q ${(d.x+x)/2+22} ${(d.y+y)/2-16} ${x} ${y}`} color={d.color} width={2.1} opacity={.44}/>
          {j%2===0&&<Stroke d={`M ${x} ${y} Q ${(x+next.x)/2} ${(y+next.y)/2-19} ${next.x} ${next.y}`} color={d.color} width={1.5} opacity={.19}/>}
          <circle cx={x} cy={y} r={j%4===0?9:5.6} fill={colorCycle[(i+j)%5]} opacity={.92}/>
        </g>;
      })}
      <circle cx={d.x} cy={d.y} r="45" fill={d.color} opacity=".11" filter="url(#v2-soft-glow)"/>
      <circle cx={d.x} cy={d.y} r="27" fill={C.bg} stroke={d.color} strokeWidth="5"/>
      <circle cx={d.x} cy={d.y} r="11" fill={d.color}/>
      {labels&&<g><rect x={d.x-108} y={d.y+43} width="216" height="66" rx="15" fill={C.panel} stroke={d.color} strokeWidth="2"/><text x={d.x} y={d.y+88} textAnchor="middle" fill={C.cream} fontSize={d.label.length>8?29:35}>{d.label}</text></g>}
    </g>;
  })}
</g>;

export const TopScrim=({height=266,opacity=.95})=><rect x="0" y="0" width="1920" height={height} fill={C.bg} opacity={opacity}/>;
