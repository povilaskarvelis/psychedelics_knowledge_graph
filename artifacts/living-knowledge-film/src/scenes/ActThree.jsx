import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import * as THREE from 'three';
import {Graph, useGraphBuffers} from '../three/Graph';
import {Post} from '../three/Post';
import {Rig, applyPose, project} from '../three/rig';
import {EXT} from '../data/extGraph';
import FLOWS from '../data/flows.json';
import {PSILO, AGENT, EDGE, FINDINGS, HERO_FINDING, HERO_CARD, COVERAGE, PUB_HISTORY, POPULATIONS} from '../data/product';
import {C, SPACE, PLEX, MONO} from '../lib/theme';
import {band, clamp, eio, eo3, eo5, hash, lin, mix} from '../lib/ease';
import {sp, track} from '../lib/spring';
import {Block} from '../ui/Type';
import {ACT2_END, ACT2_GRAPH, FLY, GP, B as B2} from './ActTwo';

// ACT III — the first one we built: psychedelic science. The living graph lands on the explorer's flow diagram, and the
// product is shown as motion graphics built from its real numbers rather than as screenshots. Explore drills down in a
// few clicks, from the whole field to one compound, one condition, the findings behind it, a single finding and the
// paper it comes from. Analyze gives the whole field at a glance: its publication history, its coverage (who or what was studied) and
// its gaps (one click swaps primary studies for meta-analyses). Then an agent asks the same graph over MCP. The type is a headline
// at the top. Local frames; sections start on bars (60 frames).
export const S = {land: 0, explore: 150, hover: 196, click: 232, edge: 300, list: 336, pick: 408, paper: 456, analyze: 510,
  meta: 690, gaps: 722, agents: 810, graph: 960, end: 1020};
const spc = (f, at, p = 'ui') => clamp(sp(f, at, p));
const ease = (f, a, b) => eo3(lin(f, a, b));
const PANEL = {background: 'rgba(13,17,18,0.96)', border: '1px solid rgba(255,255,255,0.09)', borderRadius: 16};
const LABEL = {fontFamily: MONO, fontSize: 15, letterSpacing: '0.12em', textTransform: 'uppercase', color: C.dim};
const fmt = (n) => Math.round(n).toLocaleString('en-US');
const soft = {teal: '#7fd6cb', gold: '#e6b765', rose: '#e992ae', green: '#a7be73'};
const DESIGN_COL = {RCT: C.gold, 'Observational study': C.teal, Qualitative: soft.rose, 'Open-label trial': soft.green};

// ---- the explorer's flow diagram (compounds → conditions), from its real geometry --------------------------------
const VIS = (y) => y > 140 && y < 1012;
const FL = FLOWS.flows.filter((fl) => VIS(fl.pts[0][1]) && VIS(fl.pts[fl.pts.length - 1][1]));
const HOVER = [361.1, 333.2]; // Psilocybin's marker
const MDD = [815.1, 207.5];   // Major depressive disorder's marker
const PSI = (fl) => Math.abs(fl.pts[0][0] - HOVER[0]) < 2 && Math.abs(fl.pts[0][1] - HOVER[1]) < 2;
const ISEDGE = (fl) => PSI(fl) && Math.abs(fl.pts[fl.pts.length - 1][1] - MDD[1]) < 3;
const fixLabel = (t) => t.replace(/([a-z])(depression|disorder|illness|syndrome)$/, '$1 $2');
const LEFT = FLOWS.labels.filter(([, x, y]) => x < 600 && VIS(y));
const RIGHT = FLOWS.labels.filter(([, x, y]) => x > 600 && VIS(y)).map(([t, x, y, w]) => [fixLabel(t), x, y, w]);
const MARKS = FLOWS.nodes.filter(([, y]) => VIS(y));
const DA = [535, 178, 1.0], DB = [120, 214, 0.86]; // diagram placement: centred, then left of the detail panel
const DA2 = [520, 171, 1.018]; // a slow push while it holds
const dgm = (f) => track(f, [[0, DA], [70, DA2, 'drift'], [S.explore + 8, DB]], 'soft');
const toF = (vx, vy, T) => [T[0] + (vx - 190) * T[2], T[1] + (vy - 150) * T[2]];
const flowD = (fl, T) => fl.pts.map(([x, y], k) => { const [X, Y] = toF(x, y, T); return `${k ? 'L' : 'M'}${X.toFixed(1)} ${Y.toFixed(1)}`; }).join(' ');
const PSI_ENDS = FL.filter(PSI).map((fl) => fl.pts[fl.pts.length - 1][1]);

const FlowDiagram = ({f}) => {
  const out = ease(f, S.pick - 4, S.pick + 16) * 0.85 + ease(f, S.analyze - 6, S.analyze + 16) * 0.15;
  if (out >= 0.999) return null;
  const T = dgm(f);
  const inA = lin(f, 44, 92);
  const hov = ease(f, S.hover, S.hover + 10), foc = ease(f, S.click + 2, S.click + 20), edg = ease(f, S.edge + 2, S.edge + 16);
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', inset: 0, opacity: 1 - out}}>
      <defs>
        <linearGradient id="flowg" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stopColor={C.teal} /><stop offset="1" stopColor="#bfeee8" /></linearGradient>
        <linearGradient id="flowh" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stopColor={C.gold} /><stop offset="1" stopColor="#f6dca8" /></linearGradient>
      </defs>
      {FL.map((fl, k) => {
        const p = PSI(fl), e = ISEDGE(fl);
        const d0 = 44 + ((fl.pts[0][1] - 150) / 860) * 26 + hash(k * 1.3) * 10;
        const draw = eo3(lin(f, d0, d0 + 26));
        if (draw <= 0) return null;
        let op = fl.op * 0.72 * inA * (p ? 1 + 0.7 * hov : 1 - 0.72 * hov - 0.2 * foc);
        if (p && !e) op *= 1 - 0.7 * edg;
        if (e) op *= 1 + 0.6 * edg;
        return <path key={k} d={flowD(fl, T)} fill="none" stroke={p && hov > 0.5 ? 'url(#flowh)' : 'url(#flowg)'} strokeWidth={fl.w * T[2] * (p ? 1 + 0.4 * hov : 1) * (e ? 1 + 1.4 * edg : 1)}
          strokeLinecap="round" pathLength={1} strokeDasharray={`${draw} 1`} opacity={op} />;
      })}
      {MARKS.map(([x, y], k) => {
        const [X, Y] = toF(x, y, T), psi = Math.abs(x - HOVER[0]) < 2 && Math.abs(y - HOVER[1]) < 2, mdd = Math.abs(x - MDD[0]) < 2 && Math.abs(y - MDD[1]) < 2;
        const right = x > 600, lit = right ? PSI_ENDS.some((e) => Math.abs(e - y) < 3) : psi;
        const a = ease(f, 52 + k * 1.2, 70 + k * 1.2) * (lit ? 1 : 1 - 0.7 * hov) * (psi || mdd ? 1 : 1 - 0.6 * edg);
        const big = psi ? 6 + 3 * hov : mdd ? 5 + 4 * edg : 5;
        return <circle key={k} cx={X} cy={Y} r={big * T[2] * 1.1} fill={C.bg} stroke={(psi && hov > 0.5) || (mdd && edg > 0.5) ? C.gold : C.teal} strokeWidth={2} opacity={a} />;
      })}
      {LEFT.map(([t, x, y, w], k) => {
        const [X, Y] = toF(x + w, y, T), psi = t === 'Psilocybin';
        return <text key={t} x={X - 4} y={Y + 5} textAnchor="end" fontFamily={PLEX} fontSize={18} fontWeight={psi ? 600 : 500}
          fill={psi && hov > 0.5 ? C.gold : C.fg} opacity={ease(f, 60 + k * 2, 78 + k * 2) * (psi ? 1 : 1 - 0.75 * hov)}>{t}</text>;
      })}
      {RIGHT.map(([t, x, y], k) => {
        const [X, Y] = toF(x, y, T), lit = PSI_ENDS.some((e) => Math.abs(e - y) < 22), mdd = t === 'Major depressive disorder';
        return <text key={t} x={X + 2} y={Y + 5} fontFamily={PLEX} fontSize={mdd ? 15.5 + 2.5 * edg : 15.5} fontWeight={mdd && edg > 0.5 ? 600 : 400} fill={mdd && edg > 0.5 ? C.gold : C.muted}
          opacity={ease(f, 66 + k * 1.4, 84 + k * 1.4) * (lit ? 1 : 1 - 0.7 * hov) * (mdd ? 1 : 1 - 0.55 * edg)}>{t}</text>;
      })}
    </svg>
  );
};
const Tooltip = ({f}) => {
  const a = band(f, S.hover + 4, S.hover + 12, S.click + 2, S.click + 12);
  if (a <= 0) return null;
  const [X, Y] = toF(...HOVER, dgm(f));
  return (
    <div style={{position: 'absolute', left: X + 22, top: Y + 16, opacity: a, transform: `translateY(${(1 - a) * 8}px)`, ...PANEL, padding: '14px 18px', borderRadius: 12}}>
      <div style={{fontFamily: SPACE, fontSize: 22, fontWeight: 600, color: C.gold}}>Psilocybin</div>
      <div style={{fontFamily: MONO, fontSize: 16, color: C.fg, marginTop: 6}}>{PSILO.tooltip.studies} studies · {PSILO.tooltip.findings} findings</div>
      <div style={{fontFamily: MONO, fontSize: 15, color: C.dim, marginTop: 4}}>Connections: {PSILO.tooltip.connections}</div>
    </div>
  );
};

// ---- the panel: a compound, then one compound–condition pair and the findings behind it ------------------------------
const P = {x: 990, y: 190, w: 810, h: 830};
const ROW_H = 118, LIST_TOP = 404; // findings rows inside the panel (panel-local y)
const listScroll = (f) => track(f, [[S.list, 0], [S.list + 16, 1.25 * ROW_H, 'slow'], [S.pick - 30, 1.5 * ROW_H, 'soft']], 'soft');
const heroRowRect = (f) => ({x: P.x + 30, y: P.y + LIST_TOP + HERO_FINDING * ROW_H - listScroll(f), w: P.w - 60, h: ROW_H - 12});
const Bars = ({data, max, h, f, t0, gold = -1}) => (
  <div style={{display: 'flex', alignItems: 'flex-end', gap: 8, height: h, borderBottom: '1px solid rgba(255,255,255,0.12)'}}>
    {data.map(([y, v], k) => {
      const g = eo5(lin(f, t0 + k * 2, t0 + 20 + k * 2));
      return <div key={y} style={{flex: 1, height: (v / max) * (h - 4) * g, background: k === gold ? soft.gold : soft.teal, opacity: 0.85, borderRadius: '3px 3px 0 0'}} />;
    })}
  </div>
);
const Tiles = ({f, t0, items}) => (
  <div style={{display: 'flex', gap: 16, marginTop: 20}}>
    {items.map(([l, n, sub], k) => (
      <div key={l} style={{flex: 1, padding: '12px 18px', borderRadius: 12, border: `1px solid ${k ? 'rgba(110,227,215,0.35)' : 'rgba(255,255,255,0.08)'}`, background: 'rgba(255,255,255,0.02)'}}>
        <div style={{fontFamily: PLEX, fontSize: 16, color: C.muted}}>{l}</div>
        <div style={{fontFamily: SPACE, fontSize: 34, fontWeight: 600, color: C.fg, fontVariantNumeric: 'tabular-nums'}}>{fmt(n * ease(f, t0 + k * 4, t0 + 24 + k * 4))}</div>
        {sub && <div style={{fontFamily: PLEX, fontSize: 14, color: C.dim}}>{sub}</div>}
      </div>
    ))}
  </div>
);
const Designs = ({f, t0, data, total, w}) => (
  <div>
    {data.slice(0, 4).map(([t, n], k) => (
      <div key={t} style={{display: 'flex', alignItems: 'center', gap: 12, height: 28}}>
        <div style={{width: 180, fontFamily: PLEX, fontSize: 16, color: C.muted}}>{t}</div>
        <div style={{width: w, height: 8, borderRadius: 4, background: 'rgba(255,255,255,0.05)'}}>
          <div style={{width: (n / total) * w * eo5(lin(f, t0 + k * 3, t0 + 22 + k * 3)), height: 8, borderRadius: 4, background: DESIGN_COL[t] || soft.teal, opacity: 0.9}} />
        </div>
        <div style={{fontFamily: MONO, fontSize: 15, color: C.fg}}>{n}</div>
      </div>
    ))}
  </div>
);
const ExplorePanel = ({f}) => {
  const t0 = S.click + 6;
  const inn = spc(f, t0, 'soft'), toPaper = eo3(lin(f, S.paper + 2, S.paper + 20)), out = eo3(lin(f, S.analyze - 6, S.analyze + 16));
  if (f < t0 - 1 || out >= 1) return null;
  const sw = eo3(lin(f, S.edge + 2, S.edge + 16)); // compound → pair
  const scroll = listScroll(f);
  return (
    <div style={{position: 'absolute', left: P.x, top: P.y, width: P.w, height: P.h, ...PANEL, overflow: 'hidden', boxSizing: 'border-box',
      opacity: clamp(inn * 1.4) * (1 - out) * (1 - toPaper) * (1 - 0.55 * ease(f, S.pick + 2, S.pick + 14)), transform: `translateX(${(1 - inn) * 120 + toPaper * 60}px)`}}>
      {/* the compound */}
      <div style={{position: 'absolute', inset: 0, padding: '28px 32px', opacity: 1 - sw, transform: `translateY(${-sw * 30}px)`}}>
        <div style={{display: 'flex', alignItems: 'baseline', justifyContent: 'space-between'}}>
          <div style={{fontFamily: SPACE, fontSize: 40, fontWeight: 600, color: C.fg, letterSpacing: '-0.02em'}}>Psilocybin</div>
          <div style={LABEL}>Primary studies</div>
        </div>
        <Tiles f={f} t0={t0 + 6} items={[['All studies', PSILO.studies], ['Open access', PSILO.open, `${Math.round((PSILO.open / PSILO.studies) * 100)}% of studies`]]} />
        <div style={{...LABEL, marginTop: 26}}>Publications per year</div>
        <div style={{marginTop: 12}}><Bars data={PSILO.perYear} max={96} h={140} f={f} t0={t0 + 14} gold={PSILO.perYear.length - 2} /></div>
        <div style={{display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 14, color: C.dim, marginTop: 6}}><span>2014</span><span>2026</span></div>
        <div style={{...LABEL, marginTop: 24, marginBottom: 10}}>Study designs</div>
        <Designs f={f} t0={t0 + 26} data={PSILO.designs} total={PSILO.designs[0][1]} w={420} />
      </div>
      {/* one compound–condition pair, and the findings behind it */}
      <div style={{position: 'absolute', inset: 0, padding: '28px 32px', opacity: sw, transform: `translateY(${(1 - sw) * 30}px)`}}>
        <div style={{fontFamily: SPACE, fontSize: 34, fontWeight: 600, color: C.fg, letterSpacing: '-0.02em'}}>
          Psilocybin <span style={{color: C.gold}}>→</span> Major depressive disorder
        </div>
        <div style={{display: 'flex', gap: 28, alignItems: 'flex-end', marginTop: 18}}>
          <div style={{width: 250}}>
            <div style={{fontFamily: PLEX, fontSize: 16, color: C.muted}}>Studies</div>
            <div style={{fontFamily: SPACE, fontSize: 44, fontWeight: 600, color: C.fg, fontVariantNumeric: 'tabular-nums'}}>{fmt(EDGE.studies * ease(f, S.edge + 8, S.edge + 30))}</div>
            <div style={{fontFamily: PLEX, fontSize: 15, color: C.gold}}>{EDGE.designs[0][1]} randomized trials</div>
          </div>
          <div style={{flex: 1}}>
            <div style={{...LABEL, fontSize: 13, marginBottom: 8}}>Publications per year · 2019–2026</div>
            <Bars data={EDGE.perYear} max={96} h={92} f={f} t0={S.edge + 12} gold={EDGE.perYear.length - 2} />
          </div>
        </div>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 34, opacity: ease(f, S.list - 4, S.list + 8)}}>
          <div style={{fontFamily: SPACE, fontSize: 24, fontWeight: 600, color: C.fg}}>Findings</div>
          <div style={{...LABEL, fontSize: 13}}>From {EDGE.studies} studies</div>
        </div>
      </div>
      {/* the findings list (scrolls: browse) */}
      <div style={{position: 'absolute', left: 30, right: 30, top: LIST_TOP, bottom: 20, overflow: 'hidden', opacity: ease(f, S.list, S.list + 10)}}>
        <div style={{transform: `translateY(${-scroll}px)`}}>
          {FINDINGS.map(([design, text, src], k) => {
            const hero = k === HERO_FINDING, sel = hero ? ease(f, S.pick - 2, S.pick + 6) : 0;
            const inRow = ease(f, S.list + 2 + k * 3, S.list + 14 + k * 3);
            return (
              <div key={k} style={{height: ROW_H - 12, marginBottom: 12, padding: '14px 18px', boxSizing: 'border-box', borderRadius: 12,
                border: `1px solid ${sel > 0.01 ? `rgba(241,183,75,${0.3 + 0.5 * sel})` : 'rgba(255,255,255,0.07)'}`, background: `rgba(255,255,255,${0.02 + 0.03 * sel})`,
                opacity: inRow, transform: `translateY(${(1 - inRow) * 20}px)`}}>
                <div style={{display: 'flex', alignItems: 'center', gap: 12}}>
                  <span style={{fontFamily: MONO, fontSize: 13, letterSpacing: '0.06em', color: DESIGN_COL[design] || C.muted, border: `1px solid ${(DESIGN_COL[design] || C.muted)}66`, borderRadius: 999, padding: '2px 10px'}}>{design}</span>
                  <span style={{fontFamily: MONO, fontSize: 13, color: C.dim}}>{src}</span>
                </div>
                <div style={{fontFamily: PLEX, fontSize: 17, lineHeight: 1.35, color: C.fg, marginTop: 8, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden'}}>{text}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

// the finding we open: it lifts out of the list and opens up, down to the paper it comes from
const FIELD_COL = {context: C.teal, method: C.rose};
const CARD_RECT = {x: 120, y: 214, w: 820, h: 740};
const HeroCard = ({f}) => {
  const t0 = S.pick;
  const g = clamp(sp(f, t0, 'snappy'), 0, 1.02), out = eo3(lin(f, S.analyze - 6, S.analyze + 16));
  if (f < t0 || out >= 1) return null;
  const r0 = heroRowRect(t0), R1 = CARD_RECT;
  const x = mix(r0.x, R1.x, g), y = mix(r0.y, R1.y, g), w = mix(r0.w, R1.w, g), h = mix(r0.h, R1.h, g);
  const c = ease(f, t0 + 5, t0 + 15);
  const link = ease(f, S.paper - 10, S.paper - 2), press = band(f, S.paper - 1, S.paper, S.paper + 1, S.paper + 5);
  return (
    <div style={{position: 'absolute', left: x, top: y, width: w, height: h, ...PANEL, background: 'rgba(12,16,17,0.98)', borderColor: 'rgba(241,183,75,0.5)',
      boxShadow: '0 40px 90px rgba(0,0,0,0.6)', overflow: 'hidden', opacity: 1 - out, transform: `translateX(${-out * 60}px)`}}>
      <div style={{padding: '28px 34px', opacity: c}}>
        <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16}}>
          <div style={{fontFamily: SPACE, fontSize: 27, fontWeight: 600, color: C.fg}}>{HERO_CARD.title}</div>
          <div style={{fontFamily: MONO, fontSize: 14, letterSpacing: '0.06em', color: C.gold, border: `1px solid ${C.gold}88`, borderRadius: 999, padding: '4px 14px'}}>{HERO_CARD.design}</div>
        </div>
        <div style={{marginTop: 18, padding: '14px 18px', borderLeft: `3px solid ${C.gold}`, background: 'rgba(241,183,75,0.07)', borderRadius: 6}}>
          <div style={{...LABEL, color: C.gold, fontSize: 14}}>Finding</div>
          <div style={{fontFamily: PLEX, fontSize: 22, lineHeight: 1.4, color: C.fg, marginTop: 4}}>{HERO_CARD.finding}</div>
        </div>
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '14px 26px', marginTop: 20}}>
          {HERO_CARD.fields.map(([l, v, kind], k) => (
            <div key={l} style={{opacity: ease(f, t0 + 18 + k * 3, t0 + 28 + k * 3), gridColumn: l === 'Population' || l === 'Administration' ? 'span 3' : undefined}}>
              <div style={{...LABEL, fontSize: 13, color: FIELD_COL[kind]}}>{l}</div>
              <div style={{fontFamily: PLEX, fontSize: 19, color: C.muted, marginTop: 2}}>{v}</div>
            </div>
          ))}
        </div>
        <div style={{marginTop: 26, paddingTop: 18, borderTop: '1px solid rgba(255,255,255,0.08)', opacity: ease(f, t0 + 34, t0 + 44)}}>
          <div style={{...LABEL, fontSize: 13}}>Source</div>
          <div style={{fontFamily: PLEX, fontSize: 20, lineHeight: 1.35, color: link > 0.5 ? C.gold : C.fg, marginTop: 6, textDecoration: link > 0.5 ? 'underline' : 'none',
            textUnderlineOffset: 5, transform: `scale(${1 - press * 0.01})`, transformOrigin: '0 50%'}}>{HERO_CARD.paper.title} ↗</div>
          <div style={{fontFamily: MONO, fontSize: 15, color: C.dim, marginTop: 6}}>{HERO_CARD.paper.journal} · {HERO_CARD.paper.year} · doi:{HERO_CARD.paper.doi}</div>
          <div style={{fontFamily: PLEX, fontSize: 15, color: C.muted, marginTop: 8}}>Other findings from this paper: {HERO_CARD.paper.more}</div>
        </div>
      </div>
    </div>
  );
};
// …and the paper itself
const PaperPage = ({f}) => {
  const t0 = S.paper + 4;
  const inn = spc(f, t0, 'soft'), out = eo3(lin(f, S.analyze - 6, S.analyze + 16));
  if (f < t0 - 1 || out >= 1) return null;
  const bar = (w, k) => <div key={k} style={{height: 7, width: `${w}%`, background: 'rgba(46,51,56,0.55)', borderRadius: 2, marginTop: 9}} />;
  return (
    <div style={{position: 'absolute', left: 1080, top: 186, width: 640, height: 830, background: '#efebe3', borderRadius: 4, boxShadow: '0 40px 100px rgba(0,0,0,0.7)',
      padding: '46px 52px', boxSizing: 'border-box', opacity: clamp(inn * 1.4) * (1 - out), transform: `translateX(${(1 - inn) * 140}px) rotate(${(1 - inn) * 2}deg)`}}>
      <div style={{display: 'flex', justifyContent: 'space-between', fontFamily: 'Georgia, serif', fontSize: 16, color: '#5e6468'}}>
        <span style={{fontWeight: 700, letterSpacing: '0.08em'}}>{HERO_CARD.paper.journal}</span><span>Original Investigation · {HERO_CARD.paper.year}</span>
      </div>
      <div style={{height: 3, background: '#2e3338', marginTop: 12, opacity: 0.7}} />
      <div style={{fontFamily: 'Georgia, serif', fontSize: 31, lineHeight: 1.25, fontWeight: 700, color: '#23282c', marginTop: 28}}>{HERO_CARD.paper.title}</div>
      <div style={{fontFamily: 'Georgia, serif', fontSize: 17, color: '#4a5055', marginTop: 16}}>{HERO_CARD.paper.authors}</div>
      <div style={{marginTop: 26, padding: '16px 18px', background: 'rgba(46,51,56,0.06)'}}>
        <div style={{fontFamily: 'Georgia, serif', fontSize: 15, fontWeight: 700, color: '#3a4045', letterSpacing: '0.06em'}}>ABSTRACT</div>
        {[98, 96, 99, 94, 97, 92, 98, 60].map(bar)}
      </div>
      <div style={{display: 'flex', gap: 28, marginTop: 20}}>
        <div style={{flex: 1}}>{[99, 97, 98, 95, 99, 97, 93, 99, 96, 70].map(bar)}</div>
        <div style={{flex: 1}}>{[98, 99, 96, 97, 99, 94, 98, 97, 99, 55].map(bar)}</div>
      </div>
      <div style={{position: 'absolute', left: 52, bottom: 34, fontFamily: 'Georgia, serif', fontSize: 14, color: '#6c7277'}}>doi:{HERO_CARD.paper.doi}</div>
    </div>
  );
};

// the cursor makes every click: the compound, the condition, one finding, its paper; then meta-analyses
const hoverPt = () => { const [x, y] = toF(...HOVER, DB); return [x + 3, y + 4]; };
const mddPt = () => { const [x, y] = toF(...MDD, DB); return [x + 3, y + 4]; };
const rowPt = () => { const r = heroRowRect(S.pick); return [r.x + r.w * 0.55, r.y + r.h * 0.62]; };
const linkPt = [CARD_RECT.x + 380, CARD_RECT.y + 588];
const CHIP_META = [1712, 560];
const Cursor = ({f}) => {
  const a = Math.max(band(f, S.explore + 14, S.explore + 24, S.paper + 20, S.paper + 30), band(f, S.meta - 40, S.meta - 30, S.gaps + 24, S.gaps + 34));
  if (a <= 0) return null;
  const pos = track(f, [[S.explore, [1300, 980]], [S.hover - 22, hoverPt()], [S.edge - 22, mddPt()], [S.pick - 22, rowPt()], [S.paper - 20, linkPt], [S.paper + 16, [1500, 1000]],
    [S.meta - 40, [1560, 900]], [S.meta - 18, CHIP_META], [S.gaps + 30, [1640, 1000]]], 'soft');
  const press = [S.click, S.edge, S.pick, S.paper, S.meta].reduce((m, t) => Math.max(m, band(f, t - 2, t, t + 1, t + 6)), 0);
  return (
    <svg width="26" height="31" viewBox="0 0 30 36" style={{position: 'absolute', left: pos[0] - 3, top: pos[1] - 2, opacity: a, transform: `scale(${1 - press * 0.14})`, transformOrigin: '0 0',
      filter: 'drop-shadow(0 3px 8px rgba(0,0,0,0.6))'}}>
      <path d="M3 2 L3 28 L10 21 L15 33 L20 31 L15 19 L25 19 Z" fill="#f4f6f5" stroke="#0a0c0d" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
};

// ---- the whole field at a glance (Analyze): publication history, coverage, gaps ----------------------------------------
const hexRgb = (h) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16));
const mixRgb = (a, b, t) => { const p = hexRgb(a), q = hexRgb(b); return p.map((v, k) => Math.round(v + (q[k] - v) * t)); };
const Head = ({title, sub, children}) => (
  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', height: 34}}>
    <div style={{whiteSpace: 'nowrap'}}>
      <span style={{fontFamily: SPACE, fontSize: 23, fontWeight: 600, color: C.fg}}>{title}</span>
      <span style={{...LABEL, fontSize: 12.5, marginLeft: 16}}>{sub}</span>
    </div>
    {children}
  </div>
);
const Chip = ({on, children, w}) => (
  <div style={{width: w, height: 32, boxSizing: 'border-box', borderRadius: 999, fontFamily: PLEX, fontSize: 15, display: 'flex', alignItems: 'center',
    justifyContent: 'center', whiteSpace: 'nowrap', color: on ? C.bg : C.muted, background: on ? soft.teal : 'rgba(255,255,255,0.04)',
    border: `1px solid ${on ? soft.teal : 'rgba(255,255,255,0.1)'}`}}>{children}</div>
);

// Publication history: papers per year, 2000–2025, stacked by kind (the site's Publication history panel). 2026 is still
// under way, so it stops at 2025.
const PH = PUB_HISTORY.filter(([y]) => y <= 2025);
const PH_KINDS = [['Primary studies', soft.teal], ['Reviews', soft.gold], ['Meta-analyses', soft.rose]];
const PX0 = 160, PX1 = 1760, PY0 = 458, PK = 196 / Math.max(...PH.map(([, p, r, m]) => p + r + m)); // plot box; px per paper
const PSLOT = (PX1 - PX0) / PH.length, PBW = 42;
const PubHistory = ({f, t0}) => {
  const grid = ease(f, t0 + 4, t0 + 18);
  const grow = (k) => eo5(lin(f, t0 + 10 + k * 2, t0 + 30 + k * 2));
  const ends = [0, PH.length - 1];
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', inset: 0}}>
      <defs>
        {PH.map(([y, p, r, m], k) => {
          const h = (p + r + m) * PK * grow(k);
          return <clipPath key={y} id={`ph${y}`}><rect x={PX0 + k * PSLOT + (PSLOT - PBW) / 2} y={PY0 - h} width={PBW} height={h + 6} rx={4} /></clipPath>;
        })}
      </defs>
      <line x1={PX0} x2={PX1} y1={PY0 + 0.5} y2={PY0 + 0.5} stroke="rgba(255,255,255,0.14)" strokeWidth={1} opacity={grid} />
      {PH.map(([y, ...n], k) => {
        const g = grow(k), x = PX0 + k * PSLOT + (PSLOT - PBW) / 2;
        let top = PY0;
        return (
          <g key={y} clipPath={`url(#ph${y})`}>
            {n.map((v, j) => { const h = v * PK * g; top -= h; return h > 0.01 ? <rect key={j} x={x} y={top} width={PBW} height={h} fill={PH_KINDS[j][1]} opacity={0.92} /> : null; })}
          </g>
        );
      })}
      {PH.map(([y], k) => (y % 5 ? null :
        <text key={y} x={PX0 + (k + 0.5) * PSLOT} y={PY0 + 26} textAnchor="middle" fontFamily={MONO} fontSize={15} fill={C.dim} opacity={grid}>{y}</text>
      ))}
      {ends.map((k) => { // the first year and the last, counted as their bars grow
        const [, p, r, m] = PH[k], g = grow(k), tot = p + r + m;
        return <text key={k} x={PX0 + (k + 0.5) * PSLOT} y={PY0 - tot * PK * g - 12} textAnchor="middle" fontFamily={SPACE} fontSize={24} fontWeight={600}
          fill={C.fg} opacity={clamp(g * 3)} style={{fontVariantNumeric: 'tabular-nums'}}>{fmt(tot * g)}</text>;
      })}
    </svg>
  );
};

// Coverage: who or what each compound's primary studies were done in — people, animals, cells
const DN = 132, DW = 440; // name column, bar width
const Coverage = ({f, t0}) => (
  <div style={{position: 'absolute', left: 144, top: 584, width: 780}}>
    {POPULATIONS.compounds.map(([name, v], r) => {
      const tot = v.reduce((a, b) => a + b, 0);
      let acc = 0;
      const g = eo5(lin(f, t0 + r * 5, t0 + 30 + r * 5));
      return (
        <div key={name} style={{position: 'relative', height: 58, opacity: lin(f, t0 - 4 + r * 5, t0 + 6 + r * 5)}}>
          <div style={{position: 'absolute', left: 0, top: 8, width: DN, textAlign: 'right', fontFamily: PLEX, fontSize: 16.5, color: C.fg}}>{name}</div>
          {v.map((n, j) => {
            const x = acc; acc += n;
            return <div key={j} style={{position: 'absolute', left: DN + 18 + (x / tot) * DW * g, top: 8, height: 24, width: Math.max(0, (n / tot) * DW * g - 2),
              background: POPULATIONS.groups[j][1], opacity: j === 0 ? 0.95 : 0.8, borderRadius: j === 0 ? '5px 0 0 5px' : j === v.length - 1 ? '0 5px 5px 0' : 0}} />;
          })}
          <div style={{position: 'absolute', left: DN + 18 + DW + 16, top: 9, fontFamily: MONO, fontSize: 15, color: C.muted, whiteSpace: 'nowrap', opacity: g}}>
            <span style={{color: soft.teal}}>{fmt(v[0])}</span> in people
          </div>
        </div>
      );
    })}
    <div style={{display: 'flex', gap: 18, marginTop: 14, marginLeft: DN + 18, opacity: lin(f, t0 + 30, t0 + 44)}}>
      {POPULATIONS.groups.map(([label, col]) => (
        <span key={label} style={{display: 'flex', alignItems: 'center', gap: 7, fontFamily: PLEX, fontSize: 13.5, color: C.muted, whiteSpace: 'nowrap'}}>
          <span style={{width: 10, height: 10, borderRadius: 2, background: col}} />{label}</span>
      ))}
    </div>
  </div>
);

// Gaps: conditions × compounds, papers per cell. One click swaps primary studies for meta-analyses; the pairs with 10 or
// more primary studies and no meta-analysis are outlined in gold
const G_ROWS = ['Treatment-resistant depression', 'Major depressive disorder', 'Post-traumatic stress disorder', 'Alcohol use disorder',
  'Substance use disorder', 'Opioid use disorder', 'Obsessive-compulsive disorder', 'Cluster headache'].map((n) => COVERAGE.rows.find((r) => r[0] === n));
const G_COLS = 6;
const GX = {x0: 1244, col: 88.7, y0: 612, row: 41, cw: 78, ch: 33};
const G_PMAX = Math.max(...G_ROWS.flatMap((r) => r[1].slice(0, G_COLS))), G_MMAX = Math.max(...G_ROWS.flatMap((r) => r[2].slice(0, G_COLS)));
const G_GAPS = G_ROWS.flatMap((r, i) => r[1].slice(0, G_COLS).map((p, j) => (p >= 10 && r[2][j] === 0 ? [i, j] : null)).filter(Boolean)).sort((a, b) => a[1] - b[1] || a[0] - b[0]);
const Gaps = ({f, t0}) => {
  const legend = ease(f, S.gaps + 10, S.gaps + 24);
  return (
    <>
      {COVERAGE.compounds.slice(0, G_COLS).map((c, j) => (
        <div key={c} style={{position: 'absolute', left: GX.x0 + j * GX.col, width: GX.col, top: 584, textAlign: 'center', fontFamily: PLEX, fontSize: 14.5,
          color: C.fg, opacity: ease(f, t0 + j * 2, t0 + 12 + j * 2)}}>{c}</div>
      ))}
      {G_ROWS.map(([name, P, M], i) => (
        <React.Fragment key={name}>
          <div style={{position: 'absolute', right: 1920 - GX.x0 + 14, top: GX.y0 + i * GX.row + 7, fontFamily: PLEX, fontSize: 14.5, whiteSpace: 'nowrap', color: C.muted,
            opacity: ease(f, t0 + 2 + i * 1.5, t0 + 14 + i * 1.5)}}>{name}</div>
          {P.slice(0, G_COLS).map((p, j) => {
            const m = M[j], k = G_GAPS.findIndex(([a, b]) => a === i && b === j);
            const inC = eo3(lin(f, t0 + 6 + j * 2.2 + i * 1.1, t0 + 20 + j * 2.2 + i * 1.1));
            const w = clamp(sp(f, S.meta + 2 + j * 2.2, 'soft'), 0, 1);           // primary studies → meta-analyses
            const shown = Math.round(mix(p, m, w));
            const strength = mix(Math.sqrt(p / G_PMAX), Math.sqrt(m / G_MMAX), w);
            const col = mixRgb(soft.teal, soft.rose, w);
            const g = k >= 0 ? eo3(lin(f, S.gaps + k * 4, S.gaps + k * 4 + 12)) : 0;
            return (
              <div key={j} style={{position: 'absolute', left: GX.x0 + j * GX.col + (GX.col - GX.cw) / 2, top: GX.y0 + i * GX.row + (GX.row - GX.ch) / 2,
                width: GX.cw, height: GX.ch, boxSizing: 'border-box', borderRadius: 7, opacity: inC, transform: `scale(${mix(0.86, 1, inC)})`,
                background: shown > 0 ? `rgba(${col.join(',')},${(0.14 + 0.66 * strength).toFixed(3)})` : 'rgba(255,255,255,0.015)',
                border: g > 0.01 ? `1.5px solid rgba(241,183,75,${(0.9 * g).toFixed(3)})` : '1px solid rgba(255,255,255,0.05)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: MONO, fontSize: 14.5, fontVariantNumeric: 'tabular-nums',
                color: strength > 0.8 ? C.bg : C.fg}}>
                {shown > 0 ? shown : g > 0.01 ? <span style={{color: C.gold, opacity: g}}>{p}</span> : ''}
              </div>
            );
          })}
        </React.Fragment>
      ))}
      <div style={{position: 'absolute', left: 988, top: 962, display: 'flex', alignItems: 'center', gap: 10, fontFamily: PLEX, fontSize: 14.5, color: C.muted, opacity: legend}}>
        <span style={{display: 'block', width: 20, height: 14, boxSizing: 'border-box', borderRadius: 4, border: `2px solid ${C.gold}`, background: 'rgba(241,183,75,0.08)'}} />
        10 or more primary studies, no meta-analysis yet
      </div>
    </>
  );
};

const Analyze = ({f}) => {
  if (f < S.analyze - 2 || f > S.agents + 24) return null;
  const t0 = S.analyze + 6;
  const inn = (at) => clamp(sp(f, at, 'soft'), 0, 1.02);
  const out = eo3(lin(f, S.agents - 6, S.agents + 18));
  const shift = (at) => ({opacity: clamp(inn(at) * 1.5) * (1 - out), transform: `translateX(${(1 - inn(at)) * 160 - out * 700}px)`});
  const box = (at, x, y, wd, h, children) => (
    <div style={{position: 'absolute', left: x, top: y, width: wd, height: h, ...PANEL, boxSizing: 'border-box', padding: '18px 24px', ...shift(at)}}>{children}</div>
  );
  const meta = f >= S.meta;
  return (
    <>
      {box(t0, 120, 164, 1680, 330, <Head title="Publication history" sub="Papers per year · 2000–2025">
        <div style={{display: 'flex', gap: 24, opacity: ease(f, t0 + 6, t0 + 20)}}>
          {PH_KINDS.map(([l, c]) => (
            <span key={l} style={{display: 'flex', alignItems: 'center', gap: 8, fontFamily: PLEX, fontSize: 16, color: C.muted, whiteSpace: 'nowrap'}}>
              <span style={{width: 12, height: 12, borderRadius: 3, background: c}} />{l}</span>
          ))}
        </div></Head>)}
      {box(t0 + 8, 120, 518, 820, 494, <Head title="Coverage" sub="Who or what was studied · primary studies" />)}
      {box(t0 + 16, 964, 518, 836, 494, <Head title="Gaps" sub="Conditions × compounds">
        <div style={{display: 'flex', gap: 8}}><Chip on={!meta} w={146}>Primary studies</Chip><Chip on={meta} w={140}>Meta-analyses</Chip></div></Head>)}
      <div style={{position: 'absolute', inset: 0, ...shift(t0)}}><PubHistory f={f} t0={t0} /></div>
      <div style={{position: 'absolute', inset: 0, ...shift(t0 + 8)}}><Coverage f={f} t0={t0 + 44} /></div>
      <div style={{position: 'absolute', inset: 0, ...shift(t0 + 16)}}><Gaps f={f} t0={t0 + 70} /></div>
    </>
  );
};

// ---- agents: the same graph over MCP (a real session against the live server) -------------------------------------
const LINES = [
  {t: 0, k: 'ask', s: 'Which psychedelics have been studied for PTSD?'},
  {t: 22, k: 'call', s: 'search_concepts', a: '{ query: "PTSD" }'},
  {t: 34, k: 'res', s: `Post-traumatic stress disorder · ${AGENT.ptsd} papers`},
  {t: 42, k: 'call', s: 'find_relationships', a: '{ object_ids: ["clinical_entity:post_traumatic_stress_disorder"] }'},
  {t: 58, k: 'res', s: `${AGENT.relationships} relationships across ${AGENT.ptsd} papers`},
  {t: 70, k: 'ans', s: `Most studied: MDMA (${AGENT.top[0][1]} papers), ketamine (${AGENT.top[1][1]}), psilocybin (${AGENT.top[2][1]}).`},
];
const Terminal = ({f}) => {
  const t0 = S.agents + 8;
  const inn = spc(f, t0, 'soft'), out = eo3(lin(f, S.graph - 22, S.graph - 4));
  if (f < t0 - 1 || out >= 1) return null;
  const local = f - t0 - 12;
  return (
    <div style={{position: 'absolute', left: 120, top: 250, width: 1000, height: 520, ...PANEL, borderColor: `${C.teal}40`, overflow: 'hidden',
      opacity: clamp(inn * 1.5) * (1 - out), transform: `translateX(${(1 - inn) * 160}px)`}}>
      <div style={{height: 52, borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', padding: '0 22px', gap: 9}}>
        {['#ff5f57', '#febc2e', '#28c840'].map((c) => <span key={c} style={{width: 12, height: 12, borderRadius: 12, background: c, opacity: 0.8}} />)}
        <span style={{marginLeft: 16, fontFamily: MONO, fontSize: 15, color: C.muted, letterSpacing: '0.04em'}}>agent · MCP · psychedelics-kg-api.onrender.com/mcp</span>
        <span style={{marginLeft: 'auto', fontFamily: MONO, fontSize: 13, letterSpacing: '0.12em', color: C.green}}>● CONNECTED</span>
      </div>
      <div style={{padding: '28px 34px', fontFamily: MONO, fontSize: 21, lineHeight: 1.62}}>
        {LINES.map((ln, k) => {
          const shown = local - ln.t;
          if (shown < 0) return null;
          const typed = (s, speed) => s.slice(0, Math.floor(clamp((shown * speed) / s.length) * s.length));
          if (ln.k === 'ask') return <div key={k} style={{color: C.fg, marginBottom: 16, display: 'flex', gap: 14}}><span style={{color: C.teal}}>›</span><span style={{fontFamily: PLEX, fontSize: 27}}>{typed(ln.s, 2.6)}</span></div>;
          if (ln.k === 'call') return <div key={k} style={{color: C.muted, marginTop: 4}}><span style={{color: C.teal}}>→ {typed(ln.s, 3)}</span>{' '}<span style={{color: C.dim, fontSize: 15}}>{shown > 5 ? typed(ln.a, 7) : ''}</span></div>;
          if (ln.k === 'res') return <div key={k} style={{color: C.gold, paddingLeft: 26, opacity: eo3(clamp(shown / 8))}}>← {ln.s}</div>;
          return <div key={k} style={{marginTop: 16, color: C.fg, fontFamily: PLEX, fontSize: 24, display: 'flex', gap: 14, opacity: eo3(clamp(shown / 6))}}><span style={{color: C.teal}}>◆</span>{typed(ln.s, 3)}</div>;
        })}
      </div>
    </div>
  );
};
// what the agent read from the graph, drawn as the results come back
const AnswerGraph = ({f}) => {
  const t0 = S.agents + 20;
  const a = lin(f, t0 + 30, t0 + 44) * (1 - lin(f, S.graph - 22, S.graph - 4));
  if (a <= 0) return null;
  const P = [1690, 520];
  const nodes = AGENT.top.map(([name, n], k) => ({name, n, pos: [1420 + k * 26, 330 + k * 190]}));
  const ptsdIn = spc(f, t0 + 34, 'pop');
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', inset: 0, opacity: a}}>
      {nodes.map((q, k) => {
        const at = t0 + 70 + k * 6, g = eo3(lin(f, at, at + 16));
        const mid = [(q.pos[0] + P[0]) / 2, (q.pos[1] + P[1]) / 2 - 40];
        return (
          <g key={q.name} opacity={g}>
            <path d={`M${q.pos[0]} ${q.pos[1]} Q${mid[0]} ${mid[1]} ${P[0]} ${P[1]}`} fill="none" stroke={C.gold} strokeWidth={2 + (q.n / 252) * 10} strokeLinecap="round"
              pathLength={1} strokeDasharray={`${g} 1`} opacity={0.75} />
            <circle cx={q.pos[0]} cy={q.pos[1]} r={9 + (q.n / 252) * 10} fill={C.bg} stroke={C.gold} strokeWidth={2.5} />
            <text x={q.pos[0] - 26} y={q.pos[1] + 7} textAnchor="end" fontFamily={PLEX} fontSize={22} fill={C.fg}>{q.name}</text>
            <text x={q.pos[0] - 26} y={q.pos[1] + 32} textAnchor="end" fontFamily={MONO} fontSize={16} fill={C.gold}>{q.n} papers</text>
          </g>
        );
      })}
      <g transform={`translate(${P[0]} ${P[1]}) scale(${Math.max(0.001, ptsdIn)})`}>
        <circle r={26} fill={C.bg} stroke={C.teal} strokeWidth={3} />
        <circle r={8} fill={C.teal} />
      </g>
      <text x={P[0] + 42} y={P[1] - 4} fontFamily={PLEX} fontSize={24} fill={C.fg} opacity={ptsdIn}>PTSD</text>
      <text x={P[0] + 42} y={P[1] + 22} fontFamily={MONO} fontSize={16} fill={C.muted} opacity={ptsdIn}>{AGENT.ptsd} papers</text>
    </svg>
  );
};

// ---- landing: every node of the living graph flies onto a point of the flow diagram --------------------------------
const base = new THREE.PerspectiveCamera(ACT2_END.pose.fov, 16 / 9, 0.05, 400);
applyPose(base, ACT2_END.pose);
const R = new THREE.Vector3().setFromMatrixColumn(base.matrixWorld, 0);
const U = new THREE.Vector3().setFromMatrixColumn(base.matrixWorld, 1);
const F = new THREE.Vector3().setFromMatrixColumn(base.matrixWorld, 2).negate();
const D0 = new THREE.Vector3(...GP).sub(base.position).dot(F);
const TANH = Math.tan(THREE.MathUtils.degToRad(ACT2_END.pose.fov / 2));
const planeAt = (sx, sy) => {
  const nx = (sx / 1920) * 2 - 1, ny = 1 - (sy / 1080) * 2, hh = D0 * TANH;
  return base.position.clone().addScaledVector(F, D0).addScaledVector(R, nx * hh * (16 / 9)).addScaledVector(U, ny * hh);
};
const PTS = [];
FL.forEach((fl) => fl.pts.forEach(([x, y]) => PTS.push([x, y])));
const BYSIZE = EXT.nodes.map((n, i) => i).sort((a, b) => EXT.nodes[b][5] - EXT.nodes[a][5]);
const MARK = new Map(MARKS.map((c, k) => [BYSIZE[k], c])); // the biggest nodes land on the diagram's markers
const target = (i) => MARK.get(i) || PTS[Math.floor(hash(i * 12.99 + 3.1) * PTS.length)];
const flatOf = (i) => { const w = planeAt(...toF(...target(i), DA)); return [w.x - GP[0], w.y - GP[1], w.z - GP[2]]; };
const landDelay = (i) => 0.28 * clamp((target(i)[0] - 200) / 700) + 0.1 * hash(i * 7.77); // a wave from compounds to conditions
const morphAmt = (f) => eio(lin(f, 0, 58));
const LandScene = ({f}) => {
  const buffers = useGraphBuffers({graph: EXT, ...ACT2_GRAPH, flat: flatOf, delay: landDelay, key: 'act3-land-v19'});
  const m = morphAmt(f);
  return (
    <>
      <color attach="background" args={[C.bg]} />
      <Rig pose={ACT2_END.pose} />
      <Graph buffers={buffers} f={f + B2.end} rotY={ACT2_END.rot + 0.028 * (1 - Math.exp(-f / 20))} position={GP} fly={FLY} scale={mix(320, 190, m)} grow={24}
        morph={m} breath={1 - m} alpha={1 - lin(f, 62, 90)} fog={[20 + 180 * m, 72 + 330 * m]} tint={C.teal} />
      <Post bloom={0} threshold={0.9} smoothing={0.15} radius={0.4} vignette={0} grain={0.02} />
    </>
  );
};

// ---- the end: psychedelic science as one graph again (Act IV pulls back from here) ---------------------------
const SYN = {a0: 0.35, r: 30, y: 6};
const HIC = 3; // lights up as the agent's answer: the evidence it gathered
export const endPose = (f) => {
  const a = SYN.a0 + (f - S.graph) * 0.0022;
  return {pos: [Math.sin(a) * SYN.r, SYN.y, Math.cos(a) * SYN.r], look: [0, 0, 0], fov: 44, roll: 0.02};
};
export const ACT3_END = {pose: endPose(S.end), angle: SYN.a0 + (S.end - S.graph) * 0.0022, r: SYN.r, y: SYN.y, uF: S.end + 2000, hic: HIC};
const EndScene = ({f}) => {
  const buffers = useGraphBuffers({graph: EXT, source: (i, n) => [n[0], n[1], n[2]], birth: () => -1000, key: 'act3-end'});
  const hi = eio(lin(f, S.graph + 14, S.graph + 48));
  return (
    <>
      <color attach="background" args={[C.bg]} />
      <Rig pose={endPose(f)} />
      <Graph buffers={buffers} f={f + 2000} rotY={0} scale={320} alpha={lin(f, S.graph - 4, S.graph + 18)}
        hiCluster={HIC} hiAmt={hi} focusCluster={HIC} focusAmt={hi * 0.7} fog={[20, 70]} />
      <Post bloom={0} threshold={0.9} smoothing={0.15} radius={0.4} vignette={0} grain={0.02} />
    </>
  );
};
export const HERO_TAG = [0, 9.5, 0]; // where the field's name sits above its graph (shared with Act IV)
export const FieldTag = ({x, y, text, a, gold}) => (
  <div style={{position: 'absolute', left: 0, top: 0, transform: `translate3d(${x}px, ${y}px, 0) translate(-50%, -100%)`, willChange: 'transform', opacity: a,
    fontFamily: MONO, fontSize: gold ? 22 : 17, letterSpacing: '0.16em', whiteSpace: 'nowrap', color: gold ? C.gold : C.muted,
    textShadow: '0 0 12px rgba(0,0,0,0.9)'}}>{text.toUpperCase()}</div>
);

// ---- headlines sit at the top, above the product ----------------------------------------------------------------
const HEAD = {x: 0, width: 1920, align: 'center', y: 66, anchor: 'top', size: 56, stagger: 1.6};
export const ActThree = () => {
  const f = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const tag = project(endPose(f), HERO_TAG);
  return (
    <AbsoluteFill style={{background: C.bg}}>
      {f < 100 && (
        <AbsoluteFill>
          <ThreeCanvas width={width} height={height} camera={{fov: 46, position: [0, 0, 30]}} gl={{antialias: false}}>
            <LandScene f={f} />
          </ThreeCanvas>
        </AbsoluteFill>
      )}
      {f >= S.graph - 10 && (
        <AbsoluteFill>
          <ThreeCanvas width={width} height={height} camera={{fov: 44, position: [0, 0, 30]}} gl={{antialias: false}}>
            <EndScene f={f} />
          </ThreeCanvas>
          <FieldTag x={tag.x} y={tag.y} text="Psychedelic science" a={lin(f, S.graph + 10, S.graph + 30)} gold />
        </AbsoluteFill>
      )}
      <FlowDiagram f={f} />
      <Tooltip f={f} />
      <ExplorePanel f={f} />
      <HeroCard f={f} />
      <PaperPage f={f} />
      <Analyze f={f} />
      <Terminal f={f} />
      <AnswerGraph f={f} />
      <Cursor f={f} />

      {/* the title from Act II hands over to this act's headline */}
      <Block f={f} at={-60} until={6} x={1250} width={600} size={100} weight={600} lh={1.02} tracking={-0.04} lines={['A **living**', 'knowledge', 'graph.']} />
      <Block f={f} at={16} until={S.explore - 8} {...HEAD} lines={['We built our first one for **psychedelic science.**']} />
      <Block f={f} at={S.explore + 4} until={S.analyze - 8} {...HEAD} lines={['All the evidence, **a few clicks away.**']} />
      <Block f={f} at={S.analyze + 4} until={S.agents - 8} {...HEAD} y={60} lines={['Understand the whole field **at a glance.**']} />
      <Block f={f} at={S.agents + 8} until={S.graph - 20} {...HEAD} lines={['AI agents can query it too — **through an API and MCP server.**']} />
    </AbsoluteFill>
  );
};
