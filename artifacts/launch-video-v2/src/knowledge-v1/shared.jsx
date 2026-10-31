import React from 'react';
import {staticFile} from 'remotion';

export const C = {
  bg: '#090e0d',
  white: '#e6ece8',
  muted: '#a8b9b2',
  line: '#36534b',
  mint: '#61c7ac',
  teal: '#69a196',
  blue: '#82a9d8',
  violet: '#a88bd1',
  gold: '#d6a84f',
  paper: '#e8e7da',
  ink: '#1c302a',
};

export const clamp = (v) => Math.max(0, Math.min(1, v));
export const smooth = (v) => {const t=clamp(v); return t*t*(3-2*t);};
export const p = (f,a,b) => smooth((f-a)/(b-a));
export const mix = (a,b,t) => a+(b-a)*t;

export const Canvas = ({children}) => <>
  <style>{`@font-face{font-family:FilmSpace;src:url('${staticFile('landscape/space-bold.ttf')}')}`}</style>
  <svg width="1920" height="1080" viewBox="0 0 1920 1080" style={{position:'absolute',inset:0,fontFamily:'FilmSpace, Arial, sans-serif',fontWeight:700}}>
    <rect width="1920" height="1080" fill={C.bg}/>
    {children}
  </svg>
</>;

export const Headline = ({lines,x=110,y=120,size=94,opacity=1,align='start',color=C.white,lineHeight=1.07}) => <g opacity={opacity} fill={color} textAnchor={align} fontSize={size} letterSpacing={-3.2}>
  {lines.map((line,i)=><text key={i} x={x} y={y+i*size*lineHeight}>{line}</text>)}
</g>;

export const Paper = ({x,y,w=160,h=210,rotation=0,opacity=1,scale=1,accent=C.teal,marked=false}) => <g opacity={opacity} transform={`translate(${x} ${y}) rotate(${rotation}) scale(${scale})`}>
  <rect x={-w/2} y={-h/2} width={w} height={h} rx="6" fill={C.paper}/>
  <rect x={-w/2+19} y={-h/2+21} width={w*.44} height="7" rx="3" fill={accent} opacity=".8"/>
  {[0,.14,.30,.47,.63,.79].map((q,i)=><rect key={i} x={-w/2+19} y={-h/2+51+i*23} width={(w-38)*(i===2?.68:i===5?.52:.9)} height="5" rx="2.5" fill={C.ink} opacity={marked&&i===3?.85:.24}/>)}
  {marked&&<rect x={-w/2+15} y={-h/2+112} width={w-30} height="20" rx="3" fill={accent} opacity=".25"/>}
</g>;

export const Node = ({x,y,r=25,color=C.mint,opacity=1,outline=false}) => <g opacity={opacity}>
  <circle cx={x} cy={y} r={r} fill={outline?C.bg:color} stroke={color} strokeWidth={outline?3:0}/>
  {!outline&&<circle cx={x} cy={y} r={Math.max(4,r*.27)} fill={C.white} opacity=".56"/>}
</g>;

export const Stroke = ({d,color=C.teal,width=3,opacity=1,dash}) => <path d={d} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={dash} opacity={opacity}/>;
