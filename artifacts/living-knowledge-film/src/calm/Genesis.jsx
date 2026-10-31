import React, {useMemo, useLayoutEffect} from 'react';
import * as THREE from 'three';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {useThree} from '@react-three/fiber';
import {PaperField} from '../three/PaperField';
import {Graph, useGraphBuffers} from '../three/Graph';
import {Post} from '../three/Post';
import {Rig} from '../three/rig';
import {EXT} from '../data/extGraph';
import {C} from '../lib/theme';
import {clamp, hash, lin, mix} from '../lib/ease';
import {sp} from '../lib/spring';
import {journalPage, PAPER_ASPECT, ATLAS_COLS, ATLAS_ROWS} from '../lib/textures';
import {Block} from '../ui/Type';

// GENESIS — the idea in one camera move. One paper; pulled back, the field of papers it belongs to, to the horizon. Down
// into one page: its findings, methods and context sit in prose. They lift off the page — and across the field every
// page gives up its pieces, which rise and connect into one graph, and new papers keep coming apart into it.
// Local frames at 90 bpm (20 frames = 1 beat, 80 = 1 bar).
export const G = {line1: 22, rise: 50, line2: 240, specks: 300, dive: 340, line3: 400, lift: 480, line4: 490, release: 640,
  line4b: 662, living: 800, end: 960};
const SEGCOL = {finding: C.gold, method: C.rose, context: C.teal};
const smoother = (t) => t * t * t * (t * (t * 6 - 15) + 10);

// ---- the field: pages lying on a plane, to the horizon ---------------------------------------------------------------
const SX = 0.95, SZ = 1.22, NX = 181, NZ = 85;
const BX = 40, BZ = 22; // the block whose pages become the graph (one per wall paper)
const CX = (NX - 1) / 2, CZ = (NZ - 1) / 2;
export const GPc = [0, 13, 0]; // where the graph forms, above the field
const HERO = 6; // the wall paper we read: one finding, one method, one context

// which wall paper sits in which block cell: ordered by where its contents end up, so the pieces rise almost straight up
const BLOCK = (() => {
  const W = EXT.wallPapers;
  const cen = W.map((p) => [0, 2].map((k) => p.members.reduce((s, m) => s + EXT.nodes[m][k], 0) / p.members.length));
  const order = W.map((p, j) => j).sort((a, b) => cen[a][0] - cen[b][0]);
  const grid = new Map(); // "ix,iz" -> wall paper index
  for (let c = 0; c < BX; c++) {
    const col = order.slice(c * BZ, (c + 1) * BZ).sort((a, b) => cen[a][1] - cen[b][1]);
    col.forEach((j, r) => grid.set(`${CX - BX / 2 + c},${CZ - BZ / 2 + r}`, j));
  }
  // the hero paper takes the centre cell
  const centre = `${CX},${CZ}`, heroKey = [...grid].find(([, j]) => j === HERO)[0];
  const displaced = grid.get(centre);
  grid.set(centre, HERO); grid.set(heroKey, displaced);
  return grid;
})();

const CELLS = [];
for (let iz = 0; iz < NZ; iz++) for (let ix = 0; ix < NX; ix++) {
  const k = CELLS.length;
  const x = (ix - CX) * SX + (hash(k * 1.7) - 0.5) * 0.16, z = (iz - CZ) * SZ + (hash(k * 2.3) - 0.5) * 0.16;
  const wall = BLOCK.get(`${ix},${iz}`) ?? -1;
  CELLS.push({x, z, y: hash(k * 5.9) * 0.006, r: Math.hypot(x, z), yaw: (hash(k * 3.1) - 0.5) * 0.2, v: Math.floor(hash(k * 4.7) * ATLAS_COLS * ATLAS_ROWS), wall,
    hero: ix === CX && iz === CZ});
}
const WALL_CELL = new Map(CELLS.filter((c) => c.wall >= 0).map((c) => [c.wall, c]));
// the wave of new papers landing while the camera pulls back: the front doubles its radius every 35 frames
const landAt = (r) => (r < 0.3 ? 0 : 128 + 28 * Math.log2(1 + r / 0.9));
// highlights spread across the field, and the pieces leave, in waves from the page we read
const speckAt = (r) => G.specks + r * 0.95;
const releaseAt = (r) => G.release + 8 + r * 1.6;

// ---- camera: one continuous move — monotone cubic splines through the keys (it holds only where keys repeat) ---------
const K = [
  {f: 0, T: [0.45, 0, 0], d: 1.75, phi: 88.8, th: 0, fov: 36},          // one page, left of its words
  {f: 120, T: [0.45, 0, 0], d: 2.1, phi: 88.4, th: 0.03, fov: 36},
  {f: 170, T: [0.3, 0, -0.4], d: 4.6, phi: 84, th: 0.07, fov: 37},       // the field lands around it
  {f: 235, T: [0.1, 0, -3.5], d: 17, phi: 62, th: 0.18, fov: 39},
  {f: G.specks, T: [0, 0, -17], d: 64, phi: 31, th: 0.32, fov: 40},     // the field, to the horizon
  {f: G.dive, T: [0, 0, -17], d: 65, phi: 31, th: 0.33, fov: 40},       // hold while the highlights spread
  {f: 380, T: [0.3, 0, -1.5], d: 9, phi: 52, th: 0.08, fov: 39},
  {f: 420, T: [0.62, 0, 0.05], d: 2.25, phi: 66, th: -0.1, fov: 38},    // down into one page
  {f: G.lift, T: [0.62, 0, 0.05], d: 2.3, phi: 65, th: -0.12, fov: 38},
  {f: 575, T: [0.52, 0.3, 0], d: 3.3, phi: 40, th: -0.4, fov: 38},      // the pieces lift: tilt for depth
  {f: G.release, T: [0.52, 0.3, 0], d: 3.4, phi: 39, th: -0.42, fov: 38},
  {f: 700, T: [2.5, 5, -1], d: 17, phi: 24, th: -0.56, fov: 40},
  {f: G.living, T: [5.6, 12, -2], d: 44, phi: 13, th: -0.7, fov: 42},   // out, to the graph they form
  {f: G.end, T: [5.9, 12, -2], d: 43, phi: 12, th: -0.82, fov: 42},
];
const monotone = (xs, ys) => { // Fritsch–Carlson: a smooth curve through the points that never overshoots them
  const n = xs.length, dl = [], m = new Array(n).fill(0);
  for (let i = 0; i < n - 1; i++) dl.push((ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]));
  for (let i = 1; i < n - 1; i++) m[i] = dl[i - 1] * dl[i] <= 0 ? 0 : (3 * (dl[i - 1] + dl[i])) / ((2 * dl[i] + dl[i - 1]) / dl[i - 1] + (dl[i] + 2 * dl[i - 1]) / dl[i]);
  return (x) => {
    if (x <= xs[0]) return ys[0];
    if (x >= xs[n - 1]) return ys[n - 1];
    let i = 0;
    while (x > xs[i + 1]) i++;
    const h = xs[i + 1] - xs[i], t = (x - xs[i]) / h, t2 = t * t, t3 = t2 * t;
    return (2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * m[i] + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h * m[i + 1];
  };
};
const FS = K.map((k) => k.f);
const CURVE = {tx: monotone(FS, K.map((k) => k.T[0])), ty: monotone(FS, K.map((k) => k.T[1])), tz: monotone(FS, K.map((k) => k.T[2])),
  ld: monotone(FS, K.map((k) => Math.log(k.d))), phi: monotone(FS, K.map((k) => k.phi)), th: monotone(FS, K.map((k) => k.th)), fov: monotone(FS, K.map((k) => k.fov))};
const camParams = (f) => ({T: [CURVE.tx(f), CURVE.ty(f), CURVE.tz(f)], d: Math.exp(CURVE.ld(f)), phi: CURVE.phi(f), th: CURVE.th(f), fov: CURVE.fov(f)});
export const genesisPose = (f) => {
  const {T, d, phi, th, fov} = camParams(f), p = (phi * Math.PI) / 180;
  return {pos: [T[0] + d * Math.cos(p) * Math.sin(th), T[1] + d * Math.sin(p), T[2] + d * Math.cos(p) * Math.cos(th)], look: T, fov, roll: 0};
};

// ---- the graph: block pages' contents rise into it; new papers come apart into it later ---------------------------------
const rotY = (f) => Math.max(0, f - G.release) * 0.0011;
const nodeInfo = new Map();
EXT.wallPapers.forEach((p, j) => {
  nodeInfo.set(p.node, {j, slot: -1, n: p.members.length});
  p.members.forEach((m, k) => nodeInfo.set(m, {j, slot: k, n: p.members.length}));
});
const LATE = EXT.latePapers;
LATE.forEach((p, k) => {
  nodeInfo.set(p.node, {late: true, k, slot: -1, n: p.members.length});
  p.members.forEach((m, s) => nodeInfo.set(m, {late: true, k, slot: s, n: p.members.length}));
});
const local = (w) => [w[0] - GPc[0], w[1] - GPc[1], w[2] - GPc[2]];
const rotated = (n, a) => [n[0] * Math.cos(a) + n[2] * Math.sin(a), n[1], -n[0] * Math.sin(a) + n[2] * Math.cos(a)];
const onPage = (cell, slot, n) => { // where a piece sits on its page before it leaves
  const a = (slot / n) * Math.PI * 2 + hash(cell.x * 3.1 + cell.z) * 6.28;
  return [cell.x + Math.cos(a) * 0.2, 0.09, cell.z + Math.sin(a) * 0.3];
};

// the three pieces we watch leave the page we read: they hover above it, facing us
const HERO_PAGE = {seed: 9025, titleLines: 3, figure: {kind: 0, colors: ['#90baff', '#f1b74b']}, rule: '#90baff'};
const HERO_MEMBERS = EXT.wallPapers[HERO].members;
const pieceType = (m) => { const t = EXT.nodes[m][3]; return t === 1 ? 'finding' : t === 4 ? 'method' : 'context'; };
const HOVER = {finding: [-0.32, 0.46, 0.12], method: [0.05, 0.56, 0.02], context: [0.42, 0.46, -0.08]};

// ---- arrivals: new papers fly in and come apart on their way (as in the living graph) -----------------------------------
const STREAM = [G.living + 15, G.end - 20], PEEL = 1.4, FADE = 12, U_BREAK = 0.55;
const incoming = LATE.map((p, k) => {
  const h = (q) => hash(k * 5.3 + q * 1.7 + 71);
  return {t: STREAM[0] + ((k + 0.5) / LATE.length) * (STREAM[1] - STREAM[0]) + (h(1) - 0.5) * 3, node: p.node, pre: 16 + h(2) * 8,
    up: (h(4) - 0.45) * 2.2, reach: 0.25 + h(5) * 0.5, spin: [(h(6) - 0.5) * 3, (h(7) - 0.5) * 3.5, (h(8) - 0.5) * 2], v: (k * 7) % 12};
});
const ARR = genesisPose((STREAM[0] + STREAM[1]) / 2);
const ARR_F = (() => { const d = ARR.look.map((v, k) => v - ARR.pos[k]), l = Math.hypot(...d); return d.map((v) => v / l); })();
const ARR_R = (() => { const r = [-ARR_F[2], 0, ARR_F[0]], l = Math.hypot(...r); return r.map((v) => v / l); })();
const ARR_U = [ARR_R[1] * ARR_F[2] - ARR_R[2] * ARR_F[1], ARR_R[2] * ARR_F[0] - ARR_R[0] * ARR_F[2], ARR_R[0] * ARR_F[1] - ARR_R[1] * ARR_F[0]];
const FACE = [-Math.asin(Math.max(-1, Math.min(1, -ARR_F[1] / Math.cos(Math.asin(-ARR_F[0]))))), Math.asin(-ARR_F[0])];
const arrival = (k) => { const q = incoming[k], n = EXT.nodes[q.node], r = rotated(n, rotY(q.t + 40)); return [GPc[0] + r[0], GPc[1] + r[1], GPc[2] + r[2]]; };
const launch = (k) => {
  const q = incoming[k], A = arrival(k), toCam = ARR.pos.map((v, j) => v - A[j]);
  return A.map((v, j) => v - ARR_R[j] * 20 + (j === 1 ? 5 + q.up * 4 : 0) + toCam[j] * q.reach);
};
const pageAt = (k, f) => {
  const q = incoming[k], S = launch(k), A = arrival(k);
  const M = S.map((v, j) => (v + A[j]) / 2 + (j === 1 ? 1.8 : 0));
  const u = ((f - (q.t - q.pre)) / q.pre) * U_BREAK;
  return {u, p: [0, 1, 2].map((j) => mix(mix(S[j], M[j], u), mix(M[j], A[j], u), u))};
};
const peelAt = (info) => incoming[info.k].t + (info.slot < 0 ? info.n * PEEL + 1 : info.slot * PEEL);
const peelFrom = (info) => {
  const c = pageAt(info.k, peelAt(info)).p;
  if (info.slot < 0) return c;
  const a = (info.slot / info.n) * Math.PI * 2 + hash(info.k * 3.3) * 6.28;
  return c.map((v, j) => v + ARR_R[j] * Math.cos(a) * 0.24 + ARR_U[j] * Math.sin(a) * 0.32);
};

// per-node timing and starting points
const heroSlot = (m) => HERO_MEMBERS.indexOf(m);
function graphBirth(i) {
  const info = nodeInfo.get(i);
  if (!info) return G.release + 40 + hash(i) * 30;             // shared hubs: they form as the structure connects
  if (info.late) return peelAt(info);
  if (info.j === HERO) return G.release + 4 + Math.max(0, info.slot) * 2;
  return releaseAt(WALL_CELL.get(info.j).r) + hash(i * 2.7) * 8;
}
function graphAppear(i) {
  const info = nodeInfo.get(i);
  if (!info) return graphBirth(i);
  if (info.late) return peelAt(info) - 1;
  if (info.j === HERO) return graphBirth(i) - 1;
  if (info.slot < 0) return graphBirth(i);                     // the paper itself joins as a node when it leaves
  return speckAt(WALL_CELL.get(info.j).r) + hash(i * 3.3) * 6; // its pieces show on the page first, as highlights
}
function graphSource(i) {
  const info = nodeInfo.get(i);
  if (!info) { const n = EXT.nodes[i]; return rotated(n, rotY(graphBirth(i))); }
  if (info.late) return local(peelFrom(info));
  const cell = WALL_CELL.get(info.j);
  if (info.j === HERO && info.slot >= 0) return local(HOVER[pieceType(i)]);
  if (info.slot < 0) return local([cell.x, 0.04, cell.z]);
  return local(onPage(cell, info.slot, info.n));
}
const graphSeed = (i, n) => (n[7] ? hash(i * 1.37) * 0.6 : hash(i * 1.37));
const graphEase = (i) => (nodeInfo.get(i)?.late ? 1 : 0);
export const GEN_GRAPH = {source: (i) => graphSource(i), birth: (i) => graphBirth(i), appear: (i) => graphAppear(i), seedOf: graphSeed, easeOf: graphEase};
export const GEN_END = {pose: genesisPose(G.end), rot: rotY(G.end)};

// ---- 3D pieces ---------------------------------------------------------------------------------------------------------
const Field = ({f}) => (
  <PaperField count={CELLS.length} variant={(k) => CELLS[k].v} fog={[34, 110]} bright={0.72}
    layout={(k, o) => {
      const c = CELLS[k];
      if (c.hero) { o.alpha = 0; return; }
      const t0 = landAt(c.r);
      if (f < t0) { o.alpha = 0; return; }
      const e = clamp(sp(f, t0, 'ui'), 0, 1.04);
      o.x = c.x; o.z = c.z; o.y = c.y + (1 - clamp(e)) * 0.6; o.rx = -Math.PI / 2; o.rz = c.yaw; o.s = 1;
      const dim = 1 - 0.93 * smoother(lin(f, G.dive + 10, G.dive + 60)); // the page we read takes the light
      const gone = c.wall >= 0 ? lin(f, releaseAt(c.r) + 6, releaseAt(c.r) + 26) : lin(f, G.release + 20 + c.r * 1.2, G.release + 50 + c.r * 1.2);
      o.alpha = clamp(e * 1.6) * dim * (1 - gone);
    }} />
);

// the page we read: drawn at full resolution, with its highlights in the colours of the words that name them
const Highlights = ({f, page, times, fade}) => {
  const mats = useMemo(() => page.segs.map((sg) => new THREE.MeshBasicMaterial({color: new THREE.Color(SEGCOL[sg.type]).lerp(new THREE.Color('#ffffff'), 0.12),
    transparent: true, opacity: 0, depthWrite: false, blending: THREE.MultiplyBlending, premultipliedAlpha: true})), [page]);
  useLayoutEffect(() => () => mats.forEach((m) => m.dispose()), [mats]);
  return (
    <group rotation={[-Math.PI / 2, 0, 0]}>
      {page.segs.map((sg, k) => {
        const t0 = times[sg.type] + (k >= 3 ? 3 : 0);
        mats[k].opacity = smoother(lin(f, t0, t0 + 10)) * fade * 0.9;
        const w = (sg.u1 - sg.u0) * PAPER_ASPECT, h = sg.v1 - sg.v0, grow = clamp(sp(f, t0, 'snappy'), 0, 1.05);
        const cx = ((sg.u0 + sg.u1) / 2 - 0.5) * PAPER_ASPECT, cy = (sg.v0 + sg.v1) / 2 - 0.5;
        return (
          <mesh key={k} position={[cx - w / 2 + (w * grow) / 2, cy, 0.002]} material={mats[k]} renderOrder={5}>
            <planeGeometry args={[Math.max(0.0001, w * grow), h * 1.15]} />
          </mesh>
        );
      })}
    </group>
  );
};
const HeroPage = ({f}) => {
  const page = journalPage(HERO_PAGE, 1400);
  const a = smoother(lin(f, 2, 50)) * (1 - lin(f, G.release + 4, G.release + 30));
  const marks = G.line3 + 6; // in step with the marks on the words
  return (
    <>
      <PaperField count={1} map={page.tex} cols={1} rows={1} variant={() => 0} fog={[80, 400]} bright={0.86}
        layout={(i, o) => { o.rx = -Math.PI / 2; o.alpha = a; }} />
      <Highlights f={f} page={page} times={{finding: marks + 2, method: marks + 8, context: marks + 14}} fade={1 - lin(f, G.lift + 6, G.lift + 24)} />
    </>
  );
};

// a lifted piece: the highlighted phrase, now a chip of its own colour with its words still on it
const chipTexture = (() => {
  const cache = {};
  return (type) => {
    if (cache[type]) return cache[type];
    const W = 512, H = 112, cv = document.createElement('canvas');
    cv.width = W; cv.height = H;
    const ctx = cv.getContext('2d');
    ctx.fillStyle = SEGCOL[type]; ctx.beginPath(); ctx.roundRect(4, 4, W - 8, H - 8, 28); ctx.fill();
    ctx.fillStyle = 'rgba(20,24,26,0.72)';
    [[40, 130], [184, 96], [294, 150]].forEach(([x, w]) => { ctx.beginPath(); ctx.roundRect(x, H / 2 - 12, w, 24, 10); ctx.fill(); });
    const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
    return (cache[type] = tex);
  };
})();
const tmpO = new THREE.Object3D(), qFlat = new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0)), qOut = new THREE.Quaternion();
const Chips = ({f, pose}) => {
  const page = journalPage(HERO_PAGE, 1400);
  const segs = page.segs.slice(0, 3); // the three highlights in the abstract
  const mats = useMemo(() => ['finding', 'method', 'context'].map((t) => new THREE.MeshBasicMaterial({map: chipTexture(t), transparent: true, depthWrite: false})), []);
  useLayoutEffect(() => () => mats.forEach((m) => m.dispose()), [mats]);
  if (f < G.lift - 1 || f > G.release + 14) return null;
  return segs.map((sg, k) => {
    const type = sg.type, mi = ['finding', 'method', 'context'].indexOf(type);
    const t = clamp(sp(f, G.lift + mi * 7, 'soft'), 0, 1.02), e = clamp(t);
    const start = [((sg.u0 + sg.u1) / 2 - 0.5) * PAPER_ASPECT, 0.006, -((sg.v0 + sg.v1) / 2 - 0.5)];
    const end = HOVER[type];
    const p = start.map((v, j) => mix(v, end[j], t));
    p[1] += Math.sin(Math.PI * e) * 0.12;
    tmpO.position.set(...p); tmpO.lookAt(...pose.pos); qOut.copy(qFlat).slerp(tmpO.quaternion, smoother(e));
    const segW = (sg.u1 - sg.u0) * PAPER_ASPECT;
    const shrink = smoother(lin(f, G.release - 6, G.release + 6)); // it becomes a node of the graph
    const sx = mix(segW, 0.34, smoother(e)) * mix(1, 0.06, shrink), sy = mix(0.028, 0.074, smoother(e)) * mix(1, 0.3, shrink);
    mats[mi].opacity = lin(f, G.lift - 1, G.lift + 3) * (1 - lin(f, G.release + 2, G.release + 8));
    return (
      <mesh key={k} position={p} quaternion={qOut.clone()} scale={[sx, sy, 1]} material={mats[mi]} renderOrder={8}>
        <planeGeometry args={[1, 1]} />
      </mesh>
    );
  });
};

// highlights on every other page of the field, as small marks in the three colours
const speckVert = /* glsl */ `
attribute vec3 aCol; attribute vec2 aT;
uniform float uF; uniform float uScale; uniform float uDpr;
varying vec3 vCol; varying float vA;
void main(){
  vec4 mv = modelViewMatrix * vec4(position, 1.);
  float a = clamp((uF - aT.x) / 8., 0., 1.) * (1. - clamp((uF - aT.y) / 16., 0., 1.));
  gl_PointSize = clamp(uScale / max(.1, -mv.z), 2.2, 7.) * uDpr * (.5 + .5 * a);
  gl_Position = projectionMatrix * mv;
  vCol = aCol; vA = a * (1. - smoothstep(70., 125., -mv.z));
}`;
const speckFrag = /* glsl */ `
varying vec3 vCol; varying float vA;
void main(){ float r = length(gl_PointCoord * 2. - 1.); float aa = fwidth(r) * 1.4; float a = (1. - smoothstep(1. - aa, 1., r)) * vA;
  if (a < .01) discard; gl_FragColor = vec4(vCol, a); }`;
const Specks = ({f}) => {
  const {geo, mat} = useMemo(() => {
    const pts = [], cols = [], ts = [];
    const pal = [C.gold, C.rose, C.teal].map((h) => new THREE.Color(h));
    CELLS.forEach((c, k) => {
      if (c.wall >= 0 || c.hero) return; // those pages show their real pieces
      for (let s = 0; s < 3; s++) {
        pts.push(c.x + (hash(k * 7.1 + s) - 0.5) * 0.5, 0.09, c.z + (hash(k * 9.3 + s) - 0.5) * 0.75);
        const col = pal[s]; cols.push(col.r, col.g, col.b);
        ts.push(speckAt(c.r) + hash(k * 3.7 + s) * 8, G.release + 20 + c.r * 1.2);
      }
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    g.setAttribute('aCol', new THREE.Float32BufferAttribute(cols, 3));
    g.setAttribute('aT', new THREE.Float32BufferAttribute(ts, 2));
    const m = new THREE.ShaderMaterial({vertexShader: speckVert, fragmentShader: speckFrag, transparent: true, depthWrite: false,
      uniforms: {uF: {value: 0}, uScale: {value: 260}, uDpr: {value: 1}}});
    return {geo: g, mat: m};
  }, []);
  const {gl} = useThree();
  mat.uniforms.uF.value = f; mat.uniforms.uDpr.value = gl.getPixelRatio();
  useLayoutEffect(() => () => { geo.dispose(); mat.dispose(); }, [geo, mat]);
  return <points geometry={geo} material={mat} frustumCulled={false} />;
};

const IncomingPapers = ({f}) => (
  <PaperField count={incoming.length} variant={(k) => incoming[k].v} fog={[20, 95]} bright={0.8}
    layout={(k, o) => {
      const q = incoming[k], t0 = q.t - q.pre;
      if (f < t0 || f > q.t + FADE) { o.alpha = 0; return; }
      const {u, p} = pageAt(k, f), turn = clamp(u / U_BREAK), e = turn * turn * (3 - 2 * turn);
      o.x = p[0]; o.y = p[1]; o.z = p[2];
      o.rx = mix(q.spin[0], FACE[0], e); o.ry = mix(q.spin[1], FACE[1], e); o.rz = q.spin[2] * (1 - e);
      o.s = mix(1.6, 0.95, e) * (1 - 0.3 * lin(f, q.t, q.t + FADE));
      o.alpha = lin(f, t0, t0 + 5) * (1 - lin(f, q.t + 1, q.t + FADE));
    }} />
);

const Scene3D = ({f}) => {
  const pose = genesisPose(f);
  const buffers = useGraphBuffers({graph: EXT, ...GEN_GRAPH, key: 'genesis-v1', edgeDelay: 8});
  return (
    <>
      <color attach="background" args={[C.bg]} />
      <Rig pose={pose} />
      {f < G.release + 140 && <Field f={f} />}
      {f < G.release + 40 && <HeroPage f={f} />}
      <Chips f={f} pose={pose} />
      {f >= G.specks - 2 && f < G.release + 150 && <Specks f={f} />}
      {f >= STREAM[0] - 40 && <IncomingPapers f={f} />}
      <Graph buffers={buffers} f={f} rotY={rotY(f)} position={GPc} fly={60} scale={320} grow={26} onPage={1}
        pulse={0.5 * lin(f, G.living - 20, G.living + 30)} trails={f > G.living ? 0.8 : 0}
        bridge={0.7 * Math.min(lin(f, 720, 760), 1 - lin(f, 840, 890))} fog={[30, 120]} />
      <Post bloom={0} threshold={0.9} smoothing={0.15} radius={0.4} vignette={0} grain={0.02} />
    </>
  );
};

const COL = {x: 1150, width: 700, size: 60};
export const Genesis = () => {
  const f = useCurrentFrame();
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <ThreeCanvas width={width} height={height} camera={{fov: 36, position: [0, 3, 0]}} gl={{antialias: false, powerPreference: 'high-performance'}}>
        <Scene3D f={f} />
      </ThreeCanvas>
      <Block f={f} at={G.line1} until={118} x={1060} width={780} size={60} weight={500} lineDelay={10}
        lines={['For 360 years,', 'the paper has been', "science's **unit of record.**"]} />
      <Block f={f} at={G.line2} until={G.dive + 10} x={0} width={1920} align="center" y={120} anchor="top" size={60} weight={500}
        lines={['Today, **millions a year.**']} />
      <Block f={f} at={G.line3} until={G.lift - 6} {...COL}
        lines={[`[[Findings|${C.gold}|8]], [[methods|${C.rose}|14]]`, `and [[context|${C.teal}|20]] are`, '**buried in prose.**']} />
      <Block f={f} at={G.line4} until={G.living - 30} {...COL} lineAt={[G.line4, G.line4b, G.line4b + 6]}
        lines={['AI can now extract them', 'and connect them', '**across papers.**']} />
      <Block f={f} at={G.living + 6} until={G.end + 30} {...COL} size={100} weight={600} lh={1.02} tracking={-0.04} stagger={2.4} lineDelay={7}
        lines={['A **living**', 'knowledge', 'graph.']} />
    </AbsoluteFill>
  );
};
