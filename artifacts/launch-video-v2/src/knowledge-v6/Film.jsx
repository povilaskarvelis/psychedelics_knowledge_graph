import React from 'react';
import {useCurrentFrame,staticFile} from 'remotion';
import {Archive} from './Archive';
import {Network} from './Network';
import {Typography} from './Type';
import {C,p,lerp,palette} from './model';

// One persistent coordinate system: the same 360 fragments survive every view.
export const KnowledgeSynthesisFilmV6=()=>{
 const f=useCurrentFrame()*1.1,tools=p(f,1590,1660)*(1-p(f,1760,1800)),example=p(f,1768,1822)*(1-p(f,1922,1970)),closing=p(f,1930,1990);
 const drift=Math.sin(f*.0035)*12;
 const impact=p(f,594,617)*(1-p(f,628,684));
 const cameraScale=1+impact*.18+p(f,1255,1290)*(1-p(f,1320,1360))*.08;
 return <>
  <style>{`@font-face{font-family:KnowledgeV4;src:url('${staticFile('landscape/space-bold.ttf')}')}`}</style>
  <svg width="1920" height="1080" viewBox="0 0 1920 1080" style={{position:'absolute',inset:0,fontFamily:'KnowledgeV4,Arial,sans-serif',fontWeight:700}}>
   <defs>
    <linearGradient id="v4-bg" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#171622"/><stop offset="1" stopColor="#080e18"/></linearGradient>
    <linearGradient id="v4-header" x1="0" y1="0" x2="0" y2="1"><stop offset=".79" stopColor={C.bg}/><stop offset="1" stopColor={C.bg} stopOpacity="0"/></linearGradient>
    <clipPath id="type-safe"><rect x="70" y="38" width="1800" height="285"/></clipPath>
    <clipPath id="v4-site"><rect x="363" y="354" width="1420" height="594" rx="9"/></clipPath>
   </defs>
   <rect width="1920" height="1080" fill="url(#v4-bg)"/>
   {/* A receding perspective plane provides depth, without decorative overlays. */}
   <g stroke={C.line} strokeWidth="1" opacity={.11*(1-p(f,130,205))}>
    {Array.from({length:15},(_,i)=><path key={i} d={`M960 620 L${-2200+i*420} 1100`}/>)}
    {[0,1,2,3,4].map(i=><path key={i} d={`M0 ${650+i*i*25+f*.15} H1920`}/>)}
   </g>
   <g transform={`translate(960 680) scale(${cameraScale}) rotate(${-impact*2}) translate(-960 -680) translate(${drift} 0)`} opacity={1-.8*p(f,530,553)*(1-p(f,582,628))}>
    {f<593&&<Archive f={f}/>}
    {f>277&&<g transform={`translate(960 670) scale(${lerp(1,1.2,closing)}) translate(-960 -670)`} opacity={lerp(1,.47,closing)}><Network f={f}/></g>}
   </g>
   <g opacity={tools}>
    {['Ask questions','Trace evidence','Build analyses'].map((t,i)=><g key={t} transform={`translate(0 ${lerp(130,0,p(f,1600+i*9,1640+i*9))})`}>
     <rect x={255+i*505} y="894" width="420" height="99" rx="49" fill={C.bg} stroke={palette[i]} strokeWidth="3"/>
     <text x={465+i*505} y="958" textAnchor="middle" fill={C.paper} fontSize="42">{t}</text>
    </g>)}
   </g>
   <g opacity={example}>
    {['Medicine','Ecology','Neuroscience'].map((label,i)=><g key={label} transform={`translate(0 ${lerp(70,0,p(f,1780+i*9,1820+i*9))})`}><rect x={240+i*515} y="899" width="440" height="80" rx="40" fill={C.bg} stroke={palette[i]} strokeWidth="2"/><text x={460+i*515} y="952" textAnchor="middle" fill={C.paper} fontSize="38">{label}</text></g>)}
   </g>
   <rect width="1920" height="345" fill="url(#v4-header)" opacity={p(f,96,143)}/>
   <rect width="1920" height="1080" fill={C.bg} opacity={.42*(1-p(f,94,137))}/>
   <Typography f={f}/>
   <g opacity={p(f,1980,2010)}>
    <text x="960" y="749" textAnchor="middle" fill={C.paper} fontSize="53">Rethink how knowledge is stored,</text>
    <text x="960" y="817" textAnchor="middle" fill={C.paper} fontSize="53">synthesized, and used</text>
   </g>
  </svg>
 </>;
};
