import React, {useMemo, useLayoutEffect} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import * as THREE from 'three';
import {PaperField} from '../three/PaperField';
import {Post} from '../three/Post';
import {Rig, project} from '../three/rig';
import {C, SPACE, MONO} from '../lib/theme';
import {band, clamp, eio, eo3, hash, lin, mix, smooth} from '../lib/ease';
import {sp, springT, SPR} from '../lib/spring';
import {PAPER_ASPECT, paperAtlas, reviewPage, journalPage, ATLAS_COLS, ATLAS_ROWS} from '../lib/textures';
import {Block} from '../ui/Type';

// ACT I — the problem, as one continuous camera move to the right. 1665: the first journals. For centuries papers trickle
// in, then the pile explodes while the camera pulls back to take in its height; one paper flies out of it. Findings,
// methods and context are buried in prose, so patterns across studies remain implicit; reviews and meta-analyses
// document some of these patterns, but they take months and quickly become outdated; finding every
// relevant study means sifting through thousands; and every reader starts again. The type lives in a column on the right, the picture on the left.
// Local frames (15 = 1 beat, 60 = 1 bar).
export const A = {era: 88, pick: 304, prose: 376, links: 466, synth: 556, dated: 656, search: 750, scratch: 880, end: 1020};
export const SEGCOL = {finding: C.gold, method: C.rose, context: C.teal};
const COL = {x: 1150, w: 700};
const SHADOW = '0 0 5px rgba(0,0,0,0.85), 0 0 16px rgba(0,0,0,0.8), 0 0 40px rgba(0,0,0,0.65)';

// ---- time → space: the counter runs 1665 → 1900 → 2026; the camera accelerates along the pile, then glides on --------
const Y0 = 92, YM = 172, Y1 = 300;
const frameOfYear = (y) => (y <= 1900 ? Y0 + (YM - Y0) * Math.pow(Math.max(0, (y - 1665) / 235), 1 / 1.6) : YM + (Y1 - YM) * Math.pow((y - 1900) / 126, 1 / 1.15));
const yearU = (f) => (f <= Y0 ? 1665 : f <= YM ? 1665 + 235 * Math.pow((f - Y0) / (YM - Y0), 1.6) : 1900 + 126 * Math.pow((f - YM) / (Y1 - YM), 1.15));
const PILE_LEN = 48, PX = 1.6, GLIDE = 72;
const VEND = (PILE_LEN * PX) / (Y1 - Y0); // speed at 2026 (units per frame)
const frontX = (f) => {
  if (f <= Y0) return 0;
  if (f <= Y1) return PILE_LEN * Math.pow((f - Y0) / (Y1 - Y0), PX);
  const t = Math.min(f - Y1, GLIDE);
  return PILE_LEN + VEND * t - (VEND * t * t) / (2 * GLIDE);
};
const HX = PILE_LEN + (VEND * GLIDE) / 2; // where the glide comes to rest

// ---- the pile: every decade a heap of stacks, lumpy and uneven, growing as its years pass --------------------------
const COLS = 37;
const colN = Array.from({length: COLS}, (_, c) => Math.max(1, Math.round(1.4 * Math.exp(0.19 * c))));
const XC = Array.from({length: COLS + 1}, (_, c) => frontX(frameOfYear(1665 + 10 * c)));
const THICK = 0.011, PW = PAPER_ASPECT * 0.9, PD = 0.9;
const STK = [];
for (let c = 1; c < COLS; c++) {
  const x0 = XC[c], w = Math.max(0.42, XC[c + 1] - XC[c]);
  const H = 0.0143 * Math.exp(0.19 * c);
  const rows = c < 16 ? 1 : c < 24 ? 2 : c < 30 ? 3 : 4;
  const cols = Math.max(1, Math.round(w / 0.78));
  for (let r = 0; r < rows; r++) for (let k = 0; k < cols; k++) {
    const s = c * 31 + r * 7 + k * 3;
    if (r > 0 && hash(s * 1.3) < 0.2) continue;
    const hf = (0.5 + 0.75 * hash(s * 2.9)) * [0.72, 1, 1.18, 1.3][r];
    const x = x0 + ((k + 0.5) / cols) * w + (hash(s * 3.7) - 0.5) * 0.22 * Math.min(1, w / 0.78);
    const a0 = clamp((x - x0) / w) * 0.6 + hash(s * 7.1) * 0.08;
    STK.push({c, x, z: -0.25 - r * 0.98 + (hash(s * 4.1) - 0.5) * 0.3,
      yaw: (hash(s * 5.3) - 0.5) * 0.55, lean: c > 27 ? (hash(s * 6.7) - 0.5) * 0.05 : 0, h: Math.max(THICK, H * hf),
      a0, a1: a0 + 0.34 + hash(s * 8.3) * 0.08, v: s % (ATLAS_COLS * ATLAS_ROWS)});
  }
}
const fillOf = (q, f) => clamp((yearU(f) - (1665 + 10 * q.c + 10 * q.a0)) / (10 * (q.a1 - q.a0)));
const stackH = (q, f) => Math.round((q.h * fillOf(q, f)) / THICK) * THICK;
// each stack is a few loose slabs, each slightly offset and turned: a hand-made pile rather than a block
const SLAB = [];
STK.forEach((q, qi) => { q.i = qi; });
STK.forEach((q, qi) => {
  const n = Math.max(1, Math.min(22, Math.ceil(q.h / 0.22)));
  for (let j = 0; j < n; j++) {
    const s = qi * 37 + j * 11;
    SLAB.push({q, j, n, dx: (hash(s * 1.1) - 0.5) * 0.07, dz: (hash(s * 1.7) - 0.5) * 0.07, yaw: (hash(s * 2.3) - 0.5) * 0.16,
      w: 1 + (hash(s * 2.9) - 0.5) * 0.05, tone: 0.9 + hash(s * 3.3) * 0.12, v: (q.v + j) % (ATLAS_COLS * ATLAS_ROWS)});
  }
});

const stackVert = /* glsl */ `
attribute float aVar; attribute float aTone;
varying vec3 vN; varying vec3 vW; varying float vDepth; varying vec2 vUv; varying float vVar; varying float vTone;
void main(){
  vec4 w = modelMatrix * instanceMatrix * vec4(position, 1.);
  vW = w.xyz; vUv = uv; vVar = aVar; vTone = aTone;
  vN = normalize(mat3(modelMatrix) * mat3(instanceMatrix) * normal);
  vec4 mv = viewMatrix * w;
  vDepth = -mv.z;
  gl_Position = projectionMatrix * mv;
}`;
// solid stacks: the top sheet is a page, the sides show the edges of the sheets (lines fade before they can alias)
const stackFrag = /* glsl */ `
uniform float uThick; uniform float uAlpha; uniform vec3 uPaper; uniform vec3 uBg; uniform vec2 uFog; uniform sampler2D uMap; uniform vec2 uGrid;
varying vec3 vN; varying vec3 vW; varying float vDepth; varying vec2 vUv; varying float vVar; varying float vTone;
float h11(float x){ return fract(sin(x * 91.7) * 43758.5); }
void main(){
  vec3 n = normalize(vN);
  float light = .4 + .6 * max(0., dot(n, normalize(vec3(-.45, .8, .55))));
  vec3 c = uPaper * light * vTone * mix(vec3(1.), vec3(1.02, .99, .94), h11(vVar * 7.1 + vTone * 13.));
  if (n.y > .5) {
    float col = mod(vVar, uGrid.x), row = floor(vVar / uGrid.x);
    c = texture2D(uMap, vec2((vUv.x + col) / uGrid.x, (vUv.y + (uGrid.y - 1. - row)) / uGrid.y)).rgb * .8;
  } else if (abs(n.y) < .5) {
    float s = vW.y / uThick;
    float w = fwidth(s);
    float g = abs(fract(s) - .5) * 2.;
    float gap = smoothstep(.7 - w, .7 + w, g);
    float sheet = .9 + .1 * h11(floor(s) + floor(vW.x * 3.1) * 17.);
    c *= mix(.9, (1. - gap * .4) * sheet, 1. - smoothstep(.35, .9, w));
    c *= .92 + .08 * h11(floor(vW.y / .05) + vTone * 91.); // reams: bands of slightly different stock
  }
  c = mix(c, uBg, smoothstep(uFog.x, uFog.y, vDepth));
  gl_FragColor = vec4(mix(uBg, c, uAlpha), 1.);
}`;
const m4 = new THREE.Matrix4(), qt = new THREE.Quaternion(), eu = new THREE.Euler(), pv = new THREE.Vector3(), sv = new THREE.Vector3();
const Stacks = ({f, alpha = 1}) => {
  const {mesh, mat, geo} = useMemo(() => {
    const g = new THREE.BoxGeometry(1, 1, 1);
    const vars = new Float32Array(SLAB.length), tones = new Float32Array(SLAB.length);
    SLAB.forEach((b, i) => { vars[i] = b.v; tones[i] = b.tone; });
    g.setAttribute('aVar', new THREE.InstancedBufferAttribute(vars, 1));
    g.setAttribute('aTone', new THREE.InstancedBufferAttribute(tones, 1));
    const m = new THREE.ShaderMaterial({vertexShader: stackVert, fragmentShader: stackFrag,
      uniforms: {uThick: {value: THICK}, uAlpha: {value: 1}, uPaper: {value: new THREE.Color('#e7e3da')}, uBg: {value: new THREE.Color(C.bg)},
        uFog: {value: new THREE.Vector2(26, 70)}, uMap: {value: paperAtlas()}, uGrid: {value: new THREE.Vector2(ATLAS_COLS, ATLAS_ROWS)}}});
    const ms = new THREE.InstancedMesh(g, m, SLAB.length);
    ms.frustumCulled = false;
    return {mesh: ms, mat: m, geo: g};
  }, []);
  const hs = STK.map((q) => stackH(q, f));
  SLAB.forEach((b, i) => {
    const {q} = b, H = hs[q.i], seg = q.h / b.n;
    const h = clamp(H - b.j * seg, 0, seg);
    if (h <= 0) { sv.set(0, 0, 0); pv.set(0, -500, 0); m4.compose(pv, qt, sv); mesh.setMatrixAt(i, m4); return; }
    eu.set(q.lean, q.yaw + b.yaw, 0);
    qt.setFromEuler(eu);
    const y0 = b.j * seg;
    pv.set(q.x + b.dx, y0 + h / 2, q.z + b.dz - Math.sin(q.lean) * y0);
    sv.set(PW * b.w, h, PD * b.w);
    m4.compose(pv, qt, sv);
    mesh.setMatrixAt(i, m4);
  });
  mesh.instanceMatrix.needsUpdate = true;
  mat.uniforms.uAlpha.value = alpha;
  useLayoutEffect(() => () => { geo.dispose(); mat.dispose(); }, [geo, mat]);
  return <primitive object={mesh} />;
};

// papers raining onto the stacks: a trickle for centuries, then a downpour
const byDecade = Array.from({length: COLS}, (_, c) => STK.filter((q) => q.c === c));
const RAIN = [];
for (let c = 1; c < COLS; c++) {
  const R = Math.min(colN[c], c < 12 ? 1 : c < 25 ? 1 + Math.round((c - 12) * 0.25) : 2 + Math.round(c * 1.15)); // a trickle for centuries, a downpour at the end
  for (let j = 0; j < R; j++) {
    const n = RAIN.length, q = byDecade[c][Math.floor(hash(n * 1.9) * byDecade[c].length)];
    const t = frameOfYear(1665 + 10 * c + 10 * q.a0 + 10 * (q.a1 - q.a0) * ((j + 0.5) / R));
    const early = c < 12; // the first sheets fall gently, behind the pile, away from the lens
    RAIN.push({q, t, fall: 12 + hash(n * 1.3) * 10, hgt: early ? 0.8 + hash(n * 5.9) * 1.6 : 1.2 + hash(n * 5.9) * 3, dx: early ? -0.2 - hash(n * 2.1) * 0.8 : -1.4 - hash(n * 2.1) * 3,
      dz: early ? -0.3 - hash(n * 4.3) * 1.2 : (hash(n * 4.3) - 0.5) * 2.4,
      rx: (hash(n * 6.1) - 0.5) * 5, ry: (hash(n * 7.7) - 0.5) * 6, rz: (hash(n * 8.3) - 0.5) * 5, v: n % 12});
  }
}
const Rain = ({f}) => (
  <PaperField count={RAIN.length} variant={(j) => RAIN[j].v} fog={[26, 70]} bright={0.8}
    layout={(j, o) => {
      const r = RAIN[j], t0 = r.t - r.fall;
      if (f < t0 || f > r.t + 3) { o.alpha = 0; return; }
      const e = Math.pow(clamp((f - t0) / r.fall), 2);
      const land = stackH(r.q, r.t) + 0.012;
      o.x = r.q.x + r.dx * (1 - e); o.y = land + r.hgt * (1 - e); o.z = r.q.z + r.dz * (1 - e);
      o.rx = mix(r.rx, -Math.PI / 2, e); o.ry = r.ry * (1 - e); o.rz = mix(r.rz, r.q.yaw, e); o.s = 0.9;
      o.alpha = lin(f, t0, t0 + 4) * (1 - lin(f, r.t, r.t + 3));
    }} />
);
// sheets that slid off: loose papers on the floor in front of the heaps, more every decade
const SPILL = [];
for (let c = 17; c < COLS; c++) {
  const n = Math.round((c - 16) * 1.25);
  for (let j = 0; j < n; j++) {
    const k = SPILL.length, w = XC[c + 1] - XC[c];
    SPILL.push({x: XC[c] + hash(k * 1.7) * w, z: 0.45 + Math.pow(hash(k * 2.3), 1.4) * 1.9, yaw: (hash(k * 3.1) - 0.5) * 3,
      tilt: (hash(k * 4.9) - 0.5) * 0.12, t: frameOfYear(1665 + 10 * c + 10 * hash(k * 5.7)) + 4, v: (k * 5 + 2) % 12, y: 0.004 + hash(k * 6.1) * 0.02});
  }
}
const Spill = ({f}) => (
  <PaperField count={SPILL.length} variant={(j) => SPILL[j].v} fog={[26, 70]} bright={0.72}
    layout={(j, o) => {
      const q = SPILL[j];
      if (f < q.t) { o.alpha = 0; return; }
      const e = clamp(sp(f, q.t, 'ui'), 0, 1.04);
      o.x = q.x; o.y = q.y + (1 - clamp(e)) * 0.5; o.z = q.z - (1 - clamp(e)) * 0.4;
      o.rx = -Math.PI / 2 + q.tilt; o.rz = q.yaw + (1 - e) * 0.6; o.s = 0.9;
      o.alpha = clamp(e * 3);
    }} />
);

// the pages we see up close are drawn at full resolution. The first paper and the one we read are one-offs that appear
// nowhere else in the pile (the first with a blue and gold bar chart, the one we read with grey bars, so the highlights
// carry the colour); its neighbours are atlas pages
const PAGE_FIRST = {seed: 9025, titleLines: 3, figure: {kind: 0, colors: ['#90baff', '#f1b74b']}, rule: '#90baff'};
const PAGE_HERO = {seed: 9101, titleLines: 2, figure: {kind: 0, colors: ['#7d8388', '#b3b8bb']}, rule: '#8f969a'};
const PAGE_NB = [0, 7, 4, 10];
const heroPage = () => journalPage(PAGE_HERO, 1400);
const nbPage = (k) => journalPage(PAGE_NB[k], 1000);

// the first paper: it fades in, already written, then lies down as the first sheet of the pile
const PAGE0 = [0.22, 1.42, 0];
const firstPose = (f) => {
  const fall = sp(f, A.era + 2, 'heavy');
  const pos = PAGE0.map((v, k) => mix(v, [0.22, 0.012, -0.25][k], fall));
  pos[1] += Math.sin(Math.PI * clamp(fall)) * 0.25;
  return {pos, rot: [mix(0, -Math.PI / 2, fall), mix(-0.14 + f * 0.0006, 0, fall), 0], s: mix(1, 0.9, fall)};
};
const FirstPage = ({f}) => {
  const page = journalPage(PAGE_FIRST, 1400);
  const {pos, rot, s} = firstPose(f);
  const a = eio(lin(f, 2, 66));
  return (
    <group position={pos} rotation={rot} scale={s * mix(0.97, 1, a)}>
      <PaperField count={1} map={page.tex} cols={1} rows={1} variant={() => 0} fog={[80, 400]} bright={0.84} layout={(i, o) => { o.alpha = a; }} />
    </group>
  );
};

// the storm reaches the lens: papers rush past the camera in the last decades (kept out of the type column)
const STRAYS = Array.from({length: 420}, (_, i) => {
  const lat = (hash(i * 3.1) < 0.72 ? -1 : 1) * (1.2 + hash(i * 3.9) * 6.5);
  let up = (hash(i * 4.7) - 0.35) * 5.5;
  if (lat > 0) up = -3.2 - hash(i * 5.9) * 2.4;
  return {s: 238 + Math.pow(hash(i * 1.7), 0.55) * 60, dur: 11 + hash(i * 2.3) * 10, lat, up, ahead: 15 + hash(i * 5.3) * 16,
    rx: (hash(i * 6.7) - 0.5) * 8, ry: (hash(i * 7.9) - 0.5) * 8, rz: (hash(i * 8.9) - 0.5) * 8, v: (i * 5) % 12};
});
const basisCache = new Map();
const basisAt = (t) => {
  const key = Math.round(t * 2);
  if (!basisCache.has(key)) {
    const pose = cameraPose(key / 2);
    const P = new THREE.Vector3(...pose.pos), L = new THREE.Vector3(...pose.look);
    const Fw = L.clone().sub(P).normalize();
    const Rt = new THREE.Vector3().crossVectors(Fw, new THREE.Vector3(0, 1, 0)).normalize();
    basisCache.set(key, {P, Fw, Rt, Up: new THREE.Vector3().crossVectors(Rt, Fw)});
  }
  return basisCache.get(key);
};
const Strays = ({f}) => (
  <PaperField count={STRAYS.length} variant={(i) => STRAYS[i].v} fog={[40, 160]} bright={0.82}
    layout={(i, o) => {
      const q = STRAYS[i];
      if (f < q.s || f > q.s + q.dur) { o.alpha = 0; return; }
      const u = (f - q.s) / q.dur;
      const {P, Fw, Rt, Up} = basisAt(q.s);
      const d = q.ahead * (1 - u) - 7 * u;
      o.x = P.x + Fw.x * d + Rt.x * q.lat + Up.x * q.up; o.y = P.y + Fw.y * d + Rt.y * q.lat + Up.y * q.up; o.z = P.z + Fw.z * d + Rt.z * q.lat + Up.z * q.up;
      o.rx = q.rx * u; o.ry = q.ry * u; o.rz = q.rz * u; o.s = 0.9;
      o.alpha = lin(u, 0, 0.18) * (1 - lin(u, 0.8, 1));
    }} />
);

// ---- the paper, its neighbours, the review, the search -------------------------------------------------------------
// After 2026 the camera glides on at the height it pulled back to and the paper flies to it, so the rest of the act
// plays out up here, each station to the right of the last.
const PC = [HX - 0.3, 5.6, 14.2];
const localToWorld = (pos, rot, s, u, v) => {
  const p = new THREE.Vector3((u - 0.5) * PAPER_ASPECT * s, (v - 0.5) * s, 0.004).applyEuler(new THREE.Euler(...rot));
  return [p.x + pos[0], p.y + pos[1], p.z + pos[2]];
};
const WC = 18, WR = 13, WSX = 0.95, WSY = 1.24, WALL_S = 0.86;
const RS = [PC[0] + 4.8, PC[1] - 0.6, PC[2] + 0.9]; // where the review is made
const W1 = [RS[0] + 11.2, PC[1], RS[2] - 4.6];      // the search results
const WALL_R = W1[0] + ((WC - 1) / 2) * WSX + 0.35;
const wallPos = (i) => [W1[0] + ((i % WC) - (WC - 1) / 2) * WSX, W1[1] + ((WR - 1) / 2 - Math.floor(i / WC)) * WSY, W1[2] + (hash(i * 9.7) - 0.5) * 0.12];
const RELEVANT = (i) => hash(i * 9.31 + 4) < 0.1;
const SCAN_ORDER = [];
for (let r = 2; r <= 10; r++) for (let c = 8; c < WC; c++) SCAN_ORDER.push(r * WC + c);
const RANK = new Map(SCAN_ORDER.map((i, k) => [i, k]));
const SCAN1 = A.search + 60, SCAN2 = A.scratch + 34, RATE = 1.6;
const scanState = (i, f, start) => {
  const rk = RANK.get(i);
  if (rk === undefined || f < start + rk * RATE) return null;
  const since = f - (start + rk * RATE);
  return {flash: Math.exp(-since * 0.35), rel: RELEVANT(i), since};
};
// the first reader's screening, wiped column by column when the next reader starts from scratch
const wipeAt = (i, f) => lin(f, A.scratch + 4 + (WC - 1 - (i % WC)) * 0.9, A.scratch + 10 + (WC - 1 - (i % WC)) * 0.9);
// reading a paper: it comes forward as it is read; relevant ones stay forward with a teal edge, the rest drop back and dim
// (call after the paper's own position and size are set)
const markWall = (i, f, o) => {
  const read = (st, keep) => {
    const now = Math.exp(-st.since * 0.16), settle = clamp(st.since / 8);
    o.z += (0.6 * now + (st.rel ? 0.32 : -0.22) * settle) * keep;
    o.s *= 1 + (0.12 * now + (st.rel ? 0.05 : 0) * settle) * keep;
    o.edge = ((st.rel ? 1.1 : 0) * settle + st.flash * 0.6) * keep;
    o.age = (st.rel ? 0 : settle * 0.62) * keep;
  };
  const s2 = scanState(i, f, SCAN2);
  if (s2) { read(s2, 1); return; }
  const s1 = scanState(i, f, SCAN1);
  if (s1) read(s1, 1 - wipeAt(i, f));
};
const pileSlot = (k) => [RS[0] + (hash(k * 3.3) - 0.5) * 0.14, RS[1] + k * 0.013, RS[2] + (hash(k * 5.1) - 0.5) * 0.14];
const MERGE = A.synth + 58, REVIEW = A.synth + 64;

// highlighter marks: the page is tinted underneath the words (multiply), so the text stays crisp through them
const Highlights = ({f, page, pos, rot, s, times, fade = 1}) => {
  const mats = useMemo(() => page.segs.map((sg) => new THREE.MeshBasicMaterial({color: new THREE.Color(SEGCOL[sg.type]).lerp(new THREE.Color('#ffffff'), 0.12),
    transparent: true, opacity: 0, depthWrite: false, blending: THREE.MultiplyBlending, premultipliedAlpha: true})), [page]);
  return (
    <group position={pos} rotation={rot} scale={s}>
      {page.segs.map((sg, k) => {
        const t0 = times[sg.type] + (k >= 3 ? 3 : 0);
        mats[k].opacity = eo3(lin(f, t0, t0 + 10)) * fade * 0.9;
        const w = (sg.u1 - sg.u0) * PAPER_ASPECT, h = sg.v1 - sg.v0;
        const grow = clamp(springT((f - t0) / 30, SPR.snappy), 0, 1.05);
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

// papers that go into the review: they leave for the pile one after another and land flat
const toPile = (pose, f, k, t0) => {
  const g = clamp(sp(f, t0, 'ui'), 0, 1.03);
  if (g <= 0) return pose;
  const ps = pileSlot(k);
  const pos = pose.pos.map((v, j) => mix(v, ps[j], g));
  pos[1] += Math.sin(Math.PI * clamp(g)) * 0.7;
  return {pos, rot: [mix(pose.rot[0], -Math.PI / 2, clamp(g)), pose.rot[1] * (1 - clamp(g)), mix(pose.rot[2], (hash(k * 7.7) - 0.5) * 0.3, clamp(g))], s: mix(pose.s, WALL_S, g)};
};

// one paper flies out of the pile, is read up close, then goes into a review
const PICK = STK.filter((q) => q.c === 35 && q.z > -0.8).sort((a, b) => Math.abs(a.h - 4) - Math.abs(b.h - 4))[0];
const FLY = {stiffness: 9, damping: 6}, HERO_T = Y1 - 2;
const heroPose = (f) => {
  const t = sp(f, HERO_T, FLY);
  const from = [PICK.x, PICK.h + 0.03, PICK.z];
  const pos = from.map((v, k) => mix(v, PC[k], t));
  pos[1] += Math.sin(Math.PI * clamp(t)) * 0.45;
  const pose = {pos, rot: [mix(-Math.PI / 2, 0, t), mix(PICK.yaw, 0, t) + Math.sin(Math.PI * clamp(t)) * 0.5, mix(0.2, 0, t)], s: mix(0.9, 1, t)};
  return toPile(pose, f, 0, A.synth + 2);
};
const HeroPage = ({f}) => {
  if (f < HERO_T - 1 || f > MERGE + 10) return null;
  const page = heroPage();
  const {pos, rot, s} = heroPose(f);
  const dim = band(f, A.links + 20, A.links + 34, A.synth - 10, A.synth);
  return (
    <>
      <group position={pos} rotation={rot} scale={s}>
        <PaperField count={1} map={page.tex} cols={1} rows={1} variant={() => 0} fog={[80, 400]} bright={mix(0.86, 0.6, dim)}
          layout={(i, o) => { o.alpha = 1 - lin(f, MERGE, MERGE + 8); }} />
      </group>
      <Highlights f={f} page={page} pos={pos} rot={rot} s={s} times={{finding: A.prose + 6, method: A.prose + 12, context: A.prose + 18}} fade={1 - lin(f, A.synth - 8, A.synth + 4)} />
    </>
  );
};
const NB = [
  {off: [-1.42, 0.62, -0.7], ry: 0.4, from: [-7, 3.4, -4]},
  {off: [1.28, 0.7, -0.9], ry: -0.36, from: [2.5, 6.5, -6]},
  {off: [-1.3, -0.72, -0.5], ry: 0.32, from: [-7, -3.8, -3]},
  {off: [1.32, -0.64, -0.45], ry: -0.44, from: [2.5, -6.5, -5]},
];
NB.forEach((n) => { n.pos = PC.map((v, j) => v + n.off[j]); n.start = PC.map((v, j) => v + n.from[j]); });
const nbPose = (n, f) => {
  const k = NB.indexOf(n);
  const t = sp(f, A.links - 4 + k * 4, 'soft');
  const pos = n.start.map((v, j) => mix(v, n.pos[j], t));
  const rot = [mix(n.from[1] > 0 ? 0.5 : -0.5, 0, t), mix(n.ry * 2.6, n.ry, t), mix(0.3, 0, t)];
  return toPile({pos, rot, s: mix(0.9, 0.85, t)}, f, 1 + k, A.synth + 5 + k * 2.4);
};
const Neighbours = ({f}) => {
  if (f < A.links - 6 || f > MERGE + 10) return null;
  const dim = band(f, A.links + 20, A.links + 34, A.synth - 10, A.synth);
  return NB.map((n, k) => {
    const page = nbPage(k);
    const {pos, rot, s} = nbPose(n, f);
    const t0 = A.links + 14 + k * 4;
    return (
      <React.Fragment key={k}>
        <group position={pos} rotation={rot} scale={s}>
          <PaperField count={1} map={page.tex} cols={1} rows={1} variant={() => 0} fog={[80, 400]} bright={mix(0.82, 0.6, dim)}
            layout={(i, o) => { o.alpha = 1 - lin(f, MERGE, MERGE + 8); }} />
        </group>
        <Highlights f={f} page={page} pos={pos} rot={rot} s={s} times={{finding: t0, method: t0 + 2, context: t0 + 4}} fade={1 - lin(f, A.synth - 8, A.synth + 4)} />
      </React.Fragment>
    );
  });
};
// more related studies, from all over the literature, onto the same pile
const GATHER = Array.from({length: 20}, (_, k) => ({from: [RS[0] - 4 - hash(k * 2.1) * 6, RS[1] + (k % 2 ? 1 : -1) * (3 + hash(k * 3.7) * 3), RS[2] - 1 - hash(k * 5.3) * 3]}));
const Gather = ({f}) => (
  <PaperField count={GATHER.length} variant={(k) => (k * 5 + 3) % 12} fog={[20, 80]} bright={0.7}
    layout={(k, o) => {
      const t0 = A.synth + 14 + k * 1.9;
      if (f < t0 || f > MERGE + 10) { o.alpha = 0; return; }
      const g = clamp(sp(f, t0, 'ui'), 0, 1.03);
      const ps = pileSlot(5 + k), fr = GATHER[k].from;
      o.x = mix(fr[0], ps[0], g); o.y = mix(fr[1], ps[1], g) + Math.sin(Math.PI * clamp(g)) * 0.5; o.z = mix(fr[2], ps[2], g);
      o.rx = mix((hash(k * 1.9) - 0.5) * 1.2, -Math.PI / 2, clamp(g)); o.rz = mix(hash(k * 2.9) - 0.5, (hash(k * 7.1) - 0.5) * 0.3, clamp(g)); o.s = WALL_S;
      o.alpha = lin(f, t0, t0 + 4) * (1 - lin(f, MERGE, MERGE + 8));
    }} />
);

// the review: bound from the pile into a thicker document with a gold spine — a different kind of paper, still a paper
const BOOK = {w: PAPER_ASPECT * 1.05, h: 1.05, d: 0.075};
const reviewPose = (f) => {
  const t = sp(f, REVIEW, 'heavy');
  return {pos: [RS[0], RS[1] + mix(0.05, 0.6, t), RS[2] + 0.05], rot: [mix(-Math.PI / 2, -0.04, t), mix(0, 0.26, t), 0], t};
};
const reviewAge = (f) => eio(lin(f, A.dated + 22, A.dated + 92)) * 0.95;
const Review = ({f}) => {
  const mats = useMemo(() => ({
    block: new THREE.MeshBasicMaterial({color: new THREE.Color('#cfc9bd')}),
    spine: new THREE.MeshBasicMaterial({color: new THREE.Color(C.gold)}),
  }), []);
  if (f < MERGE - 2 || f > A.search + 70) return null;
  const {pos, rot, t} = reviewPose(f);
  const age = reviewAge(f);
  const grey = new THREE.Color('#6b6862');
  mats.block.color.set('#cfc9bd').lerp(grey, age * 0.8).multiplyScalar(0.8);
  mats.spine.color.set(C.gold).multiplyScalar(0.92).lerp(grey, age * 0.9);
  const a = lin(f, MERGE - 2, MERGE + 4);
  return (
    <group position={pos} rotation={rot} scale={mix(0.9, 1, clamp(t))}>
      <mesh position={[0, 0, -BOOK.d / 2]} material={mats.block}><boxGeometry args={[BOOK.w * 0.985, BOOK.h * 0.985, BOOK.d]} /></mesh>
      <mesh position={[-BOOK.w / 2, 0, -BOOK.d / 2 + 0.002]} material={mats.spine}><boxGeometry args={[0.03, BOOK.h, BOOK.d + 0.006]} /></mesh>
      <group scale={1.05}>
        <PaperField count={1} map={reviewPage()} cols={1} rows={1} variant={() => 0} fog={[80, 400]} bright={0.86} glow="#f1b74b" edge="#f1b74b"
          layout={(i, o) => { o.alpha = a; o.age = age; o.edge = (1 - age) * 0.16 * clamp(t); o.z = 0.001; }} />
      </group>
    </group>
  );
};

// soon out of date: the review is dated 2021, and the studies keep landing on the timeline after it
const STACKS = [5, 8, 12, 17, 23];
const NEW = STACKS.flatMap((h, s) => Array.from({length: h}, (_, k) => ({s, k})));
const newT = (i) => A.dated + 16 + Math.pow(i / NEW.length, 0.85) * 72;
const stackX = (s) => RS[0] + 0.95 + s * 0.6;
const W_SLOTS = (() => { // visible slots of the search results, for the new studies to join
  const out = [];
  for (let r = 2; r <= 10; r++) for (let c = 8; c < WC; c++) out.push(r * WC + c);
  return out.sort((a, b) => hash(a * 3.77) - hash(b * 3.77)).slice(0, NEW.length);
})();
const W_SLOT_SET = new Set(W_SLOTS);
const NewStudies = ({f}) => (
  <PaperField count={NEW.length} variant={(i) => (i * 7 + 1) % 12} fog={[30, 200]} bright={0.8}
    layout={(i, o) => {
      const t0 = newT(i);
      if (f < t0) { o.alpha = 0; return; }
      const {s, k} = NEW[i];
      const d = 1 - sp(f, t0, 'pop');
      let p = [stackX(s) + (hash(i * 2.2) - 0.5) * 0.05, RS[1] - 0.04 + k * 0.022 + d * 0.4, RS[2] + (hash(i * 3.3) - 0.5) * 0.05];
      let rot = [-Math.PI / 2, 0, (hash(i * 4.4) - 0.5) * 0.4];
      let sc = 0.72;
      // the search: the new studies are among its results
      const g = clamp(sp(f, A.search + 4 + (i % 23) * 0.9, 'soft'), 0, 1.02);
      if (g > 0) {
        const w = wallPos(W_SLOTS[i]);
        p = p.map((v, k2) => mix(v, w[k2], g)); p[1] += Math.sin(Math.PI * clamp(g)) * 1.2;
        rot = rot.map((v) => v * (1 - clamp(g))); sc = mix(sc, WALL_S, g);
      }
      o.x = p[0]; o.y = p[1]; o.z = p[2]; o.rx = rot[0]; o.ry = rot[1]; o.rz = rot[2]; o.s = sc;
      if (g > 0) markWall(W_SLOTS[i], f, o);
      o.alpha = lin(f, t0, t0 + 3) * (1 - lin(f, A.end - 10, A.end - 2));
      if (g <= 0) o.glow = band(f, t0, t0 + 2, t0 + 4, t0 + 18) * 0.9;
    }} />
);
const Timeline = ({f}) => {
  const mat = useMemo(() => new THREE.MeshBasicMaterial({color: new THREE.Color(C.teal).multiplyScalar(1.05), transparent: true, depthWrite: false}), []);
  const tick = useMemo(() => new THREE.MeshBasicMaterial({color: new THREE.Color(C.gold).multiplyScalar(1.4), transparent: true, depthWrite: false}), []);
  const g = clamp(sp(f, A.dated + 4, 'soft'), 0, 1.02);
  const a = lin(f, A.dated + 2, A.dated + 10) * (1 - lin(f, A.search + 2, A.search + 16));
  mat.opacity = 0.7 * a; tick.opacity = a * (1 - reviewAge(f) * 0.7);
  const L = 4.5 * Math.max(0.001, g);
  return (
    <>
      <mesh position={[RS[0] - 0.6 + L / 2, RS[1] - 0.07, RS[2] + 0.5]} material={mat}><boxGeometry args={[L, 0.012, 0.012]} /></mesh>
      <mesh position={[RS[0], RS[1] - 0.07, RS[2] + 0.52]} material={tick}><boxGeometry args={[0.02, 0.26, 0.02]} /></mesh>
    </>
  );
};
// the search results: the new studies and thousands more, screened one at a time — and again, from zero
const Wall = ({f}) => (
  <PaperField count={WC * WR} variant={(i) => (i * 5 + Math.floor(i / WC) * 3) % 12} fog={[16, 60]} bright={0.62}
    layout={(i, o) => {
      if (W_SLOT_SET.has(i)) { o.alpha = 0; return; }
      const [x, y, z] = wallPos(i);
      const t0 = A.search + 8 + hash(i * 1.37) * 26;
      if (f < t0) { o.alpha = 0; return; }
      const t = clamp(sp(f, t0, 'ui'), 0, 1.05);
      o.x = x; o.y = y; o.z = z - (1 - t) * 3; o.s = WALL_S;
      o.alpha = clamp(t) * (1 - lin(f, A.end - 10, A.end - 2));
      markWall(i, f, o);
    }} />
);

// ---- camera: one move to the right; shots blended by critically damped springs --------------------------------------
const blend = (a, b, w) => ({pos: a.pos.map((v, k) => mix(v, b.pos[k], w)), look: a.look.map((v, k) => mix(v, b.look[k], w)), fov: mix(a.fov, b.fov, w), roll: mix(a.roll, b.roll, w)});
const MOVE = {stiffness: 8, damping: 5.66};
const shots = (f, list) => {
  let cur = list[0].pose(f);
  for (let i = 1; i < list.length; i++) {
    if (f < list[i].t) break;
    cur = blend(cur, list[i].pose(f), springT((f - list[i].t) / 30, list[i].p === 'move' ? MOVE : SPR[list[i].p || 'camera']));
  }
  return cur;
};
const openShot = (f) => ({pos: [PAGE0[0] + 0.5 - f * 0.0008, PAGE0[1] + 0.02, PAGE0[2] + 3.25 - f * 0.002], look: [PAGE0[0] + 0.5 - f * 0.0008, PAGE0[1], PAGE0[2]], fov: 34, roll: 0.006});
// tracking the growth: trailing the front, looking ahead along the pile, pulling back and up so the pile's height fits
const growthCam = (f) => {
  const x = frontX(f), e = smooth(lin(f, Y0, Y1 + 10));
  return {pos: [x - mix(3.0, 11.5, e), mix(0.8, 7.6, e), mix(5.0, 21, e)], look: [x + mix(2.4, 5.6, e), mix(0.12, 5.9, e), -1.1], fov: mix(42, 48, e), roll: mix(0.006, 0.02, e)};
};
const closeShot = (f) => ({pos: [PC[0] + 0.3 + (f - A.prose) * 0.0008, PC[1] - 0.01, PC[2] + 1.95 - lin(f, A.prose, A.links) * 0.1],
  look: [PC[0] + 0.3 + (f - A.prose) * 0.0008, PC[1] - 0.02, PC[2]], fov: 34, roll: 0});
const linksShot = (f) => ({pos: [PC[0] + 1.35 + (f - A.links) * 0.001, PC[1] + 0.1, PC[2] + 5.4], look: [PC[0] + 1.35 + (f - A.links) * 0.001, PC[1], PC[2] - 0.5], fov: 36, roll: 0});
const synthShot = (f) => ({pos: [RS[0] + 0.62 + (f - A.synth) * 0.001, RS[1] + 0.95, RS[2] + 3.7], look: [RS[0] + 0.62 + (f - A.synth) * 0.001, RS[1] + mix(0.2, 0.55, lin(f, REVIEW, REVIEW + 20)), RS[2]], fov: 36, roll: 0});
const datedShot = (f) => ({pos: [RS[0] + 1.55 + (f - A.dated) * 0.0012, RS[1] + 0.85, RS[2] + 5.0], look: [RS[0] + 1.55 + (f - A.dated) * 0.0012, RS[1] + 0.51, RS[2]], fov: 40, roll: 0});
const wallShot = (f) => ({pos: [WALL_R - 0.62 - (f - A.search) * 0.0008, W1[1] + 0.3, W1[2] + 12.6 - lin(f, A.search, A.end) * 1.1], look: [WALL_R - 0.62 - (f - A.search) * 0.0008, W1[1] - 0.1, W1[2]], fov: 40, roll: 0});
function cameraPose(f) {
  return shots(f, [
    {t: 0, pose: openShot},
    {t: A.era + 2, pose: growthCam},
    {t: A.pick, p: 'slow', pose: closeShot},
    {t: A.links - 4, pose: linksShot},
    {t: A.synth + 2, p: 'move', pose: synthShot},
    {t: A.dated + 2, p: 'move', pose: datedShot},
    {t: A.search, pose: wallShot},
  ]);
}

const Scene3D = ({f}) => {
  const pose = cameraPose(f);
  return (
    <>
      <color attach="background" args={[C.bg]} />
      <Rig pose={pose} />
      {f < 230 && <FirstPage f={f} />}
      {f >= A.era && f < A.pick + 80 && <Stacks f={f} />}
      {f >= A.era && f < A.pick + 20 && <Rain f={f} />}
      {f >= 150 && f < A.pick + 80 && <Spill f={f} />}
      {f >= 230 && f < Y1 + 12 && <Strays f={f} />}
      <HeroPage f={f} />
      <Neighbours f={f} />
      {f >= A.synth && f < MERGE + 12 && <Gather f={f} />}
      <Review f={f} />
      {f >= A.dated && <NewStudies f={f} />}
      {f >= A.dated && f < A.search + 20 && <Timeline f={f} />}
      {f >= A.search && <Wall f={f} />}
      <Post bloom={0.35} threshold={0.9} smoothing={0.1} radius={0.35} vignette={0} grain={0.02} />
    </>
  );
};

// ---- overlays ----------------------------------------------------------------------------------------------------
// links reach between related passages of different papers, then fade: nobody records them
const LINKS = [['hero', 'finding', 0, 'finding'], ['hero', 'method', 1, 'method'], [0, 'context', 2, 'context'], [1, 'finding', 3, 'finding'], ['hero', 'context', 3, 'context'], [2, 'method', 0, 'method']];
const segWorld = (who, type, f) => {
  const page = who === 'hero' ? heroPage() : nbPage(who);
  const {pos, rot, s} = who === 'hero' ? heroPose(f) : nbPose(NB[who], f);
  const sg = page.segs.find((q) => q.type === type);
  return localToWorld(pos, rot, s, (sg.u0 + sg.u1) / 2, (sg.v0 + sg.v1) / 2);
};
const Ghosts = ({f}) => {
  const t0 = A.links + 30;
  if (f < t0 || f > A.synth + 4) return null;
  const pose = cameraPose(f);
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', inset: 0}}>
      {LINKS.map(([wa, ta, wb, tb], k) => {
        const a = project(pose, segWorld(wa, ta, f)), b = project(pose, segWorld(wb, tb, f));
        const st = t0 + k * 6;
        const draw = eo3(lin(f, st, st + 16));
        const flick = 0.6 + 0.4 * Math.sin(f * 0.9 + k * 2.1) * Math.sin(f * 0.37 + k);
        const die = lin(f, st + 26, st + 40);
        const mx = (a.x + b.x) / 2 + (k % 2 ? 80 : -80), my = Math.min(a.y, b.y) - 110;
        return (
          <g key={k} opacity={flick * (1 - die)}>
            <path d={`M${a.x} ${a.y} Q${mx} ${my} ${b.x} ${b.y}`} fill="none" stroke={SEGCOL[ta]} strokeWidth={2} pathLength={1} style={{strokeDasharray: `${draw} 1`}} />
            <circle cx={b.x} cy={b.y} r={3.2 * draw} fill={SEGCOL[ta]} />
          </g>
        );
      })}
    </svg>
  );
};

// the year leads the type column through the growth; it lands on 2026 in gold with the hit
const YearCounter = ({f}) => {
  const a = eo3(lin(f, 6, 24)) * (1 - lin(f, A.pick + 22, A.pick + 34));
  if (a <= 0) return null;
  const y = Math.min(2026, Math.floor(yearU(f)));
  const done = f >= Y1 ? clamp(sp(f, Y1, 'pop'), 0, 1.25) : 0;
  const out = lin(f, A.pick + 22, A.pick + 34);
  return (
    <div style={{position: 'absolute', left: COL.x - 8, top: 262, opacity: a, fontFamily: SPACE, fontWeight: 600, fontSize: 150, lineHeight: 1,
      letterSpacing: '-0.045em', color: done > 0.01 ? C.gold : C.fg, fontVariantNumeric: 'tabular-nums', transformOrigin: '0% 70%',
      transform: `translateY(${(1 - eo3(lin(f, 26, 46))) * 24 - eo3(out) * 30}px) scale(${1 + (done > 0 ? Math.sin(Math.PI * clamp(done)) * 0.06 : 0)})`,
      filter: `blur(${eo3(out) * 6}px)`, textShadow: SHADOW}}>
      {y}
    </div>
  );
};
// the search: only the bar. The query is typed for the first reader, then cleared and typed again for the next
const QUERY = 'exercise AND depression';
const SearchBar = ({f}) => {
  const on = band(f, A.search + 32, A.search + 44, A.end - 14, A.end - 6);
  if (on <= 0.001) return null;
  const L = QUERY.length;
  const first = Math.floor(clamp((f - A.search - 36) / 14) * L);
  const cleared = Math.floor((1 - clamp((f - A.scratch - 2) / 6)) * L), again = Math.floor(clamp((f - A.scratch - 12) / 14) * L);
  const n = f < A.scratch + 2 ? first : f < A.scratch + 12 ? cleared : again;
  const typing = (f > A.search + 34 && f < A.search + 52) || (f > A.scratch && f < A.scratch + 28);
  const rise = eo3(clamp(on));
  return (
    <div style={{position: 'absolute', left: COL.x, top: 300, width: 640, opacity: on, transform: `translateY(${(1 - rise) * 16}px)`}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 16, padding: '18px 24px', borderRadius: 16, background: 'rgba(14,18,19,0.95)',
        border: '1px solid rgba(110,227,215,0.38)', fontFamily: MONO, fontSize: 26, color: C.fg}}>
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke={C.muted} strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></svg>
        <span>{QUERY.slice(0, n)}<span style={{opacity: typing && Math.floor(f / 8) % 2 === 0 ? 1 : 0, color: C.teal}}>|</span></span>
      </div>
    </div>
  );
};

// year tags on the review's timeline
const mixGrey = (t) => `rgb(${Math.round(241 + (140 - 241) * t)},${Math.round(183 + (136 - 183) * t)},${Math.round(75 + (126 - 75) * t)})`;
const TimelineLabels = ({f}) => {
  const a = lin(f, A.dated + 10, A.dated + 22) * (1 - lin(f, A.search - 2, A.search + 10));
  if (a <= 0) return null;
  const pose = cameraPose(f);
  const tags = [[RS[0], '2021', C.gold, A.dated + 10], ...STACKS.map((h, s) => [stackX(s), `${2022 + s}`, C.muted, newT(NEW.findIndex((q) => q.s === s)) - 4])];
  return tags.map(([x, t, c, at]) => {
    const p = project(pose, [x, RS[1] - 0.07, RS[2] + 0.55]);
    const r = clamp(sp(f, at, 'ui'));
    return (
      <div key={t} style={{position: 'absolute', left: 0, top: 0, transform: `translate3d(${p.x}px, ${p.y + 18 + (1 - r) * 10}px, 0) translate(-50%, 0)`,
        opacity: a * r, fontFamily: MONO, fontSize: 18, letterSpacing: '0.12em', color: t === '2021' ? mixGrey(reviewAge(f)) : c, textShadow: '0 0 12px #000'}}>{t}</div>
    );
  });
};

const COLB = {x: COL.x, width: COL.w, size: 58};
export const ActOne = () => {
  const f = useCurrentFrame();
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <ThreeCanvas width={width} height={height} camera={{fov: 34, position: [0, 0, 3]}} gl={{antialias: false, powerPreference: 'high-performance'}}>
        <Scene3D f={f} />
      </ThreeCanvas>
      <Ghosts f={f} />
      <TimelineLabels f={f} />
      <YearCounter f={f} />
      <SearchBar f={f} />

      <Block f={f} at={14} until={102} {...COLB} size={54} anchor="top" y={492} lines={['The first scientific', 'journals **appear.**']} />
      <Block f={f} at={116} until={226} {...COLB} size={54} anchor="top" y={492} lines={['For 360 years,', 'science has been', '**recorded in papers.**']} />
      <Block f={f} at={240} until={A.pick + 50} {...COLB} size={54} anchor="top" y={492} lineAt={[240, 246, 288, 293]} stagger={2}
        lines={['Today, millions are', 'published every year —', '**and the number**', '**keeps growing.**']} />
      <Block f={f} at={A.prose - 2} until={A.links - 2} {...COLB}
        lines={[`[[Findings|${C.gold}|8]], [[methods|${C.rose}|14]]`, `and [[context|${C.teal}|20]] are`, 'buried in prose.']} />
      <Block f={f} at={A.links + 12} until={A.synth + 4} {...COLB} lines={['So patterns', 'across studies', '**remain implicit.**']} />
      <Block f={f} at={A.synth + 18} until={A.dated + 2} {...COLB} lines={['Reviews and', 'meta-analyses', 'document **some of**', '**these patterns.**']} />
      <Block f={f} at={A.dated + 14} until={A.search - 4} {...COLB} anchor="top" y={250} lines={['But they take months —', '**and quickly**', '**become outdated.**']} />
      <Block f={f} at={A.search + 40} until={A.scratch - 4} {...COLB} anchor="top" y={492} lines={['Finding every relevant', 'study means **sifting**', '**through thousands.**']} />
      <Block f={f} at={A.scratch + 16} until={A.end - 12} {...COLB} anchor="top" y={492} lines={['And every reader —', 'human or AI —', '**starts from scratch.**']} />
      <AbsoluteFill style={{background: '#000', opacity: lin(f, A.end - 6, A.end)}} />
    </AbsoluteFill>
  );
};
