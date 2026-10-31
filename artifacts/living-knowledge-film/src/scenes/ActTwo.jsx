import React from 'react';
import * as THREE from 'three';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {PaperField} from '../three/PaperField';
import {LightSheet} from '../three/Particles';
import {Graph, useGraphBuffers, LOOK} from '../three/Graph';
import {Shards} from '../three/Shards';
import {Post} from '../three/Post';
import {Rig, applyPose} from '../three/rig';
import {EXT, WALL_COLS as COLS, WALL_ROWS as ROWS, WALL} from '../data/extGraph';
import {PAPER_ASPECT} from '../lib/textures';
import {C} from '../lib/theme';
import {band, clamp, eio, eoExpo, hash, keys, lin, mix} from '../lib/ease';
import {springT, SPR} from '../lib/spring';
import {Block} from '../ui/Type';

// ACT II — the whole field becomes one living graph, papers included. It opens on a statement on black (the turn
// continues), the blade reads the wall from right to left so the type can sit over what it has already read, every page
// travels into the graph with what was read from it, and the living graph settles left of the type column, where new
// papers keep arriving and breaking into their pieces. Local frames (15 = 1 beat).
export const B = {sweep: 90, grid: 240, drop: 300, living: 420, title: 480, end: 600};
export const GP = [0, 0, -9];
export const FLY = 56; // frames a piece takes from the wall to its place
const rotY = (f) => Math.max(0, f - B.drop) * 0.0014; // the graph turns slowly once it exists

// ---- the field: a wall of papers ---------------------------------------------------------
const SX = 0.95, SY = 1.24, WS = 0.88;
const cell = (j) => [(j % COLS - (COLS - 1) / 2) * SX, ((ROWS - 1) / 2 - Math.floor(j / COLS)) * SY, (hash(j * 9.7) - 0.5) * 0.25];
const sweepX = (f) => keys(f, [[0, 21.6], [B.sweep, 21.6], [B.sweep + 14, 17.5, (t) => t * t], [B.grid, -21.6, (t) => 1 - Math.pow(1 - t, 2.2)]]);
const crossTable = (() => { const t = []; for (let f = 0; f <= B.grid + 4; f += 0.5) t.push([f, sweepX(f)]); return t; })();
const crossAt = (x) => { for (const [f, sx] of crossTable) if (sx <= x - 0.05) return f; return B.grid; };

// each wall page ↔ one paper node + what was extracted from it; the concepts shared across topics ride on pages near
// the middle of the wall
const nodeInfo = new Map();
EXT.wallPapers.forEach((p, j) => {
  nodeInfo.set(p.node, {j, slot: -1, n: p.members.length});
  p.members.forEach((m, k) => nodeInfo.set(m, {j, slot: k, n: p.members.length}));
});
const MID = Array.from({length: WALL}, (_, j) => j).sort((a, b) => Math.hypot(cell(a)[0], cell(a)[1]) - Math.hypot(cell(b)[0], cell(b)[1]));
EXT.nodes.forEach((n, i) => { if (!nodeInfo.has(i) && !n[7]) nodeInfo.set(i, {j: MID[(nodeInfo.size % 9) * 3], slot: -2, n: 1, extra: true}); });
const wallPoint = (i) => {
  const {j, slot, n, extra} = nodeInfo.get(i), c = cell(j);
  if (extra) return [c[0], c[1] + 0.34, c[2] + 0.06];
  if (slot < 0) return [c[0], c[1] + 0.02, c[2] + 0.07];
  const a = (slot / n) * Math.PI * 2 + hash(j * 3.3) * 6.28, r = 0.24 + hash(j * 7 + slot) * 0.05;
  return [c[0] + Math.cos(a) * r, c[1] + Math.sin(a) * r * 1.2, c[2] + 0.06];
};
// pages leave the wall in the order the blade read them, right to left
const pageBirth = (j) => B.drop + ((21.6 - cell(j)[0]) / 43.2) * 22 + hash(j * 2.7) * 5;

// ---- the living shot: the graph sits left of the type column, pulled back so it clears both the type and the frame edge
const LIV_L = [7.46, 0.3, -6.1], LIV_K = 1.2, LIV_SHIFT = 2;
export const livingPose = (f) => {
  const t = lin(f, B.living, B.end);
  const P0 = [mix(-11.25, -12.85, t), mix(7.5, 6.64, t), mix(19.9, 18.4, t)];
  const pos = P0.map((v, j) => LIV_L[j] + (v - LIV_L[j]) * LIV_K);
  const F = LIV_L.map((v, j) => v - pos[j]), fl = Math.hypot(...F);
  const R = [-F[2] / fl, 0, F[0] / fl], rl = Math.hypot(...R);
  return {pos, look: LIV_L.map((v, j) => v + (R[j] / rl) * LIV_SHIFT), fov: 46, roll: 0.03};
};

const orbitPos = (a, r, y) => [GP[0] + Math.sin(a) * r, y, GP[2] + Math.cos(a) * r];

// ---- camera: shots blended by critically damped springs ---------------------------------------
const blend = (a, b, w) => ({pos: a.pos.map((v, k) => mix(v, b.pos[k], w)), look: a.look.map((v, k) => mix(v, b.look[k], w)), fov: mix(a.fov, b.fov, w), roll: mix(a.roll, b.roll, w)});
const shots = (f, list) => {
  let cur = list[0].pose(f);
  for (let i = 1; i < list.length; i++) {
    if (f < list[i].t) break;
    cur = blend(cur, list[i].pose(f), springT((f - list[i].t) / 30, SPR[list[i].p || 'camera']));
  }
  return cur;
};
const orbitLook = (a, s) => [GP[0] + Math.cos(a) * s, GP[1] + 0.3 * (s / 8), GP[2] - Math.sin(a) * s];
const cameraPose = (f) => shots(f, [
  {t: 0, pose: (ff) => ({pos: [27 - ff * 0.012, 2.4 - ff * 0.004, 15.5 - ff * 0.02], look: [15, 0, 0], fov: 42, roll: -0.015})},
  {t: B.sweep - 12, p: 'slow', pose: (ff) => ({pos: [sweepX(ff) + 2.6, 1.3, 12.5], look: [sweepX(ff) + 1.1, 0, 0], fov: 40, roll: 0})},
  {t: B.grid, pose: (ff) => ({pos: [0, 3.5 + (ff - B.grid) * 0.01, 35 + (ff - B.grid) * 0.02], look: [0, 0, -1.5], fov: 44, roll: 0})},
  {t: B.drop, p: 'slow', pose: (ff) => {
    const a = mix(0.05, -0.45, eio(lin(ff, B.drop, B.living + 20))), e = eio(lin(ff, B.drop + 20, B.living));
    return {pos: orbitPos(a, mix(34, 31.5, e), mix(8.5, 7, e)), look: orbitLook(a, 8 * e), fov: mix(44, 46, e), roll: 0.02};
  }},
  {t: B.living - 10, pose: livingPose},
]);
// ---- graph timing -------------------------------------------------------------------------------
const graphSeed = (i, n) => (n[7] ? hash(i * 1.37) * 0.6 : hash(i * 1.37));
// where a node sits in the world at frame f once it has landed (the graph turns, and every node breathes a little)
const nodeAt = (i, f) => {
  const n = EXT.nodes[i], a = rotY(f), s = graphSeed(i, n);
  const br = [Math.sin(f * 0.021 + s * 6.28), Math.cos(f * 0.017 + s * 12.1), Math.sin(f * 0.019 + s * 3.7)];
  return [GP[0] + n[0] * Math.cos(a) + n[2] * Math.sin(a) + br[0] * 0.08, GP[1] + n[1] + br[1] * 0.08, GP[2] - n[0] * Math.sin(a) + n[2] * Math.cos(a) + br[2] * 0.08];
};

// ---- new research: a steady stream of new papers flies in from beyond the frame at one steady pace. Each comes apart as
// it flies — what was extracted from it, then the paper itself (the title band) — and the pieces fly on at the same pace
// into their places, slowing only as they land --
const LATE = EXT.latePapers;
const STREAM = [402, 560]; // the moments pages start coming apart, one after another; every piece lands before the cut
const PACE = 0.42;  // world units a page covers per frame, and the speed its pieces leave it with
const PEEL = 1.7;   // frames between pieces leaving a page
const U_BREAK = 0.55; // the share of its path a page has flown when it starts coming apart (more, for pages that arrive near the cut)
const LAST = B.end - 3; // every piece is in place by then
const incoming = LATE.map((p, k) => {
  const h = (q) => hash(k * 5.3 + q * 1.7 + 71);
  return {t: STREAM[0] + ((k + 0.5) / LATE.length) * (STREAM[1] - STREAM[0]) + (h(1) - 0.5) * 3, node: p.node, members: p.members,
    up: (h(4) - 0.45) * 2.2, reach: 0.3 + h(5) * 0.45, spin: [(h(6) - 0.5) * 3, (h(7) - 0.5) * 3.5, (h(8) - 0.5) * 2], v: (k * 7) % 12};
});
LATE.forEach((p, k) => {
  nodeInfo.set(p.node, {late: true, k, slot: -1, n: p.members.length});
  p.members.forEach((m, s) => nodeInfo.set(m, {late: true, k, slot: s, n: p.members.length}));
});
// the camera's frame while papers arrive
const ARR = livingPose((STREAM[0] + STREAM[1]) / 2);
const ARR_POS = ARR.pos;
const ARR_F = (() => { const d = ARR.look.map((v, k) => v - ARR_POS[k]), l = Math.hypot(...d); return d.map((v) => v / l); })();
const ARR_R = (() => { const r = [-ARR_F[2], 0, ARR_F[0]], l = Math.hypot(...r); return r.map((v) => v / l); })();
const FACE = [-Math.asin(Math.max(-1, Math.min(1, -ARR_F[1] / Math.cos(Math.asin(-ARR_F[0]))))), Math.asin(-ARR_F[0])]; // a page facing the camera
const W2 = PAPER_ASPECT / 2;
const bez = (S, M, A, u) => [0, 1, 2].map((j) => mix(mix(S[j], M[j], u), mix(M[j], A[j], u), u));
// a page's flight: a gentle arc from beyond the frame toward the paper's place, at one steady pace. w is the share of the
// path's length it has covered; it turns to face us on the way in and starts coming apart at wb, without slowing down.
const uOf = (P, w) => { // the curve's parameter at that share of its length
  const s = w * P.len, c = P.cum, n = c.length - 1;
  if (s <= 0) return s / c[1] / n;
  if (s >= P.len) return 1 + (s - P.len) / (c[n] - c[n - 1]) / n;
  let i = 0;
  for (let step = n >> 1; step; step >>= 1) if (c[i + step] < s) i += step;
  return (i + (s - c[i]) / (c[i + 1] - c[i])) / n;
};
const pagePose = (q, P, w, wb) => {
  const turn = clamp(w / wb), e = turn * turn * (3 - 2 * turn);
  return {p: bez(P.S, P.M, P.A, uOf(P, w)), s: mix(1.5, 1.15, e),
    m: new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(mix(q.spin[0], FACE[0], e), mix(q.spin[1], FACE[1], e), q.spin[2] * (1 - e)))};
};
const view = new THREE.PerspectiveCamera(46, 16 / 9, 0.05, 400);
const inView = (st, f) => {
  applyPose(view, cameraPose(f));
  const c = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([x, y]) =>
    new THREE.Vector3(x * W2 * st.s, y * 0.5 * st.s, 0).applyMatrix4(st.m).add(new THREE.Vector3(...st.p)).project(view));
  const xs = c.map((v) => v.x), ys = c.map((v) => v.y);
  return c.every((v) => v.z < 1) && Math.max(...xs) > -1 && Math.min(...xs) < 1 && Math.max(...ys) > -1 && Math.min(...ys) < 1;
};
// it sets off out of view, from as near the lens as it can while still coming into view early on, so it is seen whole
// before it comes apart. Most come from the left; a paper whose place is at the graph's left edge comes from above or
// below instead.
const ARR_U = [0, 1, 2].map((j) => ARR_R[(j + 1) % 3] * ARR_F[(j + 2) % 3] - ARR_R[(j + 2) % 3] * ARR_F[(j + 1) % 3]);
const FROM = [[-1, 0], [-1, 0.8], [-1, -0.8], [-0.3, 1], [-0.3, -1], [0.4, 1], [0.4, -1]]; // left, upper left, lower left, then from above or below
const PATH = incoming.map((q) => {
  const A = nodeAt(q.node, q.t + 40), toCam = ARR_POS.map((v, j) => v - A[j]);
  const make = ([r, u], reach, far = 20) => {
    const d = [0, 1, 2].map((j) => ARR_R[j] * r + ARR_U[j] * u), l = Math.hypot(...d);
    const S = A.map((v, j) => v + (d[j] / l) * far + (j === 1 && !u ? 5 + q.up * 4 : 0) + toCam[j] * reach);
    const M = S.map((v, j) => (v + A[j]) / 2 + (j === 1 ? 1.8 : 0));
    const cum = [0];
    for (let i = 0; i < 64; i++) cum.push(cum[i] + Math.hypot(...bez(S, M, A, (i + 1) / 64).map((v, j) => v - bez(S, M, A, i / 64)[j])));
    return {S, M, A, len: cum[64], cum};
  };
  const seen = (P, w) => inView(pagePose(q, P, w, U_BREAK), q.t + ((w - U_BREAK) * P.len) / PACE);
  for (const from of FROM) for (const far of [20, 15, 12]) for (let reach = q.reach; reach > 0.02; reach -= 0.04) {
    const P = make(from, reach, far);
    if (!seen(P, 0) && seen(P, U_BREAK - (14 * PACE) / P.len)) return P; // in view at least 14 frames before it comes apart
  }
  return make(FROM[0], 0.02);
});
const pageAt = (k, f) => { const q = incoming[k], P = PATH[k]; return pagePose(q, P, q.ub + ((f - q.t) * PACE) / P.len, q.ub); };
// the pieces of a page: the title band is the paper; the two columns are cut into one piece per extracted item. The page
// comes apart from a point on its bottom edge upward, and the title band goes last.
const TYPE_COL = LOOK.palette.map((h) => new THREE.Color(h));
const CLUS_COL = LOOK.clusters.map((h) => new THREE.Color(h));
// where a piece leaves its page and how it is moving: it keeps the page's velocity (plus a small push away from the page's
// centre) and flies on a smooth curve to its place in the graph, taking as long as that distance needs at the page's pace,
// so its speed only falls off as it lands
const launch = (pc) => {
  const st = pageAt(pc.k, pc.t0), cx = (pc.x0 + pc.x1) / 2, cy = (pc.y0 + pc.y1) / 2;
  const local = new THREE.Vector3(cx * st.s, cy * st.s, 0).applyMatrix4(st.m);
  pc.C0 = st.p.map((v, j) => v + local.getComponent(j));
  const a = pageAt(pc.k, pc.t0 - 0.5).p, b = pageAt(pc.k, pc.t0 + 0.5).p, out = local.clone().normalize().multiplyScalar(0.035);
  const V = [0, 1, 2].map((j) => b[j] - a[j] + out.getComponent(j)), sp = Math.hypot(...V);
  let t1 = pc.t0 + 30, need = 0;
  for (let it = 0; it < 3; it++) { // the graph turns while the piece flies, so aim at where its node will be
    const D = nodeAt(pc.node, t1).map((v, j) => v - pc.C0[j]), d = Math.hypot(...D);
    const along = D.reduce((s, v, j) => s + v * V[j], 0) / Math.max(1e-6, d);
    need = Math.max(14, (1.5 * d) / Math.max(along, 0.6 * sp)); // 1.5 × distance: the speed eases off as 1 − s²
    t1 = pc.t0 + Math.min(need, LAST - pc.t0);
  }
  pc.T = t1 - pc.t0; pc.t1 = t1; pc.late = need - pc.T; // frames it would need beyond the cut
  pc.P1 = nodeAt(pc.node, t1);
  pc.V0T = V.map((v) => v * pc.T);
  return st;
};
const PIECES = incoming.flatMap((q, k) => {
  const h = (x) => hash(k * 11.7 + x * 3.1 + 5);
  const n = q.members.length, top = 0.24 + (h(1) - 0.5) * 0.04, gut = (h(2) - 0.5) * 0.06 * PAPER_ASPECT;
  const rects = [];
  const column = (cnt, x0, x1, salt) => {
    const cuts = [-0.5];
    for (let r = 1; r < cnt; r++) cuts.push(-0.5 + (1 - top) * (r / cnt + (h(salt + r) - 0.5) * 0.45 / cnt));
    cuts.push(0.5 - top);
    for (let r = 0; r < cnt; r++) rects.push({x0, x1, y0: cuts[r], y1: cuts[r + 1]});
  };
  column(Math.ceil(n / 2), -W2, gut, 10);
  column(n - Math.ceil(n / 2), gut, W2, 20);
  const ox = (h(3) - 0.5) * PAPER_ASPECT;
  const far = (r) => Math.hypot((r.x0 + r.x1) / 2 - ox, (r.y0 + r.y1) / 2 + 0.5);
  const body = rects.map((r, s) => ({...r, node: q.members[s]})).sort((a, b) => far(a) - far(b));
  const pcs = [...body, {x0: -W2, x1: W2, y0: 0.5 - top, y1: 0.5, node: q.node, paper: true}].map((r, o) => ({k, ...r,
    t0: q.t + o * PEEL + (r.paper ? 2 : 0), tilt: [h(40 + o) - 0.5, h(50 + o) - 0.5], spin: (0.6 + h(60 + o) * 0.8) * (h(70 + o) < 0.5 ? -1 : 1)}));
  // a page that arrives near the cut starts coming apart further along its path, so its pieces have less far to go
  for (q.ub = U_BREAK; q.ub < 0.85; q.ub += 0.01) if (pcs.every((pc) => (launch(pc), pc.late < 0.01))) break;
  q.tA = q.t - (q.ub * PATH[k].len) / PACE; // when it sets off from beyond the frame
  return pcs;
});
const LAND = new Map(PIECES.map((pc) => [pc.node, pc.t1]));
PIECES.forEach((pc) => {
  const st = launch(pc);
  pc.ax0 = new THREE.Vector3(((pc.x1 - pc.x0) / 2) * st.s, 0, 0).applyMatrix4(st.m);
  pc.ay0 = new THREE.Vector3(0, ((pc.y1 - pc.y0) / 2) * st.s, 0).applyMatrix4(st.m);
  pc.axis = new THREE.Vector3(pc.tilt[0], pc.tilt[1], 0.0001).applyMatrix4(st.m).normalize();
  pc.uv = [pc.x0 / PAPER_ASPECT + 0.5, pc.y0 + 0.5, pc.x1 / PAPER_ASPECT + 0.5, pc.y1 + 0.5];
  const n = EXT.nodes[pc.node];
  pc.typeCol = TYPE_COL[n[3]]; pc.nodeCol = pc.paper ? TYPE_COL[6] : CLUS_COL[n[4]];
  pc.size = n[5] * (pc.paper ? LOOK.paper[0] : LOOK.sizes[2]);
});

function graphBirth(i) {
  const info = nodeInfo.get(i);
  return info.late ? LAND.get(i) - 60 : pageBirth(info.j); // a new paper's pieces are in place the moment they land
}
const graphSource = (i) => {
  const info = nodeInfo.get(i), n = EXT.nodes[i];
  if (info.late) return [n[0], n[1], n[2]];
  const w = wallPoint(i);
  return [w[0] - GP[0], w[1] - GP[1], w[2] - GP[2]];
};
const graphAppear = (i) => {
  const info = nodeInfo.get(i);
  if (info.late) return LAND.get(i);
  return crossAt(cell(info.j)[0]) + (info.slot === -1 ? 1 : info.extra ? 4 : 3 + info.slot * 1.5);
};
// every piece travels with its page, from where the page was on the wall to where the paper lands, then unfolds
const graphGroup = (i) => {
  const info = nodeInfo.get(i), n = EXT.nodes[i];
  if (info.late) return null;
  if (info.extra) return {grp: graphSource(i), dock: [n[0], n[1], n[2]]};
  const P = EXT.wallPapers[info.j].node, w = wallPoint(P), d = EXT.nodes[P];
  return {grp: [w[0] - GP[0], w[1] - GP[1], w[2] - GP[2]], dock: [d[0], d[1], d[2]]};
};
const graphMode = (i) => (nodeInfo.get(i).late ? 0 : 2);
// a page's spokes grow on the wall as the blade opens it and travel with it; the graph's own threads grow as their ends
// land; a new paper's threads grow once its pieces are in place
const graphEdgeBirth = (a, b, kind, e, def) => {
  const ia = nodeInfo.get(a), ib = nodeInfo.get(b);
  if (ia.late || ib.late) return Math.max(graphAppear(a), graphAppear(b)) + 4 + hash(e * 1.3) * 10;
  if (kind === 4) return graphAppear(ia.slot >= 0 ? a : b) + 1;
  return def;
};
// Act III starts from this exact graph state
export const ACT2_GRAPH = {source: graphSource, birth: graphBirth, appear: graphAppear, seedOf: graphSeed, modeOf: graphMode, group: graphGroup,
  edgeBirth: graphEdgeBirth, edgeDelay: FLY - 60 - 16, edgeJitter: 10};

export const ACT2_END = {pose: livingPose(B.end), rot: rotY(B.end)};

// ---- 3D pieces --------------------------------------------------------------------------------
const Wall = ({f}) => (
  <PaperField count={WALL} variant={(j) => (j * 7 + Math.floor(j / COLS)) % 12} fog={[14, 60]} bright={0.78} dissolveX={sweepX(f)} dissolveDir={1}
    layout={(j, o) => {
      const c = cell(j);
      o.x = c[0]; o.y = c[1]; o.z = c[2]; o.rx = (hash(j * 2.1) - 0.5) * 0.08; o.ry = (hash(j * 3.3) - 0.5) * 0.1; o.rz = (hash(j * 4.4) - 0.5) * 0.03;
      o.s = WS; o.alpha = eio(lin(f, 66, 92));
      const dx = c[0] - sweepX(f);
      o.glow = f > B.sweep ? Math.exp(-dx * dx * 1.2) * 0.3 : 0;
    }} />
);

// the arriving pages, drawn as their pieces: whole while they fly in, then each piece tumbles off, turns to face us,
// draws in to the size and colour of its node and lands, where the graph takes over
const sst = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * t * (t * (t * 6 - 15) + 10); };
const hermite = (P0, V0T, P1, s) => {
  const s2 = s * s, s3 = s2 * s, h00 = 2 * s3 - 3 * s2 + 1, h10 = s3 - 2 * s2 + s, h01 = -2 * s3 + 3 * s2;
  return P0.map((v, j) => h00 * v + h10 * V0T[j] + h01 * P1[j]);
};
const lens = new THREE.PerspectiveCamera(46, 16 / 9, 0.05, 400);
const IncomingPapers = ({f, pose}) => {
  applyPose(lens, pose);
  const right = new THREE.Vector3().setFromMatrixColumn(lens.matrixWorld, 0), up = new THREE.Vector3().setFromMatrixColumn(lens.matrixWorld, 1);
  const fwd = new THREE.Vector3().setFromMatrixColumn(lens.matrixWorld, 2).negate(), tanH = Math.tan(THREE.MathUtils.degToRad(pose.fov / 2));
  return (
    <Shards count={PIECES.length} fog={[20, 90]} dotFog={[20, 72]} bright={0.8} scale={320} rim={LOOK.rim}
      layout={(i, o) => {
        const pc = PIECES[i], q = incoming[pc.k];
        if (f < q.tA || f >= pc.t1) return;
        o.uv = pc.uv; o.page = q.v; o.size = pc.size; o.cap = LOOK.maxPx[2]; o.paper = pc.paper ? 1 : 0;
        if (f < pc.t0) { // still part of the page, and blurred as the whole page (every piece takes the page's own motion)
          const hx = (pc.x1 - pc.x0) / 2, hy = (pc.y1 - pc.y0) / 2, cx = pc.x0 + hx, cy = pc.y0 + hy;
          const st = pageAt(pc.k, f), back = pageAt(pc.k, f - 0.5).p;
          const c = new THREE.Vector3(cx * st.s, cy * st.s, 0).applyMatrix4(st.m).add(new THREE.Vector3(...st.p));
          o.pos = c.toArray(); o.prev = o.pos.map((v, j) => v - st.p[j] + back[j]);
          o.ax = new THREE.Vector3(hx * st.s, 0, 0).applyMatrix4(st.m).toArray();
          o.ay = new THREE.Vector3(0, hy * st.s, 0).applyMatrix4(st.m).toArray();
          o.pg = [(-W2 - cx) / hx, (-0.5 - cy) / hy, (W2 - cx) / hx, (0.5 - cy) / hy];
          o.col = [pc.typeCol.r, pc.typeCol.g, pc.typeCol.b]; o.wash = 0; o.dot = 0; o.round = 0; o.solid = 0; o.alpha = 1;
          return;
        }
        const s = (f - pc.t0) / pc.T;
        o.pos = hermite(pc.C0, pc.V0T, pc.P1, s);
        o.prev = hermite(pc.C0, pc.V0T, pc.P1, Math.max(0, s - 0.5 / pc.T));
        const depth = new THREE.Vector3(...o.pos).sub(lens.position).dot(fwd);
        const R = 0.5 * Math.min((pc.size * 320) / depth, LOOK.maxPx[2]) * depth * ((2 * tanH) / 1080) * (pc.paper ? 0.7 : 1);
        const shrink = sst(0.04, 0.4, s), face = sst(0.16, 0.4, s), phi = pc.spin * sst(0, 0.45, s);
        const ax = pc.ax0.clone().applyAxisAngle(pc.axis, phi), ay = pc.ay0.clone().applyAxisAngle(pc.axis, phi);
        const hw = mix(ax.length(), R, shrink), hh = mix(ay.length(), R, shrink);
        o.ax = ax.normalize().lerp(right, face).normalize().multiplyScalar(hw).toArray();
        o.ay = ay.normalize().lerp(up, face).normalize().multiplyScalar(hh).toArray();
        o.round = pc.paper ? 0 : sst(0.12, 0.4, s);
        o.wash = pc.paper ? 0 : sst(0, 0.2, s);
        o.solid = sst(0.2, 0.42, s);
        o.dot = s >= 0.42 ? 1 : 0;
        const c = pc.typeCol.clone().lerp(pc.nodeCol, sst(0.55, 0.95, s));
        o.col = [c.r, c.g, c.b];
        o.alpha = pc.paper ? mix(1, LOOK.paper[1], sst(0.2, 0.42, s)) : 1;
      }} />
  );
};

const Scene3D = ({f}) => {
  const pose = cameraPose(f);
  const buffers = useGraphBuffers({graph: EXT, ...ACT2_GRAPH, key: 'act2-v19'});
  const open = eoExpo(lin(f, 66, 96));
  const bladeI = (0.85 + 1.4 * band(f, 66, 70, 76, 104)) * (1 - lin(f, B.grid - 4, B.grid + 16)) * lin(f, 62, 68);
  return (
    <>
      <color attach="background" args={[C.bg]} />
      <Rig pose={pose} />
      {f < B.grid + 10 && <Wall f={f} />}
      {bladeI > 0.001 && <LightSheet f={f} x={sweepX(f)} open={open} intensity={bladeI} z={0.25} width={1.4} height={30} focusZ={0} spread={0.5} />}
      <Graph buffers={buffers} f={f} rotY={rotY(f)} position={GP} fly={FLY} scale={320} grow={24} swirl={0.5} compact={0.5}
        bridge={band(f, B.drop + 56, B.drop + 80, B.living - 6, B.living + 16)} fog={[20, 72]} />
      {f > STREAM[0] - 40 && <IncomingPapers f={f} pose={pose} />}
      <Post bloom={0.45 * (1 - lin(f, B.drop - 10, B.drop + 20))} threshold={0.9} smoothing={0.15} radius={0.4} vignette={0} grain={0.02} />
    </>
  );
};

const COL = {x: 1250, width: 600, size: 58};
// the statement on black: display type, centred, like the thesis before it
const Statement = ({f}) => {
  if (f > 80) return null;
  return <Block f={f} at={6} until={62} x={0} width={1920} align="center" y={540} size={84} weight={600} lh={1.08} tracking={-0.035} stagger={2.2} lineDelay={8}
    lines={['AI can now read', '**an entire field.**']} />;
};
export const ActTwo = () => {
  const f = useCurrentFrame();
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <ThreeCanvas width={width} height={height} camera={{fov: 42, position: [0, 0, 20]}} gl={{antialias: false, powerPreference: 'high-performance'}}>
        <Scene3D f={f} />
      </ThreeCanvas>
      <AbsoluteFill style={{background: '#000', opacity: 1 - lin(f, 0, 8)}} />

      <Statement f={f} />
      <Block f={f} at={B.sweep + 30} until={B.grid - 4} {...COL} x={1180} width={660}
        lines={[`[[Findings|${C.gold}|6]], [[methods|${C.rose}|12]]`, `and [[context|${C.teal}|18]] —`, 'extracted from', 'every paper.']} />
      <Block f={f} at={B.drop + 28} until={B.living - 12} {...COL} lines={['**Connected**', 'into one', 'knowledge graph.']} />
      <Block f={f} at={B.living + 2} until={B.end + 30} {...COL} size={100} weight={600} lh={1.02} tracking={-0.04} stagger={2.4} lineDelay={7}
        lines={['A **living**', 'knowledge', 'graph.']} />
    </AbsoluteFill>
  );
};
