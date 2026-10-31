import React from 'react';
import {AbsoluteFill, Easing, Interactive, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {loadFont} from '@remotion/fonts';
import broad from '../v6-data.json';
import source from '../v7-data.json';

loadFont({family:'Space',url:staticFile('landscape/space-bold.ttf'),weight:'700'});
export const BG='#090e0d';
export const INK='#e6ece8';
export const GREEN='#61c7ac';
export const ease={extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:Easing.bezier(.22,1,.36,1)};
export const p=(f,a,b)=>interpolate(f,[a,b],[0,1],ease);
export const mix=(a,b,t)=>a+(b-a)*t;
export const areas=broad.cells.slice(0,10).map(c=>({name:c.area,color:c.color}));
export const compounds=['Ketamine','Psilocybin','MDMA'];
export {broad,source};
export const Stage=({children})=><AbsoluteFill style={{backgroundColor:BG,color:INK,fontFamily:'Space',fontWeight:700,overflow:'hidden'}}>{children}</AbsoluteFill>;
export const Title=({children,top=96,size=104,center=false,opacity=1})=><Interactive.Div name="Scene headline" style={{position:'absolute',left:140,right:140,top,fontSize:size,lineHeight:1.06,letterSpacing:-4,textAlign:center?'center':'left',opacity}}>{children}</Interactive.Div>;
export const Svg=({children,...rest})=><svg viewBox="0 0 1920 1080" width="1920" height="1080" style={{position:'absolute',inset:0,overflow:'visible'}} {...rest}>{children}</svg>;
export const Label=({x,y,children,size=48,anchor='start',color=INK,opacity=1})=><text x={x} y={y} fill={color} fontFamily="Space" fontWeight="700" fontSize={size} letterSpacing="-1.2" textAnchor={anchor} dominantBaseline="middle" opacity={opacity}>{children}</text>;
export const Node=({x,y,r=17,color=GREEN,opacity=1})=><g opacity={opacity}><circle cx={x} cy={y} r={r} fill={BG}/><circle cx={x} cy={y} r={r} fill={color} fillOpacity=".18" stroke={color} strokeWidth="3"/></g>;
export const curve=(x1,y1,x2,y2)=>`M ${x1} ${y1} C ${mix(x1,x2,.43)} ${y1}, ${mix(x1,x2,.57)} ${y2}, ${x2} ${y2}`;
export const Link=({x1,y1,x2,y2,color=GREEN,width=5,progress=1,opacity=.3,id='edge'})=><g opacity={opacity}><defs><linearGradient id={id} gradientUnits="userSpaceOnUse" x1={x1} y1={y1} x2={x2} y2={y2}><stop stopColor={GREEN}/><stop offset="100%" stopColor={color}/></linearGradient></defs><path d={curve(x1,y1,x2,y2)} fill="none" stroke={`url(#${id})`} strokeWidth={width} strokeLinecap="round" pathLength="1" strokeDasharray="1" strokeDashoffset={1-progress}/></g>;
export const Paper=({x,y,w=64,color='#97aaa4',opacity=1,rotate=0})=><g opacity={opacity} transform={`translate(${x} ${y}) rotate(${rotate})`}><path d={`M ${-w*.42} ${-w*.57} H ${w*.19} L ${w*.42} ${-w*.32} V ${w*.57} H ${-w*.42} Z`} fill={BG} stroke={color} strokeWidth={Math.max(1.2,w*.025)}/><path d={`M ${w*.19} ${-w*.57} V ${-w*.32} H ${w*.42}`} fill="none" stroke={color} strokeWidth={Math.max(1,w*.02)}/>{[0,1,2].map(i=><path key={i} d={`M ${-w*.25} ${w*(-.12+i*.16)} H ${w*(i===2?.09:.24)}`} stroke={color} strokeWidth={w*.035} opacity=".5"/>)}</g>;
export const Tabs=({active='Explore',frame=100})=><div style={{position:'absolute',left:142,top:54,display:'flex',gap:8,opacity:p(frame,0,20)}}>{['Explore','Analyze'].map(t=><div key={t} style={{fontSize:39,padding:'13px 30px',borderRadius:15,color:t===active?INK:'#73847e',background:t===active?'#233733':'transparent',border:t===active?'1px solid #3c5750':'1px solid transparent'}}>{t}</div>)}</div>;
export function AreaGraph({frame=100,start=0,nodeStart=start-8,labelAbove=false,x1=620,x2=1220,y1=410,gap1=210,y2=300,gap2=66,names=compounds,opacity=1}){
 return <g opacity={opacity}>{names.flatMap((name,i)=>areas.map((a,j)=>{
 const count=broad.cells.find(c=>c.compound===name.toLowerCase()&&c.area===a.name)?.count||0;
 return count>0?<Link key={`${i}-${j}`} id={`area-${i}-${j}`} x1={x1} y1={y1+i*gap1} x2={x2} y2={y2+j*gap2} width={2+Math.sqrt(count)*.24} color={a.color} opacity={.35} progress={p(frame,start+i*5+j*1.2,start+42+i*5+j*1.2)}/>:null;
 }))}{names.map((name,i)=><g key={name} opacity={p(frame,nodeStart,nodeStart+20)}><Node x={x1} y={y1+i*gap1} r={24}/><Label x={labelAbove?x1:x1-42} y={y1+i*gap1-(labelAbove?58:0)} anchor={labelAbove?'middle':'end'} size={56}>{name}</Label></g>)}{areas.map((a,j)=><g key={a.name} opacity={p(frame,start+j*2,start+20+j*2)}><Node x={x2} y={y2+j*gap2} color={a.color} r={15}/><Label x={x2+34} y={y2+j*gap2} size={44}>{a.name}</Label></g>)}</g>;
}
