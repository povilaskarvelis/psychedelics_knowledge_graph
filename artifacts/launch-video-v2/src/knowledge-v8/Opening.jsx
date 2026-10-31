import React from 'react';
import {C, colors, clamp, mix, p, rnd} from '../knowledge-v7/model';

// Coordinates are in the parent 1920 × 1080 SVG. The middle paper is the
// same object that survives the opening flood and the single-paper close-up.
export const OPENING_PAPER_POSITIONS = [
  {x: 420, y: 690, scale: 1, variant: 'left', accent: C.blue},
  {x: 960, y: 690, scale: 1, variant: 'center', accent: C.gold},
  {x: 1500, y: 690, scale: 1, variant: 'right', accent: C.coral},
];

export const OPENING_PASSAGE_ANCHORS = [
  {x: 585, y: 790},
  {x: 795, y: 790},
  {x: 1125, y: 790},
  {x: 1335, y: 790},
];

const ARTICLE = {
  left: {
    number: '01',
    titleWidths: [274, 193],
    finding: 'FINDING 01',
  },
  center: {
    number: '02',
    titleWidths: [297, 232],
    finding: 'FINDING 02',
  },
  right: {
    number: '03',
    titleWidths: [260, 216],
    finding: 'FINDING 03',
  },
};

const outCubic = t => 1 - Math.pow(1 - clamp(t), 3);
const bodyBars = [292, 320, 252, 307, 270];

/** A reusable 400 × 510 paper, centered on x/y. */
export const ResearchPaper = ({
  x,
  y,
  scale = 1,
  opacity = 1,
  rotation = 0,
  variant = 'center',
  accent = C.gold,
  highlight = 0,
  detail = 1,
  compact = false,
}) => {
  const article = ARTICLE[variant] || ARTICLE.center;
  return <g transform={`translate(${x} ${y}) rotate(${rotation}) scale(${scale})`} opacity={opacity}>
    <rect x="-188" y="-244" width="400" height="510" rx="9" fill="#02080e" opacity=".48" />
    <rect x="-200" y="-255" width="400" height="510" rx="8" fill={C.paper} />
    <path d="M-200 -247 H200" stroke={accent} strokeWidth="15" />
    <path d="M-178 -210 H178" stroke={C.bg} strokeWidth="2" opacity=".18" />
    {compact ? <g>
      <rect x="-166" y="-187" width="211" height="18" rx="3" fill={accent} />
      <rect x="-166" y="-150" width="295" height="12" rx="3" fill={C.bg} opacity=".71" />
      {[-99, -66, -33, 0, 33, 66, 99, 132, 165, 198].map((y0, j) =>
        <rect key={j} x="-166" y={y0} width={bodyBars[j % 5]} height="8" rx="2" fill={C.bg} opacity={j < 4 ? '.35' : '.24'} />)}
    </g> : <g opacity={detail}>
      <text x="-164" y="-211" fill={C.bg} opacity=".67" fontSize="16" fontWeight="700" letterSpacing="3.2">RESEARCH ARTICLE</text>
      <text x="164" y="-211" textAnchor="end" fill={accent} fontSize="17" fontWeight="800" letterSpacing="2.2">{article.number}</text>
      <text x="-164" y="-163" fill={C.bg} fontSize="38" fontWeight="800" letterSpacing="-1.1">PAPER {article.number}</text>
      {article.titleWidths.map((width, i) => <rect key={i} x="-164" y={-143 + i * 29} width={width} height="15" rx="2" fill={C.bg} opacity={i ? '.52' : '.72'} />)}
      <text x="-164" y="-78" fill={C.bg} opacity=".52" fontSize="15" fontWeight="700" letterSpacing="1.1">METHOD  ·  CONTEXT  ·  OUTCOME</text>
      <path d="M-164 -67 H164" stroke={C.bg} strokeWidth="2" opacity=".25" />
      <text x="-164" y="-37" fill={C.bg} opacity=".8" fontSize="17" fontWeight="800" letterSpacing="2.4">ABSTRACT</text>
      {[-12, 13, 38].map((y0, i) => <rect key={i} x="-164" y={y0} width={[309, 325, 261][i]} height="7" rx="2" fill={C.bg} opacity=".27" />)}
      <rect x="-170" y="57" width="340" height="91" rx="5" fill={accent} opacity={.06 + highlight * .24} />
      <path d="M-169 58 V147" stroke={accent} strokeWidth={mix(4, 8, highlight)} opacity={mix(.4, 1, highlight)} />
      <text x="-150" y="89" fill={C.bg} fontSize="18" fontWeight="800" letterSpacing="1.3" opacity={.72 + highlight * .28}>RESULTS  /  {article.finding}</text>
      <rect x="-150" y="106" width="275" height="8" rx="2" fill={C.bg} opacity=".52" />
      <rect x="-150" y="124" width="222" height="8" rx="2" fill={C.bg} opacity=".39" />
      {[168, 187, 206, 225].map((y0, i) => <rect key={i} x="-164" y={y0} width={[312, 268, 318, 221][i]} height="7" rx="2" fill={C.bg} opacity=".23" />)}
    </g>}
    <path d="M-200 242 H200" stroke={accent} strokeWidth="4" opacity=".65" />
  </g>;
};

const PAPER_COUNT = 240;
const floodItems = Array.from({length: PAPER_COUNT}, (_, i) => {
  const angle = i * 2.39996323;
  const radius = 34 + Math.sqrt((i + .5) / PAPER_COUNT) * 1050;
  const start = i < 24 ? i * .55 : i < 84 ? 14 + (i - 24) * .53 : 46 + (i - 84) * .61;
  return {
    i,
    start,
    duration: 11 + Math.floor(rnd(i + 54) * 10),
    x: 960 + Math.cos(angle) * radius,
    y: 650 + Math.sin(angle) * radius * .61,
    scale: .17 + Math.sqrt((i + 1) / PAPER_COUNT) * .31 + rnd(i + 20) * .085,
    rotation: (rnd(i + 41) - .5) * 24,
    accent: colors[i % colors.length],
  };
});

const positionInFlood = (item, f) => {
  const t = clamp((f - item.start) / item.duration);
  const e = outCubic(t);
  const pass = clamp((f - item.start - item.duration) / 24);
  const side = item.x >= 960 ? 1 : -1;
  return {
    x: mix(960 + (rnd(item.i + 190) - .5) * 72, item.x, e) + side * 2250 * outCubic(pass),
    y: mix(650 + (rnd(item.i + 290) - .5) * 62, item.y, e) + (item.y >= 650 ? 1 : -1) * 560 * outCubic(pass),
    scale: mix(.018, item.scale, Math.pow(t, .72)) * (1 + .55 * pass),
    rotation: mix(item.rotation * .3, item.rotation, e) + side * 26 * pass,
    opacity: clamp(t * 5),
  };
};

const SpeedLines = ({f}) => <g>
  {floodItems.map(item => {
    if (item.i === 0 || f < item.start || f > item.start + item.duration + 24) return null;
    const now = positionInFlood(item, f);
    const before = positionInFlood(item, f - 4);
    const tail = clamp((item.start + item.duration + 24 - f) / 9);
    return <path key={item.i} d={`M${before.x} ${before.y} L${now.x} ${now.y}`} stroke={item.accent} strokeWidth={mix(1, 6, item.scale)} strokeLinecap="round" opacity={.32 * tail * now.opacity} />;
  })}
</g>;

const Flood = ({f}) => {
  const camera = mix(1.42, 1, p(f, 2, 142));
  return <g>
    <g transform={`translate(960 650) scale(${camera}) translate(-960 -650)`}>
    {[5, 44, 91].map((start, i) => {
      const t = clamp((f - start) / 21);
      return <circle key={start} cx="960" cy="650" r={mix(9, 770, t)} fill="none" stroke={colors[i]} strokeWidth={mix(12, 1, t)} opacity={f < start || t >= 1 ? 0 : .25 * (1 - t)} />;
    })}
    <SpeedLines f={f} />
    {floodItems.map(item => {
      if (item.i === 0 || f < item.start) return null;
      if (Math.min(f, 162) >= item.start + item.duration + 24) return null;
      const a = positionInFlood(item, Math.min(f, 162));
      const exit = clamp((f - 162 - item.i % 7 * 1.15) / 19);
      if (f > 162 && exit >= 1) return null;
      const outward = outCubic(exit);
      const side = item.x >= 960 ? 1 : -1;
      return <ResearchPaper
        key={item.i}
        x={a.x + side * 2250 * outward}
        y={a.y + (item.y >= 650 ? 1 : -1) * 480 * outward}
        scale={a.scale * (1 + outward * .55)}
        rotation={a.rotation + side * 34 * outward}
        opacity={a.opacity}
        accent={item.accent}
        compact
      />;
    })}
    </g>
    <defs>
      <radialGradient id="kv8-opening-text-well">
        <stop offset="0" stopColor={C.bg} stopOpacity="1" />
        <stop offset=".63" stopColor={C.bg} stopOpacity=".91" />
        <stop offset="1" stopColor={C.bg} stopOpacity="0" />
      </radialGradient>
    </defs>
    <ellipse cx="960" cy="465" rx="1080" ry="270" fill="url(#kv8-opening-text-well)" opacity={1-p(f,154,188)} />
  </g>;
};

const CenterPaper = ({f}) => {
  const base = positionInFlood(floodItems[0], Math.min(f, floodItems[0].start + floodItems[0].duration));
  const isolate = p(f, 162, 198);
  const split = p(f, 342, 407);
  const highlight = p(f, 403, 459);
  return <ResearchPaper
    x={mix(mix(base.x, 1120, isolate), 960, split)}
    y={mix(mix(base.y, 675, isolate), 690, split)}
    scale={mix(mix(base.scale, 1.4, isolate), 1, split)}
    rotation={mix(base.rotation, 0, isolate)}
    opacity={base.opacity}
    variant="center"
    accent={C.gold}
    detail={p(f, 158, 188)}
    highlight={highlight}
  />;
};

const RelatedPapers = ({f}) => {
  if (f < 342) return null;
  const split = p(f, 342, 407);
  const highlight = p(f, 403, 459);
  return <g>
    {[OPENING_PAPER_POSITIONS[0], OPENING_PAPER_POSITIONS[2]].map((paper, index) =>
      <ResearchPaper
        key={paper.variant}
        x={mix(1120 + (index ? 8 : -8), paper.x, split)}
        y={mix(675 + (index ? 9 : -9), paper.y, split)}
        scale={mix(1.19, 1, split)}
        rotation={mix(index ? 4 : -4, 0, split)}
        opacity={1}
        variant={paper.variant}
        accent={paper.accent}
        detail={split}
        highlight={highlight}
      />)}
  </g>;
};

const Relationships = ({f}) => {
  const show = p(f, 440, 484);
  const drawOne = p(f, 456, 504);
  const drawTwo = p(f, 471, 519);
  if (!show) return null;
  const links = [
    {d: 'M585 790 C641 704 737 704 795 790', color: C.blue, progress: drawOne},
    {d: 'M1125 790 C1181 875 1279 875 1335 790', color: C.coral, progress: drawTwo},
  ];
  return <g>
    {links.map((link, i) => <g key={i} opacity={show}>
      <path d={link.d} fill="none" stroke={link.color} strokeWidth="17" strokeLinecap="round" opacity=".15" pathLength="1" strokeDasharray="1" strokeDashoffset={1 - link.progress} />
      <path d={link.d} fill="none" stroke={link.color} strokeWidth="5" strokeLinecap="round" pathLength="1" strokeDasharray="1" strokeDashoffset={1 - link.progress} />
      <circle cx={i ? 1125 : 585} cy="790" r="10" fill={C.paper} stroke={link.color} strokeWidth="5" />
      <circle cx={i ? 1335 : 795} cy="790" r="10" fill={C.paper} stroke={link.color} strokeWidth="5" opacity={link.progress} />
    </g>)}
  </g>;
};

/** Transparent SVG fragment for frames 0–522, without captions. */
export const Opening = ({f}) => <g>
  <Flood f={f} />
  <RelatedPapers f={f} />
  <CenterPaper f={f} />
  <Relationships f={f} />
</g>;
