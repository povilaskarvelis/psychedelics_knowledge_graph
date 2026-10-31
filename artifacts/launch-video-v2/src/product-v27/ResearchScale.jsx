import React from 'react';
import {Label,p,mix} from '../product/shared';

const icons=[
 {label:['Molecular','mechanisms'],x:330,color:'#72a77c',kind:'molecule'},
 {label:['Brain &','experience'],x:750,color:'#5f9eb5',kind:'brain'},
 {label:['Clinical','outcomes'],x:1170,color:'#d1846f',kind:'clinical'},
 {label:['Public','health'],x:1590,color:'#9bab62',kind:'public'},
];

const common=color=>({fill:'none',stroke:color,strokeWidth:6,strokeLinecap:'round',strokeLinejoin:'round'});

const ResearchIcon=({kind,color})=>{
 if(kind==='molecule')return <g {...common(color)}>
  <path d="M -58 -42 L 0 -10 L 62 -42 M 0 -10 L -42 62 M 0 -10 L 58 58"/>
  <circle cx="-58" cy="-42" r="19"/><circle cx="0" cy="-10" r="25"/><circle cx="62" cy="-42" r="17"/>
  <circle cx="-42" cy="62" r="16"/><circle cx="58" cy="58" r="21"/>
 </g>;
 if(kind==='brain')return <g {...common(color)}>
  <path d="M 0 70 C -54 75 -88 48 -76 12 C -102 -21 -77 -67 -39 -66 C -27 -94 -2 -91 0 -66 C 7 -94 35 -93 43 -66 C 83 -68 103 -24 78 8 C 93 45 55 74 0 70 Z"/>
  <path d="M 0 -66 V 70 M -56 -40 C -27 -36 -24 -11 -39 7 M 57 -40 C 27 -36 24 -11 40 7 M -62 31 C -34 22 -19 39 -17 57 M 64 31 C 35 22 20 39 18 57"/>
 </g>;
 if(kind==='clinical')return <g {...common(color)}>
  <rect x="-75" y="-75" width="150" height="150" rx="38"/>
  <path d="M -47 4 H -22 L -8 -30 L 13 39 L 29 3 H 52"/>
  <path d="M 0 -58 V -38 M -10 -48 H 10"/>
 </g>;
 return <g {...common(color)}>
  <circle cx="0" cy="-35" r="22"/><circle cx="-58" cy="-16" r="17"/><circle cx="58" cy="-16" r="17"/>
  <path d="M -43 55 C -40 15 40 15 43 55 M -91 61 C -88 28 -35 25 -24 48 M 91 61 C 88 28 35 25 24 48"/>
  <path d="M -112 80 C -70 103 70 103 112 80"/>
 </g>;
};

export const ResearchScale=({frame})=><g opacity={1-p(frame,294,316)}>
 {icons.map((icon,index)=>{
  const reveal=p(frame,172+index*14,196+index*14);
  const radius=82+index*9;
  return <g key={icon.kind} opacity={reveal}>
   <g transform={`translate(${icon.x} 548) scale(${mix(.84,1,reveal)})`}>
    <circle r={radius} fill={icon.color} fillOpacity=".06" stroke={icon.color} strokeWidth="2.5" opacity=".55"/>
    <ResearchIcon kind={icon.kind} color={icon.color}/>
   </g>
   <Label x={icon.x} y={765} size={50} anchor="middle" opacity={reveal}>{icon.label[0]}</Label>
   <Label x={icon.x} y={824} size={50} anchor="middle" opacity={reveal}>{icon.label[1]}</Label>
  </g>;
 })}
</g>;
