import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Easing,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

const COLORS = {
  ink: '#06100e',
  paper: '#f0eee8',
  white: '#f7f6f1',
  mint: '#74f1cf',
  green: '#2dd3a8',
  blue: '#80b9ff',
  violet: '#aa8cff',
  amber: '#f2ca68',
  coral: '#ff8078',
  muted: '#91a6a0',
};

const FONT = '"Space Grotesk", "Helvetica Neue", Arial, sans-serif';
const BODY = '"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif';

const papers = [
  {
    title: 'Effects of Psilocybin-Assisted Therapy on Major Depressive Disorder',
    meta: 'JAMA Psychiatry · 2020 · Randomized clinical trial',
    term: 'Psilocybin',
    color: COLORS.mint,
  },
  {
    title: 'MDMA-assisted psychotherapy for post-traumatic stress disorder',
    meta: 'Progress in Neuro-Psychopharmacology · 2018',
    term: 'MDMA',
    color: COLORS.coral,
  },
  {
    title: 'Neural correlates of ego-dissolution under psilocybin',
    meta: 'Human Brain Mapping · 2015 · Neuroimaging',
    term: 'Brain systems',
    color: COLORS.blue,
  },
  {
    title: 'Cortisol Modulation by Ayahuasca in Treatment-Resistant Depression',
    meta: 'Frontiers in Psychiatry · 2018',
    term: 'Ayahuasca',
    color: COLORS.amber,
  },
  {
    title: 'Classification of psychedelics based on brain-wide imaging',
    meta: 'Nature Communications · 2025',
    term: 'Molecular effects',
    color: COLORS.violet,
  },
  {
    title: 'The therapeutic alliance and outcomes in psilocybin-assisted therapy',
    meta: 'PLOS ONE · 2024',
    term: 'Treatment context',
    color: COLORS.coral,
  },
  {
    title: 'Psilocybin in alcohol use disorder: a randomized clinical trial',
    meta: 'Addiction · 2025',
    term: 'Clinical outcomes',
    color: COLORS.green,
  },
  {
    title: 'Safety and efficacy of MDMA-assisted psychotherapy in PTSD',
    meta: 'Australian & New Zealand Journal of Psychiatry · 2025',
    term: 'Safety',
    color: COLORS.amber,
  },
];

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'};
const fadeWindow = (frame, start, end, edge = 12) =>
  interpolate(frame, [start, start + edge, end - edge, end], [0, 1, 1, 0], clamp);

const ease = Easing.bezier(0.22, 0.85, 0.28, 1);

const Background = ({tone = 'green'}) => {
  const frame = useCurrentFrame();
  const x = Math.sin(frame / 70) * 70;
  const y = Math.cos(frame / 83) * 55;
  const palette = tone === 'violet'
    ? ['rgba(129,84,255,.25)', 'rgba(45,211,168,.17)']
    : ['rgba(29,169,132,.24)', 'rgba(94,76,230,.16)'];

  return (
    <AbsoluteFill style={{background: COLORS.ink, overflow: 'hidden'}}>
      <div style={{
        position: 'absolute',
        width: 820,
        height: 820,
        left: -300 + x,
        top: -320 + y,
        borderRadius: '50%',
        background: `radial-gradient(circle, ${palette[0]} 0%, transparent 68%)`,
        filter: 'blur(14px)',
      }} />
      <div style={{
        position: 'absolute',
        width: 900,
        height: 900,
        right: -420 - x,
        bottom: -360 - y,
        borderRadius: '50%',
        background: `radial-gradient(circle, ${palette[1]} 0%, transparent 70%)`,
        filter: 'blur(10px)',
      }} />
      <div style={{
        position: 'absolute',
        inset: 0,
        opacity: 0.12,
        backgroundImage: 'linear-gradient(rgba(255,255,255,.10) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.08) 1px, transparent 1px)',
        backgroundSize: '54px 54px',
        transform: `translate(${frame % 54}px, ${frame % 54}px)`,
        maskImage: 'radial-gradient(circle at 50% 45%, black 0%, transparent 72%)',
      }} />
    </AbsoluteFill>
  );
};

const Grain = () => (
  <AbsoluteFill style={{
    pointerEvents: 'none',
    opacity: 0.14,
    mixBlendMode: 'soft-light',
    backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=%270 0 180 180%27 xmlns=%27http://www.w3.org/2000/svg%27%3E%3Cfilter id=%27n%27%3E%3CfeTurbulence type=%27fractalNoise%27 baseFrequency=%27.85%27 numOctaves=%273%27 stitchTiles=%27stitch%27/%3E%3C/filter%3E%3Crect width=%27100%25%27 height=%27100%25%27 filter=%27url(%23n)%27 opacity=%27.8%27/%3E%3C/svg%3E")',
  }} />
);

const BrandBug = ({dark = false, label = 'PSYCHEDELICS KNOWLEDGE GRAPH'}) => (
  <div style={{
    position: 'absolute',
    top: 48,
    left: 56,
    display: 'flex',
    alignItems: 'center',
    gap: 13,
    zIndex: 40,
    color: dark ? COLORS.ink : COLORS.white,
    fontFamily: FONT,
    fontWeight: 700,
    fontSize: 16,
    letterSpacing: 1.6,
  }}>
    <span style={{
      width: 12,
      height: 12,
      border: `2px solid ${dark ? COLORS.ink : COLORS.mint}`,
      borderRadius: '50%',
      boxShadow: `0 0 18px ${COLORS.mint}`,
    }} />
    {label}
  </div>
);

const SlideWords = ({children, localFrame, delay = 0, style = {}}) => {
  const p = spring({frame: localFrame - delay, fps: 30, config: {damping: 16, stiffness: 130, mass: 0.7}});
  return (
    <div style={{
      opacity: p,
      transform: `translateY(${(1 - p) * 54}px)`,
      clipPath: `inset(${(1 - p) * 100}% 0 0 0)`,
      ...style,
    }}>
      {children}
    </div>
  );
};

const PaperCard = ({paper, index, localFrame, compact = false}) => {
  const starts = [20, 34, 48, 27, 62, 42, 72, 55];
  const p = spring({frame: localFrame - starts[index], fps: 30, config: {damping: 16, stiffness: 95, mass: 0.9}});
  const target = [
    [-78, 244, -9],
    [468, 188, 7],
    [68, 605, 4],
    [575, 610, -6],
    [-118, 480, 9],
    [564, 365, 12],
    [245, 146, -3],
    [284, 704, 1],
  ][index];
  const sources = [
    [-580, 20],
    [1120, -190],
    [-220, 1140],
    [1300, 1120],
    [-620, 600],
    [1400, 320],
    [500, -420],
    [520, 1260],
  ][index];
  const x = interpolate(p, [0, 1], [sources[0], target[0]]);
  const y = interpolate(p, [0, 1], [sources[1], target[1]]);
  const rotate = interpolate(p, [0, 1], [target[2] * 2.8, target[2]]);
  const width = compact ? 320 : 420;

  return (
    <div style={{
      position: 'absolute',
      left: x,
      top: y,
      width,
      minHeight: compact ? 150 : 184,
      padding: compact ? '24px 25px' : '30px 32px',
      borderRadius: 11,
      background: 'linear-gradient(145deg, rgba(249,248,243,.98), rgba(224,229,222,.97))',
      color: COLORS.ink,
      boxShadow: '0 28px 70px rgba(0,0,0,.34), inset 0 0 0 1px rgba(255,255,255,.6)',
      transform: `rotate(${rotate}deg) scale(${interpolate(p, [0, 1], [.72, 1])})`,
      transformOrigin: 'center',
      opacity: p,
      fontFamily: BODY,
    }}>
      <div style={{width: 44, height: 4, borderRadius: 3, background: paper.color, marginBottom: 18}} />
      <div style={{fontSize: compact ? 18 : 21, lineHeight: 1.22, fontWeight: 700}}>{paper.title}</div>
      <div style={{fontSize: compact ? 11 : 13, lineHeight: 1.35, opacity: 0.58, marginTop: 15, textTransform: 'uppercase', letterSpacing: 0.7}}>{paper.meta}</div>
      <div style={{position: 'absolute', right: 16, top: 15, fontSize: 10, letterSpacing: 1.2, fontWeight: 700, color: paper.color}}>PAPER {String(index + 1).padStart(2, '0')}</div>
    </div>
  );
};

const Opening = () => {
  const frame = useCurrentFrame();
  const titleOut = interpolate(frame, [100, 145], [1, 0], clamp);
  const paperScale = interpolate(frame, [95, 170], [1, 1.16], {...clamp, easing: ease});
  const count = Math.round(interpolate(frame, [36, 118], [0, 21735], {...clamp, easing: Easing.out(Easing.cubic)}));
  const domains = ['MOLECULES', 'BRAIN SYSTEMS', 'SUBJECTIVE EXPERIENCE', 'CLINICAL OUTCOMES', 'SAFETY', 'REAL-WORLD USE'];

  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      <Background />
      <BrandBug />
      <div style={{position: 'absolute', inset: 0, transform: `scale(${paperScale})`}}>
        {papers.map((paper, index) => <PaperCard key={paper.title} paper={paper} index={index} localFrame={frame} compact />)}
      </div>
      <div style={{
        position: 'absolute',
        left: 55,
        top: 150,
        width: 970,
        opacity: titleOut,
        textShadow: '0 6px 40px rgba(0,0,0,.72)',
      }}>
        <SlideWords localFrame={frame} delay={0} style={{fontFamily: FONT, fontSize: 104, lineHeight: 0.9, letterSpacing: -6, fontWeight: 700, color: COLORS.white}}>
          PSYCHEDELIC
        </SlideWords>
        <SlideWords localFrame={frame} delay={8} style={{fontFamily: FONT, fontSize: 104, lineHeight: 0.98, letterSpacing: -6, fontWeight: 700, color: COLORS.mint}}>
          RESEARCH
        </SlideWords>
        <div style={{display: 'flex', alignItems: 'baseline', gap: 17, marginTop: 24, opacity: interpolate(frame, [34, 47], [0, 1], clamp)}}>
          <div style={{fontFamily: FONT, color: COLORS.white, fontSize: 42, fontWeight: 700, letterSpacing: -1}}>{count.toLocaleString()}</div>
          <div style={{fontFamily: BODY, color: COLORS.white, fontSize: 20, fontWeight: 500, letterSpacing: 1.4}}>PUBLICATIONS — AND GROWING</div>
        </div>
      </div>
      <div style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: 40,
        overflow: 'hidden',
        padding: '12px 0',
        borderTop: '1px solid rgba(255,255,255,.22)',
        borderBottom: '1px solid rgba(255,255,255,.22)',
        background: 'rgba(6,16,14,.72)',
        backdropFilter: 'blur(18px)',
        opacity: interpolate(frame, [70, 90], [0, 1], clamp),
      }}>
        <div style={{
          display: 'flex',
          gap: 32,
          width: 'max-content',
          transform: `translateX(${-((frame - 70) * 2.1) % 600}px)`,
          color: COLORS.white,
          fontFamily: FONT,
          fontWeight: 700,
          fontSize: 14,
          letterSpacing: 2,
        }}>
          {[...domains, ...domains, ...domains].map((domain, i) => <span key={i}>{domain} <b style={{color: COLORS.mint, marginLeft: 28}}>●</b></span>)}
        </div>
      </div>
      <Grain />
    </AbsoluteFill>
  );
};

const Scatter = () => {
  const frame = useCurrentFrame();
  const zoom = interpolate(frame, [0, 115], [1.1, 0.88], {...clamp, easing: ease});
  const paperOpacity = interpolate(frame, [0, 30, 88, 118], [.76, .43, .25, 0], clamp);
  const microPapers = Array.from({length: 32});

  return (
    <AbsoluteFill>
      <Background tone="violet" />
      <BrandBug />
      <div style={{position: 'absolute', inset: -100, opacity: paperOpacity, transform: `scale(${zoom}) rotate(-3deg)`}}>
        {microPapers.map((_, i) => {
          const col = i % 6;
          const row = Math.floor(i / 6);
          const drift = Math.sin(frame / 22 + i) * 12;
          return <div key={i} style={{
            position: 'absolute',
            left: col * 214 - 30 + (row % 2) * 75 + drift,
            top: row * 190 - 25 + Math.cos(frame / 28 + i) * 10,
            width: 182,
            height: 142,
            padding: 14,
            borderRadius: 5,
            background: 'rgba(238,239,232,.92)',
            boxShadow: '0 18px 35px rgba(0,0,0,.28)',
            transform: `rotate(${((i * 13) % 15) - 7}deg)`,
          }}>
            <div style={{height: 5, width: 44, background: papers[i % papers.length].color, marginBottom: 12}} />
            {[0, 1, 2, 3, 4].map((line) => <div key={line} style={{height: line === 0 ? 6 : 3, width: `${92 - line * 7}%`, background: line === 0 ? '#1f2c29' : '#7b8884', marginBottom: 7, opacity: .72}} />)}
          </div>;
        })}
      </div>
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(circle at center, rgba(6,16,14,.58) 0%, rgba(6,16,14,.94) 66%)'}} />
      <div style={{position: 'absolute', left: 60, right: 60, top: 245, textAlign: 'center'}}>
        <SlideWords localFrame={frame} delay={3} style={{fontFamily: FONT, color: COLORS.mint, fontSize: 21, letterSpacing: 3.5, fontWeight: 700}}>THE CURRENT RESEARCH RECORD</SlideWords>
        <SlideWords localFrame={frame} delay={18} style={{fontFamily: FONT, color: COLORS.white, fontSize: 73, lineHeight: .96, letterSpacing: -3.6, fontWeight: 700, marginTop: 26}}>
          THE FINDINGS ARE<br />SCATTERED ACROSS<br /><span style={{color: COLORS.amber}}>THOUSANDS OF PAPERS.</span>
        </SlideWords>
      </div>
      <div style={{
        position: 'absolute',
        bottom: 96,
        left: '50%',
        transform: 'translateX(-50%)',
        fontFamily: BODY,
        color: COLORS.muted,
        fontSize: 18,
        letterSpacing: .7,
        opacity: interpolate(frame, [42, 62], [0, 1], clamp),
      }}>Different questions. Different vocabularies. Different levels of explanation.</div>
      <Grain />
    </AbsoluteFill>
  );
};

const ExtractedChip = ({label, value, color, index, localFrame}) => {
  const p = spring({frame: localFrame - 28 - index * 8, fps: 30, config: {damping: 18, stiffness: 115}});
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '150px 1fr',
      gap: 12,
      alignItems: 'center',
      padding: '14px 16px',
      borderRadius: 10,
      background: 'rgba(255,255,255,.065)',
      border: '1px solid rgba(255,255,255,.10)',
      opacity: p,
      transform: `translateX(${(1 - p) * 70}px)`,
    }}>
      <span style={{fontFamily: FONT, fontSize: 11, letterSpacing: 1.5, color, fontWeight: 700}}>{label}</span>
      <span style={{fontFamily: BODY, fontSize: 17, color: COLORS.white}}>{value}</span>
    </div>
  );
};

const Structure = () => {
  const frame = useCurrentFrame();
  const paperIn = spring({frame, fps: 30, config: {damping: 18, stiffness: 90}});
  const recordIn = interpolate(frame, [22, 50], [0, 1], {...clamp, easing: ease});
  const lines = [
    ['COMPOUND', 'Psilocybin', COLORS.mint],
    ['POPULATION', 'Adults with major depressive disorder', COLORS.blue],
    ['DESIGN', 'Randomized clinical trial', COLORS.violet],
    ['OUTCOME', 'Depressive symptom severity', COLORS.amber],
    ['SOURCE', 'JAMA Psychiatry · DOI linked', COLORS.coral],
  ];

  return (
    <AbsoluteFill>
      <Background />
      <BrandBug />
      <div style={{position: 'absolute', left: 52, right: 52, top: 118}}>
        <SlideWords localFrame={frame} style={{fontFamily: FONT, fontSize: 54, lineHeight: 1, letterSpacing: -2.4, fontWeight: 700, color: COLORS.white}}>
          PUBLISHED FINDINGS
          <span style={{color: COLORS.mint}}> → </span>
          STRUCTURED KNOWLEDGE
        </SlideWords>
      </div>
      <div style={{
        position: 'absolute',
        left: 55,
        top: 274,
        width: 430,
        height: 630,
        padding: '45px 42px',
        borderRadius: 12,
        background: COLORS.paper,
        color: COLORS.ink,
        boxShadow: '0 38px 90px rgba(0,0,0,.48)',
        transform: `translateX(${(1 - paperIn) * -180}px) rotate(${(1 - paperIn) * -7}deg)`,
        opacity: paperIn,
        fontFamily: BODY,
      }}>
        <div style={{fontFamily: FONT, fontSize: 12, letterSpacing: 2, color: '#58716b', marginBottom: 26}}>RANDOMIZED CLINICAL TRIAL</div>
        <div style={{fontFamily: FONT, fontSize: 28, lineHeight: 1.12, fontWeight: 700}}>Effects of Psilocybin-Assisted Therapy on Major Depressive Disorder</div>
        <div style={{fontSize: 14, color: '#5f6d69', marginTop: 18}}>Davis et al. · JAMA Psychiatry · 2020</div>
        <div style={{height: 1, background: '#cbd2ce', margin: '28px 0 22px'}} />
        <div style={{fontFamily: FONT, fontSize: 13, fontWeight: 700, letterSpacing: 1}}>RESULTS</div>
        <div style={{fontSize: 16, lineHeight: 1.62, marginTop: 16, color: '#2b3b37'}}>
          In this randomized clinical trial, psilocybin-assisted therapy was associated with clinically meaningful changes in depressive symptoms.
        </div>
        {[62, 76, 92].map((top, i) => {
          const p = interpolate(frame, [24 + i * 9, 36 + i * 9], [0, 1], clamp);
          return <div key={top} style={{position: 'absolute', left: 38, top: `${top}%`, width: `${[72, 54, 81][i]}%`, height: 17, borderRadius: 4, background: [COLORS.mint, COLORS.blue, COLORS.amber][i], opacity: p * .28}} />;
        })}
        <div style={{position: 'absolute', left: 42, right: 42, bottom: 38, fontSize: 12, color: '#64736f'}}>doi.org/10.1001/jamapsychiatry.2020.3285</div>
      </div>
      <div style={{
        position: 'absolute',
        left: 530,
        top: 270,
        width: 495,
        padding: '28px',
        borderRadius: 18,
        background: 'rgba(6,20,17,.74)',
        border: '1px solid rgba(116,241,207,.22)',
        boxShadow: '0 30px 90px rgba(0,0,0,.38)',
        opacity: recordIn,
        transform: `translateX(${(1 - recordIn) * 80}px)`,
      }}>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18}}>
          <span style={{fontFamily: FONT, color: COLORS.white, fontSize: 16, fontWeight: 700, letterSpacing: 1.5}}>STRUCTURED FINDING</span>
          <span style={{fontFamily: FONT, color: COLORS.mint, fontSize: 11, letterSpacing: 1.5}}>SOURCE-LINKED</span>
        </div>
        <div style={{display: 'flex', flexDirection: 'column', gap: 10}}>
          {lines.map(([label, value, color], i) => <ExtractedChip key={label} label={label} value={value} color={color} index={i} localFrame={frame} />)}
        </div>
        <div style={{marginTop: 20, display: 'flex', alignItems: 'center', gap: 10, fontFamily: BODY, color: COLORS.muted, fontSize: 14}}>
          <span style={{width: 9, height: 9, borderRadius: '50%', background: COLORS.mint, boxShadow: `0 0 16px ${COLORS.mint}`}} />
          Ready to connect with the rest of the literature
        </div>
      </div>
      <Grain />
    </AbsoluteFill>
  );
};

const Network = ({localFrame, fade = 1}) => {
  const nodes = [
    [540, 430, 18, 'PSILOCYBIN', COLORS.mint],
    [265, 260, 12, 'DEPRESSION', COLORS.amber],
    [820, 252, 11, 'BRAIN SYSTEMS', COLORS.blue],
    [875, 585, 13, 'SAFETY', COLORS.coral],
    [230, 665, 10, 'SUBJECTIVE EFFECTS', COLORS.violet],
    [545, 790, 9, 'CLINICAL OUTCOMES', COLORS.green],
    [512, 140, 8, '5-HT2A', COLORS.violet],
  ];
  return (
    <AbsoluteFill style={{opacity: fade}}>
      <svg width="1080" height="1080" viewBox="0 0 1080 1080" style={{position: 'absolute', inset: 0}}>
        {nodes.slice(1).map((node, i) => {
          const p = interpolate(localFrame, [i * 5, i * 5 + 32], [0, 1], clamp);
          return <line key={i} x1="540" y1="430" x2={540 + (node[0] - 540) * p} y2={430 + (node[1] - 430) * p} stroke={node[4]} strokeOpacity={.48} strokeWidth={2} />;
        })}
      </svg>
      {nodes.map(([x, y, r, label, color], i) => {
        const p = spring({frame: localFrame - i * 5, fps: 30, config: {damping: 16, stiffness: 120}});
        return <div key={label} style={{position: 'absolute', left: x, top: y, opacity: p, transform: `translate(-50%, -50%) scale(${p})`}}>
          <div style={{width: r * 2, height: r * 2, borderRadius: '50%', background: color, boxShadow: `0 0 ${r * 2}px ${color}`}} />
          <div style={{position: 'absolute', left: r + 14, top: '50%', transform: 'translateY(-50%)', width: 180, color: COLORS.white, fontFamily: FONT, fontSize: 12, fontWeight: 700, letterSpacing: 1.2}}>{label}</div>
        </div>;
      })}
    </AbsoluteFill>
  );
};

const Connection = () => {
  const frame = useCurrentFrame();
  const sub = ['COMPOUNDS', 'RESEARCH AREAS', 'FINDINGS', 'SOURCES'];
  return (
    <AbsoluteFill>
      <Background tone="violet" />
      <Network localFrame={frame} />
      <BrandBug />
      <div style={{position: 'absolute', left: 55, top: 850, right: 55, padding: '28px 32px', borderRadius: 16, background: 'rgba(5,14,12,.76)', backdropFilter: 'blur(20px)', border: '1px solid rgba(255,255,255,.12)'}}>
        <div style={{fontFamily: FONT, fontSize: 22, color: COLORS.mint, letterSpacing: 2, fontWeight: 700, marginBottom: 15}}>ONE CONNECTED RESEARCH SYSTEM</div>
        <div style={{display: 'flex', gap: 13, alignItems: 'center'}}>
          {sub.map((word, i) => {
            const p = spring({frame: frame - 16 - i * 8, fps: 30, config: {damping: 18, stiffness: 115}});
            return <React.Fragment key={word}>
              <div style={{opacity: p, transform: `translateY(${(1 - p) * 20}px)`, fontFamily: FONT, color: COLORS.white, fontSize: 17, letterSpacing: 1, fontWeight: 700}}>{word}</div>
              {i < sub.length - 1 && <div style={{color: COLORS.muted, fontSize: 22}}>→</div>}
            </React.Fragment>;
          })}
        </div>
      </div>
      <Grain />
    </AbsoluteFill>
  );
};

const ProductFrame = ({src, localFrame, start = 0, style = {}}) => {
  const p = spring({frame: localFrame - start, fps: 30, config: {damping: 18, stiffness: 88, mass: .9}});
  return (
    <div style={{
      position: 'absolute',
      width: 1210,
      height: 756,
      overflow: 'hidden',
      borderRadius: 20,
      background: '#07100e',
      border: '1px solid rgba(255,255,255,.17)',
      boxShadow: '0 55px 140px rgba(0,0,0,.62), 0 0 0 1px rgba(116,241,207,.06)',
      opacity: p,
      transform: `translateY(${(1 - p) * 120}px) scale(${.88 + p * .12}) rotateX(${(1 - p) * 9}deg)`,
      ...style,
    }}>
      <div style={{height: 34, display: 'flex', alignItems: 'center', gap: 8, paddingLeft: 16, background: '#0b1513', borderBottom: '1px solid rgba(255,255,255,.08)'}}>
        {[COLORS.coral, COLORS.amber, COLORS.green].map((c) => <span key={c} style={{width: 8, height: 8, borderRadius: '50%', background: c, opacity: .8}} />)}
        <span style={{marginLeft: 16, fontFamily: BODY, fontSize: 11, color: '#74837f'}}>psychedelicskg.com</span>
      </div>
      <Img src={staticFile(src)} style={{width: '100%', height: 'calc(100% - 34px)', objectFit: 'cover', objectPosition: 'top left'}} />
    </div>
  );
};

const ProductMap = () => {
  const frame = useCurrentFrame();
  const move = interpolate(frame, [0, 155], [-72, -178], {...clamp, easing: ease});
  return (
    <AbsoluteFill>
      <Background />
      <BrandBug />
      <ProductFrame src="assets/explore-psilocybin.png" localFrame={frame} style={{left: -65, top: 155 + move / 6}} />
      <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(6,16,14,.08) 36%, rgba(6,16,14,.98) 83%)'}} />
      <div style={{position: 'absolute', left: 58, right: 58, bottom: 62}}>
        <SlideWords localFrame={frame} delay={10} style={{fontFamily: FONT, color: COLORS.white, fontSize: 59, letterSpacing: -2.8, lineHeight: .98, fontWeight: 700}}>
          A MAP OF THE<br /><span style={{color: COLORS.mint}}>RESEARCH LITERATURE.</span>
        </SlideWords>
        <div style={{display: 'flex', gap: 12, marginTop: 22}}>
          {['COMPOUNDS', 'RESEARCH AREAS', 'FINDINGS', 'SOURCE PAPERS'].map((word, i) => {
            const p = spring({frame: frame - 35 - i * 7, fps: 30, config: {damping: 18, stiffness: 130}});
            return <div key={word} style={{padding: '10px 14px', borderRadius: 99, border: '1px solid rgba(116,241,207,.28)', background: 'rgba(14,38,32,.80)', color: i === 0 ? COLORS.mint : COLORS.white, fontFamily: FONT, fontSize: 12, fontWeight: 700, letterSpacing: .8, opacity: p, transform: `translateY(${(1 - p) * 20}px)`}}>{word}</div>;
          })}
        </div>
      </div>
      <Grain />
    </AbsoluteFill>
  );
};

const Analyze = () => {
  const frame = useCurrentFrame();
  const imageSwap = interpolate(frame, [75, 100], [0, 1], clamp);
  const cards = [
    ['PUBLICATION HISTORY', 'See how the literature has changed over time.', COLORS.blue],
    ['ENTITY COVERAGE', 'Compare what the indexed publications cover.', COLORS.mint],
    ['RESEARCH-AREA OVERLAP', 'See where topics co-occur within reports.', COLORS.amber],
  ];
  return (
    <AbsoluteFill>
      <Background tone="violet" />
      <BrandBug label="PSYCHEDELICS KNOWLEDGE GRAPH · V2" />
      <div style={{position: 'absolute', right: -245, top: 150, width: 850, height: 790, perspective: 1200}}>
        <div style={{position: 'absolute', inset: 0, opacity: 1 - imageSwap}}><ProductFrame src="assets/analyze-overview.png" localFrame={frame} style={{left: 0, top: 0, width: 950, height: 594, transform: `rotateY(-8deg) translateX(${frame * -.15}px)`}} /></div>
        <div style={{position: 'absolute', inset: 0, opacity: imageSwap}}><ProductFrame src="assets/coverage.png" localFrame={frame - 65} style={{left: 0, top: 0, width: 950, height: 594, transform: 'rotateY(-8deg)'}} /></div>
      </div>
      <div style={{position: 'absolute', left: 56, top: 150, width: 600}}>
        <div style={{display: 'inline-flex', padding: '10px 14px', borderRadius: 99, background: COLORS.mint, color: COLORS.ink, fontFamily: FONT, fontWeight: 700, fontSize: 12, letterSpacing: 1.5, opacity: spring({frame, fps: 30})}}>NEW · ANALYZE</div>
        <SlideWords localFrame={frame} delay={8} style={{fontFamily: FONT, color: COLORS.white, fontSize: 67, lineHeight: .95, letterSpacing: -3.1, fontWeight: 700, marginTop: 28}}>
          PROFILE THE<br /><span style={{color: COLORS.mint}}>PUBLICATION<br />LANDSCAPE.</span>
        </SlideWords>
        <div style={{fontFamily: BODY, color: '#b5c5c0', fontSize: 20, lineHeight: 1.4, marginTop: 24, width: 500, opacity: interpolate(frame, [24, 44], [0, 1], clamp)}}>
          See how publications are distributed across time, entities, and research areas.
        </div>
      </div>
      <div style={{position: 'absolute', left: 55, right: 55, bottom: 62, display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 13}}>
        {cards.map(([title, body, color], i) => {
          const p = spring({frame: frame - 55 - i * 10, fps: 30, config: {damping: 17, stiffness: 115}});
          return <div key={title} style={{minHeight: 138, padding: '22px 21px', borderRadius: 14, background: 'rgba(5,17,14,.85)', border: '1px solid rgba(255,255,255,.11)', backdropFilter: 'blur(18px)', opacity: p, transform: `translateY(${(1 - p) * 45}px)`}}>
            <div style={{fontFamily: FONT, color, fontSize: 12, fontWeight: 700, letterSpacing: 1.2}}>{title}</div>
            <div style={{fontFamily: BODY, color: COLORS.white, fontSize: 16, lineHeight: 1.32, marginTop: 12}}>{body}</div>
          </div>;
        })}
      </div>
      <Grain />
    </AbsoluteFill>
  );
};

const Stat = ({number, label, color, localFrame, delay}) => {
  const p = spring({frame: localFrame - delay, fps: 30, config: {damping: 17, stiffness: 110}});
  return (
    <div style={{opacity: p, transform: `translateY(${(1 - p) * 45}px)`, padding: '28px 30px', borderLeft: `3px solid ${color}`}}>
      <div style={{fontFamily: FONT, color: COLORS.white, fontSize: 67, lineHeight: 1, fontWeight: 700, letterSpacing: -3}}>{number}</div>
      <div style={{fontFamily: FONT, color, fontSize: 13, fontWeight: 700, letterSpacing: 1.8, marginTop: 11}}>{label}</div>
    </div>
  );
};

const Finale = () => {
  const frame = useCurrentFrame();
  const brandP = spring({frame: frame - 86, fps: 30, config: {damping: 18, stiffness: 105}});
  const statsOut = interpolate(frame, [78, 105], [1, 0], clamp);
  return (
    <AbsoluteFill>
      <Background />
      <Network localFrame={frame} fade={interpolate(frame, [0, 80, 120], [.36, .18, .34], clamp)} />
      <div style={{position: 'absolute', left: 80, right: 80, top: 230, opacity: statsOut}}>
        <div style={{fontFamily: FONT, color: COLORS.mint, fontSize: 16, fontWeight: 700, letterSpacing: 2.7, marginLeft: 30, marginBottom: 22}}>A LIVING RESEARCH RESOURCE</div>
        <Stat number="21,735" label="PUBLICATIONS" color={COLORS.blue} localFrame={frame} delay={4} />
        <Stat number="99,100" label="STRUCTURED FINDINGS" color={COLORS.mint} localFrame={frame} delay={18} />
        <Stat number="15 SEP 2026" label="LITERATURE UPDATED" color={COLORS.amber} localFrame={frame} delay={32} />
      </div>
      <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', opacity: brandP, transform: `scale(${.92 + brandP * .08})`}}>
        <div style={{width: 72, height: 72, position: 'relative', marginBottom: 28}}>
          <div style={{position: 'absolute', inset: 8, border: `3px solid ${COLORS.mint}`, borderRadius: '50%', boxShadow: `0 0 34px rgba(116,241,207,.58)`}} />
          {[0, 1, 2, 3].map((i) => <div key={i} style={{position: 'absolute', width: 9, height: 9, borderRadius: '50%', background: [COLORS.blue, COLORS.amber, COLORS.coral, COLORS.violet][i], left: [0, 60, 8, 55][i], top: [20, 18, 58, 55][i]}} />)}
        </div>
        <div style={{fontFamily: FONT, color: COLORS.white, fontSize: 77, lineHeight: .93, letterSpacing: -4.2, fontWeight: 700}}>PSYCHEDELICS<br /><span style={{color: COLORS.mint}}>KNOWLEDGE GRAPH</span></div>
        <div style={{fontFamily: BODY, color: '#b5c7c1', fontSize: 24, marginTop: 25}}>A living map of psychedelic research.</div>
        <div style={{fontFamily: FONT, color: COLORS.white, fontSize: 20, fontWeight: 700, letterSpacing: 2.5, marginTop: 48, padding: '16px 24px', borderRadius: 99, border: '1px solid rgba(116,241,207,.34)', background: 'rgba(8,30,24,.72)'}}>PSYCHEDELICSKG.COM</div>
        <div style={{fontFamily: FONT, color: COLORS.amber, fontSize: 12, fontWeight: 700, letterSpacing: 2, marginTop: 18}}>V2 · UPDATED LITERATURE · NEW ANALYZE MODE</div>
      </div>
      <Grain />
    </AbsoluteFill>
  );
};

const Scene = ({from, duration, children}) => {
  const frame = useCurrentFrame();
  const opacity = fadeWindow(frame, from, from + duration, 10);
  return <Sequence from={from} durationInFrames={duration}><AbsoluteFill style={{opacity}}>{children}</AbsoluteFill></Sequence>;
};

export const LaunchFilm = () => (
  <AbsoluteFill style={{backgroundColor: COLORS.ink}}>
    <Audio src={staticFile('assets/soundtrack.wav')} volume={0.72} />
    <Scene from={0} duration={170}><Opening /></Scene>
    <Scene from={160} duration={130}><Scatter /></Scene>
    <Scene from={280} duration={160}><Structure /></Scene>
    <Scene from={430} duration={115}><Connection /></Scene>
    <Scene from={535} duration={160}><ProductMap /></Scene>
    <Scene from={685} duration={185}><Analyze /></Scene>
    <Scene from={860} duration={160}><Finale /></Scene>
  </AbsoluteFill>
);
