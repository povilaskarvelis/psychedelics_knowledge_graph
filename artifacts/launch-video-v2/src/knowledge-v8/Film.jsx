import React from 'react';
import {staticFile, useCurrentFrame} from 'remotion';
import {C, colors, nodes, edges, p, mix, band, rnd} from '../knowledge-v7/model';
import {Opening, ResearchPaper, OPENING_PAPER_POSITIONS} from './Opening';

const captions = [
  [0, 162, ['Research output is outgrowing', 'our capacity to make sense of it'], 99],
  [162, 342, ['Yet the paper remains', 'the main unit of scientific output'], 103],
  [342, 522, ['Connections among findings', 'are buried in the text'], 103],
  [522, 762, ['Each synthesis reconstructs', 'these links for a specific question'], 96],
  [762, 972, ['What if this work', 'could accumulate?'], 111],
  [972, 1122, ['AI can extract findings', 'and map their relationships'], 98],
  [1122, 1392, ['The graph preserves findings', 'and the links among them'], 101],
  [1392, 1632, ['Interactive views reveal patterns,', 'differences, and gaps'], 98],
  [1632, 1872, ['Different questions produce', 'different views of the same graph'], 98],
  [1872, 2112, ['New syntheses draw on', 'knowledge already organized'], 101],
  [2112, 2412, ['As new papers are published,', 'the graph and its analyses grow'], 98],
  [2412, 2652, ['Software and AI can query', 'the same graph directly'], 102],
  [2652, 2880, ['From isolated papers', 'to a living', 'scientific record'], 111],
];

const Caption = ({f}) => <g>{captions.map(([a,b,lines,size]) => {
  const opacity=band(f,a,a+18,b-17,b);
  if (!opacity) return null;
  const final=a===2652;
  const cx=a===0 || final ? 960 : 100;
  const y0=a===0 ? 390 : final ? 260 : 153;
  return <g key={a} opacity={opacity}>
    {lines.map((line,j) => <text key={j} x={cx} y={final ? y0+j*145+mix(30,0,p(f,a+j*16,a+27+j*16)) : y0+j*size*1.16+mix(22,0,p(f,a+j*3,a+19+j*3))}
      textAnchor={a===0 || final ? 'middle' : 'start'} fontSize={final ? j===0?96:142:size}
      letterSpacing={-3.1} fill={j===lines.length-1 ? C.gold : C.paper}
      stroke={final?C.bg:'none'} strokeWidth={final?10:0} paintOrder="stroke">{line}</text>)}
  </g>;
})}</g>;

// The same paper forms the source layer for two independent literature syntheses.
const Reconstruction = ({f}) => {
  const arrive=p(f,515,592), disappear=1-p(f,817,943), text=band(f,552,582,800,850);
  const paperCenters=OPENING_PAPER_POSITIONS;
  return <g opacity={disappear}>
    {paperCenters.map((paper,i)=><ResearchPaper key={i} x={mix(paper.x,190+i*190,arrive)} y={mix(paper.y,500,arrive)} scale={mix(paper.scale,.32,arrive)}
      opacity={1} variant={paper.variant} accent={paper.accent} highlight={1-arrive} />)}
    {Array.from({length:14},(_,i)=>{
      const phase=p(f,542+i%11*3,604+i%11*3);
      const x=760+(i%7)*130, y=470+Math.floor(i/7)*94;
      return <ResearchPaper key={i+3} x={x} y={y} scale={.18} accent={colors[i%4]} opacity={phase*.9} compact/>;
    })}
    <g opacity={text}>
      <path d="M140 630 H1800" stroke={C.paper} strokeWidth="2" opacity=".33"/>
      {[0,1].map(k=>{
        const x=430+k*650, begin=585+k*65, alpha=p(f,begin,begin+22);
        return <g key={k} opacity={alpha}>
          <rect x={x-242} y="683" width="482" height="305" rx="10" fill="#151a25" stroke={colors[k]} strokeWidth="2.5" />
          <text x={x-202} y="749" fill={C.paper} fontSize="45">{k===0?'Review':'Meta-analysis'}</text>
          {Array.from({length:42},(_,i)=>{
            const q=p(f,begin+12+i%7*3,begin+72+i%7*3);
            const tx=x-185+(i%14)*27,ty=811+Math.floor(i/14)*53;
            const sx=i%4===0?190+(i%3)*190:760+(i%7)*130;
            const sy=i%4===0?500:470+Math.floor((i%14)/7)*94;
            return <g key={i}>
              {i%3===0 && <path d={`M${sx} ${sy} Q${(sx+tx)/2} ${sy+68} ${tx} ${ty}`} fill="none" stroke={colors[i%4]} strokeWidth="2" opacity={Math.sin(q*Math.PI)*.3}/>}
              <circle cx={mix(sx,tx,q)} cy={mix(sy,ty,q)} r="6" fill={colors[i%4]} opacity={q}/>
            </g>;
          })}
        </g>;
      })}
    </g>
  </g>;
};

const bridgeGroups=[[0,1],[1,2],[0,3],[1,4],[2,5],[3,4],[4,5],[0,4],[1,5]];
const bridges=bridgeGroups.flatMap(([ga,gb]) => {
  const possible=[];
  for(let a=ga;a<324;a+=6) for(let b=gb;b<324;b+=6) {
    const d=Math.hypot(nodes[a].x-nodes[b].x,nodes[a].y-nodes[b].y);
    possible.push({a,b,d});
  }
  return possible.sort((a,b)=>a.d-b.d).slice(0,3);
});
const graphEdges=[...edges,...bridges];

const graphPose=(n,f)=>{
  const i=n.i;
  const source=i<84
    ? {x:245+(i%14)*27+Math.floor(i/42)*650,y:811+Math.floor((i%42)/14)*53}
    : {x:760+(i%7)*130,y:470+Math.floor((i%14)/7)*94};
  const t=p(f,796+i%17*2,1006+i%17*2);
  let x=mix(source.x,n.x,t),y=mix(source.y,n.y,t)-Math.sin(Math.PI*t)*(52+i%6*9);
  const left=p(f,1318,1425)*(1-p(f,2590,2695));
  x=mix(x,488+(n.x-960)*.70,left);
  y=mix(y,694+(n.y-650)*.70,left);
  const finale=p(f,2610,2730);
  x=mix(x,960+(n.x-960)*.92,finale);
  y=mix(y,790+(n.y-650)*.60,finale);
  return {x,y,t,left};
};

const fresh=(i,f)=>i<324?1:p(f,2150+Math.floor((i-324)/12)*62,2220+Math.floor((i-324)/12)*62);

const Graph=({f})=>{
  const ready=p(f,793,850), end=p(f,2600,2710), positions=nodes.map(n=>graphPose(n,f));
  const selected=band(f,1430,1470,1810,1870), pulse=p(f,839,1060);
  const left=p(f,1318,1425)*(1-p(f,2590,2695));
  const query=band(f,2430,2490,2610,2660);
  return <g opacity={ready}>
    <defs>
      <clipPath id="v8-graph-window"><rect x={mix(0,60,left)} y={mix(300,434,left)}
        width={mix(1920,875,left)} height={mix(780,535,left)}/></clipPath>
      <linearGradient id="v8-graph-edge-gradient"><stop stopColor="white" stopOpacity={1-left}/>
        <stop offset=".09" stopColor="white"/><stop offset=".91" stopColor="white"/>
        <stop offset="1" stopColor="white" stopOpacity={1-left}/></linearGradient>
      <mask id="v8-graph-edge-fade"><rect x={mix(0,60,left)} y={mix(300,434,left)}
        width={mix(1920,875,left)} height={mix(780,535,left)} fill="url(#v8-graph-edge-gradient)"/></mask>
    </defs>
    <g clipPath="url(#v8-graph-window)" mask="url(#v8-graph-edge-fade)">
    {graphEdges.map((e,i)=>{
      const a=positions[e.a],b=positions[e.b], q=p(f,868+i%37,1002+i%37), isBridge=i>=edges.length;
      return <g key={i} opacity={q*fresh(e.a,f)*fresh(e.b,f)}>
        <path d={`M${a.x} ${a.y} Q${(a.x+b.x)/2} ${(a.y+b.y)/2-12} ${b.x} ${b.y}`}
          fill="none" stroke={nodes[e.a].c} strokeWidth={(isBridge?2.7:1.9)*(1+end*.25)}
          opacity={mix(isBridge?.5:.37,isBridge?.72:.62,end)}/>
      </g>;
    })}
    {nodes.map((n,i)=>{
      const a=positions[i], isSel=(n.group===2 || n.group===4), dim=mix(1,isSel?1:.25,selected);
      const r=(i<324?6.1:6.5)*(1+end*.52);
      return <circle key={i} cx={a.x} cy={a.y} r={r+query*(i%7===0?2.6:0)} fill={n.c}
        opacity={fresh(i,f)*dim*mix(1,i%7===0?1:.42,query)} />;
    })}
    {bridges.map((e,j)=>{
      const a=positions[e.a],b=positions[e.b], beat=(f-1115-j*19)%108;
      const show=band(f,1110,1160,1340,1400)+band(f,2430,2480,2620,2660);
      const t=Math.max(0,Math.min(1,beat/65));
      return <circle key={`flow-${j}`} cx={mix(a.x,b.x,t)} cy={mix(a.y,b.y,t)} r="6" fill={colors[j%4]}
        opacity={show*(beat>=0&&beat<65?Math.sin(Math.PI*t)*.86:0)}/>;
    })}
    {[2,17,44,72].map((i,j)=>{
      const a=positions[i], show=band(f,1032+j*7,1086+j*7,1318,1390);
      return <circle key={i} cx={a.x} cy={a.y} r={mix(12,37,pulse)} fill="none" stroke={nodes[i].c} strokeWidth="3" opacity={show*.65}/>;
    })}
    </g>
    <g opacity={band(f,1400,1450,2590,2680)}>
      <text x="485" y="414" textAnchor="middle" fill={C.paper} fontSize="45">Knowledge graph</text>
    </g>
  </g>;
};

const chartData=Array.from({length:180},(_,i)=>({i,n: nodes[(i*7)%324],col:i%18,row:Math.floor((i%90)/18),lower:i>=90}));
const chartPose=(datum,f)=>{
  const {col,row,lower,i}=datum;
  const next=p(f,1645,1770), growth=p(f,2150,2360), access=p(f,2410,2520);
  const base={x:1050+col*41,y:lower?792+row*31:653-row*(20+(col%4)*4)};
  const question={x:1050+col*41,y:lower?792+row*31:647-row*(12+col*1.55)};
  let x=mix(base.x,question.x,next),y=mix(base.y,question.y,next);
  if(!lower) y-=growth*(row/4)*(16+col*1.8);
  const missing=lower&&col>11&&row>1;
  const appear=missing?mix(.07,1,growth):1;
  if(lower){x=mix(x,1058+(i%3)*249,access);y=mix(y,790+Math.floor((i-90)/3)*17,access)}
  const opacity=appear*(lower && i>=126 ? 1-access : 1);
  return {x,y,opacity,access};
};

const Interface=({f})=>{
  const enter=p(f,1360,1480), scan=band(f,1390,1450,1580,1620), focus=band(f,1872,1930,2070,2120), second=p(f,1640,1770);
  const oldView=1-p(f,2412,2455), access=p(f,2455,2480);
  const grow=p(f,2140,2360);
  return <g opacity={enter}>
    <path d="M971 424 V981" stroke={C.muted} strokeWidth="2" opacity=".3"/>
    <g opacity={oldView}>
      <text x="1410" y="430" textAnchor="middle" fill={C.paper} fontSize="45">Interactive view</text>
      <path d="M1033 681 H1799" stroke={C.muted} strokeWidth="2" opacity=".55"/>
      <path d="M1033 952 H1799" stroke={C.muted} strokeWidth="2" opacity=".3"/>
      <text x="1062" y="739" fill={C.paper} fontSize="37"
        opacity={f<1872?1-p(f,1605,1650):p(f,1872,1940)}>Coverage</text>
      {chartData.map(d=>{
        const pt=chartPose(d,f), from=graphPose(d.n,f), travel=p(f,1370+d.i%18*3,1470+d.i%18*3);
        const rebuild=p(f,1872+d.i%18*2,1978+d.i%18*2);
        const useRebuild=d.lower&&f>=1872;
        const move=useRebuild?rebuild:travel;
        const lowerVisible=d.lower?(f<1872?1-p(f,1605,1650):rebuild):1;
        return <g key={d.i}>
          <path d={`M${from.x} ${from.y} C${from.x+200} ${from.y} 940 ${pt.y} ${pt.x} ${pt.y}`}
            fill="none" stroke={d.n.c} strokeWidth="1.6" opacity={Math.sin(move*Math.PI)*.26*(useRebuild?1:lowerVisible)}/>
          <rect x={mix(from.x,pt.x,move)-7} y={mix(from.y,pt.y,move)-6} width="15" height={d.lower?14:10}
            rx="3" fill={d.n.c} opacity={move*pt.opacity*(useRebuild?1:lowerVisible)}/>
        </g>;
      })}
      <path d={`M${mix(1080,1680,p(f,1460,1570))} 461 V669`} stroke={C.gold} strokeWidth="3" opacity={scan*.8}/>
      <rect x="1470" y="795" width="255" height="148" rx="10" fill="none" stroke={C.gold} strokeWidth="3"
        strokeDasharray="11 8" opacity={focus}/>
      <g opacity={band(f,1590,1630,2065,2115)}>
        {['By method','Over time'].map((label,j)=>{
          const x=1070+j*335, on=j===0?1-second:second;
          return <g key={label}>
            <rect x={x} y="966" width="296" height="73" rx="36" fill={colors[j]} opacity={.17+.66*on}/>
            <rect x={x} y="966" width="296" height="73" rx="36" fill="none" stroke={colors[j]} strokeWidth="2.5"/>
            <text x={x+148} y="1014" textAnchor="middle" fill={C.paper} fontSize="35">{label}</text>
          </g>;
        })}
        <path d="M0 0 V36 L12 27 21 46 30 40 21 20 H36Z" fill={C.paper}
          transform={`translate(${mix(1230,1580,second)} ${mix(1040,1014,p(f,1640,1700))})`}/>
      </g>
      <g opacity={band(f,2112,2160,2380,2425)}>
        {[0,1,2].map(i=>{
          const start=2142+i*62,q=p(f,start,start+74), target=graphPose(nodes[[327,340,350][i]],f);
          const sx=105+i*24,sy=1010+i*14;
          return <g key={i}>
            <ResearchPaper x={mix(sx,target.x,q)} y={mix(sy,target.y,q)} scale={mix(.42,.025,q)}
              opacity={1-p(f,start+54,start+77)} accent={colors[i]}/>
            {[0,1,2,3].map(k=><circle key={k} cx={target.x+Math.cos(k*1.57)*q*40} cy={target.y+Math.sin(k*1.57)*q*40}
              r="5" fill={colors[i]} opacity={p(f,start+50,start+80)*(1-p(f,start+120,start+150))}/>) }
            <path d={`M${target.x} ${target.y} C920 ${target.y} 940 595 1040 595`} fill="none" stroke={colors[i]} strokeWidth="3"
              strokeDasharray="12 13" strokeDashoffset={-q*90} opacity={band(f,start+60,start+83,start+130,start+162)}/>
          </g>;
        })}
        <path d={`M1032 ${mix(620,597,grow)} H1795`} stroke={C.gold} strokeWidth="2" opacity={grow*.4}/>
      </g>
    </g>
    <g opacity={access}>
      <text x="1410" y="430" textAnchor="middle" fill={C.paper} fontSize="46">Direct query</text>
      <rect x="1050" y="484" width="746" height="90" rx="14" fill="#1f2832" stroke={C.blue} strokeWidth="2.5"/>
      <text x="1085" y="543" fill={C.paper} fontSize="38">Findings where method = ...</text>
      <path d="M1120 601 H1723" stroke={C.blue} strokeWidth="3" strokeDasharray="14 14" strokeDashoffset={-f*.8}/>
      {['Finding','Context','Relation'].map((label,j)=><text key={label} x={1088+j*242} y="747" fill={colors[j]} fontSize="38">{label}</text>)}
      {chartData.filter(d=>d.lower&&d.i<126).map(d=>{
        const pt=chartPose(d,f),row=Math.floor((d.i-90)/3),fill=p(f,2450+row*7,2490+row*7);
        return <rect key={d.i} x={pt.x-15} y={pt.y-6} width={181*fill} height="9" rx="4"
          fill={d.n.c} opacity={pt.opacity*.9*fill}/>;
      })}
      <path d="M799 790 C890 790 913 840 1019 840" fill="none" stroke={C.purple} strokeWidth="3.5"
        strokeDasharray="8 11" strokeDashoffset={-f*.4}/>
    </g>
  </g>;
};

const Finale=({f})=>{
  const t=p(f,2615,2760), hold=band(f,2630,2680,2875,2880);
  return <g opacity={hold}>
    {Array.from({length:54},(_,i)=>{
      const a=i*2.39996,r=140+Math.sqrt((i+1)/54)*720,q=p(f,2615+i%12*2,2745+i%12*2);
      const parent=graphPose(nodes[(i*11)%324],f);
      const x=mix(parent.x,960+Math.cos(a)*r,q),y=mix(parent.y,850+Math.sin(a)*r*.24,q);
      return <g key={i} opacity={q*.64}>
        <path d={`M${parent.x} ${parent.y} Q${mix(parent.x,x,.45)} ${mix(parent.y,y,.28)-35} ${x} ${y}`}
          fill="none" stroke={colors[i%4]} strokeWidth="2.4" opacity={q*.7}/>
        <circle cx={x} cy={y} r={6+i%4*2} fill={colors[i%4]}/>
      </g>;
    })}
    <rect x="0" y="0" width="1920" height="1080" fill={C.bg} opacity={t*.18}/>
  </g>;
};

export const KnowledgeSynthesisFilmV8=()=>{
  const f=useCurrentFrame();
  return <>
    <style>{`@font-face{font-family:KnowledgeV8;src:url('${staticFile('landscape/space-bold.ttf')}')}`}</style>
    <svg viewBox="0 0 1920 1080" width="1920" height="1080"
      style={{position:'absolute',inset:0,fontFamily:'KnowledgeV8,Arial,sans-serif',fontWeight:700}}>
      <defs>
        <linearGradient id="v8-bg" x2="1" y2="1"><stop stopColor="#161821"/><stop offset="1" stopColor="#09121a"/></linearGradient>
        <linearGradient id="v8-scrim" x2="0" y2="1"><stop offset=".73" stopColor={C.bg}/><stop offset="1" stopColor={C.bg} stopOpacity="0"/></linearGradient>
      </defs>
      <rect width="1920" height="1080" fill="url(#v8-bg)" />
      {f<543 && <g opacity={1-p(f,520,543)}><Opening f={f}/></g>}
      {f>=520 && f<947 && <g opacity={p(f,520,543)}><Reconstruction f={f}/></g>}
      {f>=793 && <Graph f={f}/>}
      {f>=1340 && f<2680 && <Interface f={f}/>}
      {f>=2615 && <Finale f={f}/>}
      <rect width="1920" height="340" fill="url(#v8-scrim)" opacity={p(f,140,190)*(1-p(f,2620,2710))}/>
      <Caption f={f}/>
    </svg>
  </>;
};
