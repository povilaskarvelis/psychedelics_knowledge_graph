import React, {useMemo, useLayoutEffect} from 'react';
import * as THREE from 'three';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {Graph, useGraphBuffers, fieldLook, LOOK} from '../three/Graph';
import {Post} from '../three/Post';
import {Rig, project} from '../three/rig';
import {C, SPACE, PLEX} from '../lib/theme';
import {band, clamp, eio, eo3, eo5, eoExpo, eioExpo, hash, lin, mix} from '../lib/ease';
import {Block} from '../ui/Type';
import {EXT} from '../data/extGraph';
import {ACT3_END, FieldTag, HERO_TAG} from './ActThree';

// ACT IV — the potential: pull back from psychedelic science to a network of fields, linked to each other. The network
// rises into the top of the frame and the last two statements are set large beneath it, centred like the thesis.
// Then the end card.
export const D = {tagline: 120, card: 240, end: 420}; // tagline and card land on bars (60 frames)

const FIELDS = [
  {name: 'Psychedelic science', pos: [0, 0, 0], s: 1, ry: 0, hero: true}, // the graph Act III ends on
  {name: 'Oncology', pos: [-88, 22, -40], s: 0.9, ry: 1.1},
  {name: 'Climate science', pos: [96, -18, -70], s: 1.05, ry: 2.3},
  {name: 'Chemistry', pos: [-40, -30, 70], s: 0.85, ry: 0.4},
  {name: 'Genomics', nolabel: true, pos: [-72, -46, 86], s: 0.8, ry: 3.1},
  {name: 'Materials science', pos: [-150, -8, 30], s: 0.95, ry: 1.7},
  {name: 'Ecology', nolabel: true, pos: [150, 12, 10], s: 0.9, ry: 0.9},
  {name: 'Epidemiology', nolabel: true, pos: [20, 46, -120], s: 1, ry: 2.8},
  {name: 'Immunology', pos: [-110, 40, 110], s: 0.75, ry: 0.2},
  {name: 'Cardiology', pos: [118, 28, 118], s: 0.9, ry: 1.3},
  {name: 'Neuroscience', pos: [-20, -48, -150], s: 0.8, ry: 2.0},
  {name: 'Education research', nolabel: true, pos: [-190, 20, -110], s: 0.85, ry: 0.6},
  {name: 'Astrophysics', pos: [200, -40, -130], s: 0.8, ry: 1.9},
  {name: 'Economics', pos: [-60, 60, -210], s: 0.9, ry: 2.6},
  {name: 'Public health', nolabel: true, pos: [80, -58, -220], s: 0.85, ry: 0.1},
];

// every other field in its own hue (psychedelic science keeps the spectrum it has had since Act II)
const HUES = ['#7fb5f2', '#f4a27a', '#9ad27f', '#ae9df3', '#f0c35e', '#5fd6c8', '#ef8db0', '#6fc3e8', '#e6a3e0', '#c9d36a', '#f28f8f', '#8fa8f5', '#7fdcb4', '#f5b979'];
const LOOKS4 = FIELDS.map((q, k) => (k === 0 ? LOOK : fieldLook(HUES[(k - 1) % HUES.length])));

// the camera keeps Act III's orbit and pulls back until every field is in view
const cameraPose = (f) => {
  const a = ACT3_END.angle + f * 0.0022;
  const out = eioExpo(lin(f, 8, 132));
  const r = mix(ACT3_END.r, 250, out);
  return {pos: [Math.sin(a) * r, mix(ACT3_END.y, 70, out), Math.cos(a) * r], look: [0, mix(0, -38, out), 0], fov: mix(44, 50, out), roll: 0.02 + out * 0.05};
};

const staticSrc = (i, n) => [n[0], n[1], n[2]];
const staticBirth = () => -1000;

// arcs between fields: separate graphs become one network (the first links grow out of psychedelic science)
const MAJOR = EXT.nodes.map((n, i) => i).sort((a, b) => EXT.nodes[b][5] - EXT.nodes[a][5]).slice(0, 48);
const PAIRS = [];
FIELDS.forEach((a, i) => FIELDS.forEach((b, j) => {
  if (j <= i) return;
  const d = Math.hypot(a.pos[0] - b.pos[0], a.pos[1] - b.pos[1], a.pos[2] - b.pos[2]);
  if (d < 170) PAIRS.push([i, j]);
}));
const ARCS = PAIRS.flatMap(([i, j], p) => Array.from({length: 6}, (_, k) => ({
  i, j, a: MAJOR[Math.floor(hash(p * 13.1 + k * 1.7) * MAJOR.length)], b: MAJOR[Math.floor(hash(p * 7.3 + k * 2.9) * MAJOR.length)],
  t: 58 + (i === 0 || j === 0 ? 0 : 26) + hash(p * 3.7 + k * 5.1) * 50, gold: hash(p * 5.1 + k * 3.3) < 0.2, lift: 0.12 + hash(p * 9.1 + k) * 0.16,
  speed: 0.006 + hash(p * 2.3 + k * 4.4) * 0.006, phase: hash(p * 8.8 + k * 6.6),
})));
const SEGS = 16;
const fieldNode = (q, k, idx, f) => {
  const n = EXT.nodes[idx], a = q.ry + (k === 0 ? 0 : f * 0.002);
  const x = n[0] * Math.cos(a) + n[2] * Math.sin(a), z = -n[0] * Math.sin(a) + n[2] * Math.cos(a);
  return [q.pos[0] + x * q.s, q.pos[1] + n[1] * q.s, q.pos[2] + z * q.s];
};
const TEAL = [0.43, 0.89, 0.84], GOLD = [1, 0.72, 0.3];
const Bridges = ({f}) => {
  const {lines, dots, lg, dg} = useMemo(() => {
    const lgeo = new THREE.BufferGeometry();
    lgeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(ARCS.length * SEGS * 6), 3));
    lgeo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(ARCS.length * SEGS * 6), 3));
    const dgeo = new THREE.BufferGeometry();
    dgeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(ARCS.length * 3), 3));
    dgeo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(ARCS.length * 3), 3));
    const add = {transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, vertexColors: true};
    const l = new THREE.LineSegments(lgeo, new THREE.LineBasicMaterial(add));
    const d = new THREE.Points(dgeo, new THREE.PointsMaterial({...add, size: 3, sizeAttenuation: false}));
    l.frustumCulled = false; d.frustumCulled = false;
    return {lines: l, dots: d, lg: lgeo, dg: dgeo};
  }, []);
  const P = lg.getAttribute('position').array, Cc = lg.getAttribute('color').array;
  const DP = dg.getAttribute('position').array, DC = dg.getAttribute('color').array;
  const pt = (A, M, B, t) => [0, 1, 2].map((k) => (1 - t) * (1 - t) * A[k] + 2 * (1 - t) * t * M[k] + t * t * B[k]);
  ARCS.forEach((r, n) => {
    const A = fieldNode(FIELDS[r.i], r.i, r.a, f), B = fieldNode(FIELDS[r.j], r.j, r.b, f);
    const L = Math.hypot(B[0] - A[0], B[1] - A[1], B[2] - A[2]);
    const M = [(A[0] + B[0]) / 2, (A[1] + B[1]) / 2 + L * r.lift, (A[2] + B[2]) / 2];
    const g = eio(clamp((f - r.t) / 34));
    const col = r.gold ? GOLD : TEAL, w = (r.gold ? 0.5 : 0.3) * lin(f, r.t, r.t + 6);
    for (let s = 0; s < SEGS; s++) {
      const t0 = Math.min(s / SEGS, g), t1 = Math.min((s + 1) / SEGS, g);
      const p0 = pt(A, M, B, t0), p1 = pt(A, M, B, t1);
      const fade0 = 0.4 + 0.6 * Math.sin(Math.PI * (s / SEGS)), fade1 = 0.4 + 0.6 * Math.sin(Math.PI * ((s + 1) / SEGS));
      const o = (n * SEGS + s) * 6;
      P.set([...p0, ...p1], o);
      Cc.set([col[0] * w * fade0, col[1] * w * fade0, col[2] * w * fade0, col[0] * w * fade1, col[1] * w * fade1, col[2] * w * fade1], o);
    }
    const tp = (f * r.speed + r.phase) % 1, pd = pt(A, M, B, tp), on = g >= 1 ? Math.sin(Math.PI * tp) : 0;
    DP.set(pd, n * 3);
    DC.set([col[0] * on, col[1] * on, col[2] * on], n * 3);
  });
  lg.getAttribute('position').needsUpdate = true; lg.getAttribute('color').needsUpdate = true;
  dg.getAttribute('position').needsUpdate = true; dg.getAttribute('color').needsUpdate = true;
  useLayoutEffect(() => () => { lg.dispose(); dg.dispose(); lines.material.dispose(); dots.material.dispose(); }, [lines, dots, lg, dg]);
  return <><primitive object={lines} /><primitive object={dots} /></>;
};

const Scene3D = ({f}) => {
  const buffers = useGraphBuffers({graph: EXT, source: staticSrc, birth: staticBirth, key: 'static4-ext'});
  const pose = cameraPose(f);
  const hi = 1 - eio(lin(f, 24, 84)); // the answer's gold hands back to the whole field
  return (
    <>
      <color attach="background" args={[C.bg]} />
      <Rig pose={pose} />
      <Bridges f={f} />
      {FIELDS.map((q, k) => {
        const ign = k === 0 ? 1 : eoExpo(lin(f, 28 + k * 6, 54 + k * 6));
        return (
          <Graph key={k} buffers={buffers} f={k === 0 ? f + ACT3_END.uF : f + 2660 + k * 97} rotY={q.ry + (k === 0 ? 0 : f * 0.002)} position={q.pos} scaleAll={q.s}
            fog={k === 0 ? [20, 70] : [60, 420]} alpha={ign} bright={1 + (1 - ign) * 1.5}
            scale={k === 0 ? 320 : 460} hiCluster={k === 0 ? ACT3_END.hic : -9} hiAmt={k === 0 ? hi : 0} focusCluster={k === 0 ? ACT3_END.hic : -9} focusAmt={k === 0 ? hi * 0.7 : 0}
            look={LOOKS4[k]} />
        );
      })}
      <Post bloom={0} threshold={0.9} smoothing={0.15} radius={0.45} vignette={0} grain={0.02} />
    </>
  );
};

const FieldLabels = ({f}) => {
  const pose = cameraPose(f);
  const out = lin(f, D.card - 24, D.card - 6);
  return FIELDS.map((q, k) => {
    if (q.nolabel) return null; // unlabeled fields keep the wide shot legible
    const a = (q.hero ? 1 : eo3(lin(f, 50 + k * 6, 74 + k * 6))) * (1 - out);
    if (a <= 0) return null;
    const pt = project(pose, q.hero ? HERO_TAG : [q.pos[0], q.pos[1] + 17 * q.s, q.pos[2]]);
    if (!pt.visible) return null;
    return <FieldTag key={q.name} x={pt.x} y={pt.y} text={q.name} a={a} gold={q.hero} />;
  });
};

const Logo = ({size = 96, draw = 1}) => {
  const tips = [[32, 11], [51.972, 25.511], [44.344, 48.989], [19.656, 48.989], [12.028, 25.511]];
  return (
    <svg width={size} height={size} viewBox="0 0 64 64">
      <circle cx="32" cy="32" r="30.75" fill="none" stroke="#293132" strokeWidth="1.5" opacity={draw} />
      {tips.map(([x, y], k) => {
        const t = eo5(clamp(draw * 1.6 - k * 0.12));
        return <line key={k} x1={32} y1={32} x2={mix(32, x, t)} y2={mix(32, y, t)} stroke="#55bdb1" strokeWidth={2.75} strokeLinecap="round" opacity={0.78} />;
      })}
      {tips.map(([x, y], k) => {
        const t = eo5(clamp(draw * 1.6 - k * 0.12 - 0.25));
        return <circle key={k} cx={x} cy={y} r={4 * t} fill="#0b1414" stroke="#a8bab7" strokeWidth={2.75} opacity={t} />;
      })}
      <circle cx="32" cy="32" r={6.25 * eo5(clamp(draw * 2))} fill="#d4a650" />
    </svg>
  );
};

const EndCard = ({f}) => {
  const t = f - D.card;
  if (t < -2) return null;
  const a = eo3(lin(t, 0, 24));
  const fade = 1 - lin(f, D.end - 24, D.end);
  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', opacity: fade}}>
      <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
        <div style={{opacity: a, transform: `scale(${mix(0.8, 1, eo5(lin(t, 0, 30)))})`}}>
          <Logo size={120} draw={lin(t, 2, 40)} />
        </div>
        <div style={{marginTop: 40, fontFamily: SPACE, fontSize: 84, fontWeight: 600, letterSpacing: '-0.03em', color: C.fg, lineHeight: 1,
          opacity: eo3(lin(t, 14, 36)), transform: `translateY(${(1 - eo3(lin(t, 14, 40))) * 24}px)`, filter: `blur(${(1 - eo3(lin(t, 14, 36))) * 10}px)`}}>
          Psychedelics Knowledge Graph
        </div>
        <div style={{marginTop: 26, fontFamily: PLEX, fontSize: 28, color: C.muted, opacity: eo3(lin(t, 26, 48))}}>
          A living knowledge graph of psychedelic research.
        </div>
        <div style={{marginTop: 64, fontFamily: SPACE, fontSize: 40, fontWeight: 500, letterSpacing: '-0.01em', color: C.gold, opacity: eo3(lin(t, 42, 64))}}>
          psychedelicskg.com
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const ActFour = () => {
  const f = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const spaceOut = lin(f, D.card - 8, D.card + 16);
  return (
    <AbsoluteFill style={{background: C.bg}}>
      {f < D.card + 20 && (
        <AbsoluteFill style={{opacity: 1 - spaceOut}}>
          <ThreeCanvas width={width} height={height} camera={{fov: 44, position: [0, 0, 30]}} gl={{antialias: false}}>
            <Scene3D f={f} />
          </ThreeCanvas>
          <FieldLabels f={f} />
        </AbsoluteFill>
      )}
      <EndCard f={f} />

      <Block f={f} at={24} until={D.tagline - 6} x={0} width={1920} align="center" y={872} size={76} weight={600} tracking={-0.035} stagger={2.2}
        lines={['Now imagine this for **all of science.**']} />
      <Block f={f} at={D.tagline + 6} until={D.card - 14} x={0} width={1920} align="center" y={872} size={68} weight={600} tracking={-0.03} stagger={2}
        lines={['Every field connected — **and always up to date.**']} />
    </AbsoluteFill>
  );
};
