import React, {useMemo, useLayoutEffect} from 'react';
import * as THREE from 'three';
import {useThree} from '@react-three/fiber';
import graph from '../data/graph.json';
import {hash} from '../lib/ease';
import {CLUSTER_RANK} from '../data/extGraph';

// Node record: [x, y, z, type, cluster, size, order, late]
export const G = graph;
export const NODE_COUNT = graph.nodes.length;

// type: 0 concept, 1 finding, 2 intervention, 3 population, 4 method, 5 outcome, 6 paper
// (findings gold · methods rose · context teal · papers off-white — the colour code the captions use)
export const TYPE_COLORS = ['#f3efe6', '#f1b74b', '#6ee3d7', '#5fd0c4', '#f080a3', '#56c4b8', '#9aa4a6'];

// Visual looks. sizes/maxPx: hub, sub-hub, leaf (world size, then a pixel cap so nothing near the lens balloons);
// leafDim: leaves sit below the hierarchy; paper: [size, alpha]; edge: [gain, tint toward the node colours, base colour].
// byCluster: nodes take the colour of their cluster; keep: the share of leaves drawn; straight: short spokes run straight.
const BRAND = ['#f3efe6', '#f1b74b', '#6ee3d7', '#5fd0c4', '#f080a3', '#56c4b8', '#9aa4a6'];
// a colour ramp sampled at each cluster's place in the frame, so hue flows across the whole graph
const ramp = (stops, t) => {
  const c = stops.map((h) => new THREE.Color(h)), x = Math.min(0.9999, Math.max(0, t)) * (c.length - 1), i = Math.floor(x);
  return '#' + c[i].clone().lerp(c[i + 1], x - i).getHexString();
};
const spectral = (stops) => Array.from({length: 12}, (_, k) => ramp(stops, CLUSTER_RANK[k] ?? 0.5));
export const SPECTRUM = ['#5fd6c8', '#7fb5f2', '#ae9df3', '#ef8db0', '#f4a27a', '#f0c35e'];
const clusterLook = (clusters, o = {}) => ({sizes: [.6, .44, .46], maxPx: [16, 9.5, 5.6], leafDim: 1, stem: .25, paper: [.24, .34], spokes: .25, soft: 0, add: false,
  edge: [1.5, .92, '#8f9493'], palette: BRAND, byCluster: 1, clusters, rim: .3, flat: 1, edgeNormal: 1, keep: .62, straight: 1, flash: .3, open: .6, ...o});
export const LOOKS = {
  // v11: every topic its own hue, flowing teal → blue → violet → rose → coral → gold across the field; crisp flat dots with
  // a dark rim, straight spokes, threads alpha-blended in their clusters' colours; no glow
  spectrum: clusterLook(spectral(SPECTRUM)),
  // the product's language: teal threads and ring hubs as in the Explore flow diagram
  teal: {sizes: [.62, .46, .34], maxPx: [17, 10, 4.4], leafDim: 1, stem: 0, paper: [.26, .45], spokes: .3, soft: 0, add: false, flat: 1, rim: 0, ring: 1,
    edge: [1.25, 0, '#6ee3d7'], edgeNormal: 1, keep: .62, straight: 1, palette: ['#6ee3d7', '#cdeee9', '#cdeee9', '#cdeee9', '#cdeee9', '#cdeee9', '#9aa4a6']},
  // v10 (rejected): warm ivory threads, white stems, type colours on the leaf tips
  pearl: {sizes: [.42, .34, .46], maxPx: [16, 9, 5.4], leafDim: 1, stem: .9, paper: [.24, .12], spokes: 0, soft: 0, add: false, edge: [1.0, .16, '#d6cdbc'],
    palette: ['#fffaf0', '#f8c46c', '#8fe9df', '#7fdcd2', '#f6a3bf', '#72d1c7', '#7f8789']},
};
export const LOOK = LOOKS.spectrum;
// another field in Act IV: the same drawing in one hue, lighter to darker across its clusters
export const fieldLook = (hex) => {
  const c = new THREE.Color(hex);
  const hi = '#' + c.clone().lerp(new THREE.Color('#ffffff'), 0.28).getHexString(), lo = '#' + c.clone().multiplyScalar(0.72).getHexString();
  return clusterLook(spectral([hi, hex, lo]));
};

// Every node: appears (pops in at its source), waits, flies to its target at `birth`,
// and can be morphed onto a flat layout (aFlat) by uMorph with a per-node delay.
const COMMON = /* glsl */ `
uniform float uF; uniform float uFly; uniform mat3 uRot; uniform float uBreath; uniform float uMorph; uniform float uBend;
uniform float uSwirl; uniform float uCompact;
float eioc(float t){ return t < .5 ? 4.*t*t*t : 1. - pow(max(0., -2.*t + 2.), 3.) / 2.; }
float sstep5(float a, float b, float x){ float t = clamp((x - a) / (b - a), 0., 1.); return t * t * t * (t * (t * 6. - 15.) + 10.); }
vec3 breathAt(float t, float seed){ return uBreath * vec3(sin(t * .021 + seed * 6.28), cos(t * .017 + seed * 12.1), sin(t * .019 + seed * 3.7)) * .08; }
// where a node is at time t. mode 0: it lifts off from rest along a gentle arc; 1: it leaves already moving (eases out
// only); 2: it travels with its paper (grp → dock, the paper's own place, the group drawing in as it goes), then unfolds
// from the dock into its own place. Every path bends the same way around the graph's axis, so the streams flow together.
vec3 nodeAt(vec3 src, vec3 tgt, vec3 grp, vec3 dock, float birth, float seed, float mode, float t){
  float k = clamp((t - birth) / uFly, 0., 1.);
  vec3 T = uRot * tgt + breathAt(t, seed);
  if (mode > 1.5) {
    float eA = sstep5(0., .8, k), eB = sstep5(.42, 1., k);
    vec3 D = uRot * dock;
    vec3 G = mix(grp, D, eA);
    float th = uSwirl * 4. * eA * (1. - eA), c = cos(th), s = sin(th);
    G = vec3(c * G.x + s * G.z, G.y, -s * G.x + c * G.z);
    vec3 O = src - grp;
    return G + O * mix(1., uCompact, eA) + (T - D - O * uCompact) * eB;
  }
  float e = mix(eioc(k), 1. - pow(1. - k, 3.5), mode); // 3.5: a piece leaves at about the speed of its page
  vec3 p = mix(src, T, e);
  vec3 d = T - src;
  vec3 side = normalize(cross(d + vec3(1e-3), vec3(0., 1., 0.)));
  float arc = sin(3.14159 * e);
  p += (side * (seed - .5) * 3. + vec3(0., 1., 0.) * (0.6 + seed * 1.8)) * arc * min(1., length(d) * .08);
  return p;
}
vec3 morphAt(vec3 p, vec3 flatPos, float delay, float m){
  float x = clamp((m - delay) / .55, 0., 1.);
  return mix(p, flatPos, eioc(x));
}
vec3 morphPos(vec3 p, vec3 flatPos, float delay){ return morphAt(p, flatPos, delay, uMorph); }
// every edge is a gentle quadratic arc; all arcs bend the same way around the vertical, so bundles flow
vec3 arcCtrl(vec3 a, vec3 b){
  vec3 d = b - a;
  vec3 side = cross(d, vec3(0., 1., 0.));
  float l = length(side);
  side = l > 1e-4 ? side / l : vec3(1., 0., 0.);
  float L = length(d);
  float lift = smoothstep(4., 16., L) * .75; // long edges arch upward like flight paths; short ones just curve
  return (a + b) * .5 + (side * (1. - lift * .5) + vec3(0., 1., 0.) * lift) * L * uBend * (1. - uMorph);
}
vec3 arcAt(vec3 a, vec3 c, vec3 b, float t){ return mix(mix(a, c, t), mix(c, b, t), t); }
`;

// Nodes are quads, one per node (instanced). At rest a quad is exactly the dot's square; while the node moves it
// stretches along the node's path over the shutter, so fast pieces are drawn motion-blurred, as a camera would see them.
const nodeVert = /* glsl */ `
${COMMON}
attribute vec3 aTgt; attribute vec3 aSrc; attribute vec3 aFlat; attribute vec3 aGrp; attribute vec3 aDock;
attribute vec4 aNodeA; // type, size, birth, seed
attribute vec4 aNodeB; // cluster, hub level, index, appear
attribute vec2 aNodeC; // morph delay, motion mode
uniform float uScale; uniform float uFocusCluster; uniform float uFocusAmt; uniform float uHiNode;
uniform vec3 uColors[7]; uniform float uFogNear; uniform float uFogFar; uniform float uHiCluster; uniform float uHiAmt;
uniform vec4 uSel; uniform float uSelAmt; uniform vec3 uSizes; uniform vec3 uMaxPx; uniform float uLeafDim; uniform vec2 uPaper; uniform float uStem; uniform float uDpr;
uniform vec3 uCluster[12]; uniform float uByCluster; uniform float uKeep; uniform vec3 uTint; uniform float uTintAmt; uniform float uFlashAmt; uniform float uOpen;
uniform vec2 uViewport; uniform float uShutter; uniform float uMorphPrev;
varying vec3 vColor; varying float vAlpha; varying float vFlash; varying float vHub; varying float vType; varying float vSize;
varying vec2 vQ; varying float vLh; varying float vR;
float inSel(float i){ return (abs(i - uSel.x) < .5 || abs(i - uSel.y) < .5 || abs(i - uSel.z) < .5 || abs(i - uSel.w) < .5) ? 1. : 0.; }
void main(){
  float aType = aNodeA.x, aSize = aNodeA.y, aBirth = aNodeA.z, aSeed = aNodeA.w;
  float aCluster = aNodeB.x, aHub = aNodeB.y, aIndex = aNodeB.z, aAppear = aNodeB.w;
  float aDelay = aNodeC.x, aMode = aNodeC.y;
  float k = clamp((uF - aBirth) / uFly, 0., 1.);
  vec3 p = morphAt(nodeAt(aSrc, aTgt, aGrp, aDock, aBirth, aSeed, aMode, uF), aFlat, aDelay, uMorph);
  vec3 pp = morphAt(nodeAt(aSrc, aTgt, aGrp, aDock, aBirth, aSeed, aMode, uF - uShutter), aFlat, aDelay, uMorphPrev);
  vec4 mv = modelViewMatrix * vec4(p, 1.);
  float since = uF - aBirth - uFly;
  float flash = step(0., since) * exp(-max(0., since) * 0.12);
  float sinceAppear = uF - aAppear;
  float pop = aAppear < aBirth - .5 ? clamp(sinceAppear / 7., 0., 1.) : 1.;
  float popFlash = aAppear < aBirth - .5 ? step(0., sinceAppear) * exp(-max(0., sinceAppear) * 0.16) : 0.;
  float hi = (aIndex == uHiNode) ? 1. : 0.;
  bool paper = aType > 5.5;
  float base = paper ? uPaper.x : aHub > 1.5 ? uSizes.x : aHub > .5 ? uSizes.y : uSizes.z;
  float cap = paper || aHub < .5 ? uMaxPx.z : aHub > 1.5 ? uMaxPx.x : uMaxPx.y;
  float sz = aSize * base;
  if (aMode > 1.5 && aHub > .5) { // a hub travels at the size of any other piece and grows into its place
    float g = sstep5(.42, 1., k);
    sz = mix(.85 * uSizes.z, sz, g); cap = mix(uMaxPx.z, cap, g);
  }
  float popE = 1. - pow(1. - pop, 3.);
  float s = sz * (0.2 + 0.8 * popE);
  float opened = aAppear < aBirth - .5 ? 1. - smoothstep(0., .35, k) : 0.; // a piece shown beside its paper before it flies
  float S = min(s * uScale / max(0.1, -mv.z), cap * (1. + uOpen * opened)) * uDpr * (1. + (flash * .5 + popFlash * .8) * uFlashAmt + hi * 1.4) * (1. + uOpen * opened);
  vSize = S / uDpr;
  vec4 c0 = projectionMatrix * mv;
  vec4 c1 = projectionMatrix * (modelViewMatrix * vec4(pp, 1.));
  vec2 hv = .5 * uViewport;
  vec2 s0 = c0.xy / c0.w * hv;
  vec2 s1 = c1.w > .01 ? c1.xy / c1.w * hv : s0;
  float L = length(s0 - s1);
  bool moving = L > .3;
  vec2 dir = moving ? (s0 - s1) / L : vec2(1., 0.);
  float R = .5 * S, Lh = moving ? .5 * L : 0.;
  vec2 mid = moving ? .5 * (s0 + s1) : s0;
  gl_Position = vec4((mid + dir * position.x * (Lh + R) + vec2(-dir.y, dir.x) * position.y * R) / hv * c0.w, c0.zw);
  vQ = vec2(position.x * (Lh + R), position.y * R);
  vLh = Lh; vR = R;
  vec3 col = aHub > .5 ? mix(uColors[int(aType)], uColors[0], uStem) : uColors[int(aType)] * (paper ? 1. : uLeafDim);
  if (uByCluster > .5) { // settle from the type colours into the colour of the node's cluster as it arrives
    vec3 cc = aCluster < -.5 ? vec3(.93, .92, .88) : uCluster[int(aCluster)];
    vec3 cn = paper ? uColors[6] : aHub > .5 ? mix(cc, vec3(1.), uStem) : cc * uLeafDim;
    col = mix(col, cn, aMode > 1.5 ? sstep5(.55, .95, k) : smoothstep(.15, .85, k));
  }
  col = mix(col, uTint, uTintAmt * clamp((uMorph - aDelay) / .55, 0., 1.)); // landing on the flow diagram: take its colour
  float inFocus = (aCluster == uFocusCluster || aHub > 1.5) ? 1. : 0.;
  float focus = mix(1., mix(0.16, 1.2, inFocus), uFocusAmt);
  float gold = (aCluster == uHiCluster && aType < 1.5) ? uHiAmt : 0.;
  col = mix(col, vec3(1., .74, .3), gold);
  float fog = 1. - smoothstep(uFogNear, uFogFar, -mv.z) * 0.85;
  vColor = col * focus * fog * mix(1., mix(.13, 1.25, inSel(aIndex)), uSelAmt) * (1. + gold * .2);
  vAlpha = step(aAppear, uF) * smoothstep(2.5, 6., -mv.z) * (aHub < .5 && !paper && aSeed > uKeep ? 0. : 1.);
  vFlash = ((flash * .6 + popFlash * .8) * uFlashAmt + hi) * fog;
  vHub = aHub;
  vType = aType;
}`;

// crisp lit beads (hubs catch a specular highlight); papers are small cards
const nodeFrag = /* glsl */ `
uniform float uBright; uniform float uAlpha; uniform float uShade; uniform float uSoft; uniform float uAdd; uniform vec2 uPaper; uniform float uRim; uniform float uFlat; uniform float uRing; uniform vec3 uBg;
varying vec3 vColor; varying float vAlpha; varying float vFlash; varying float vHub; varying float vType; varying float vSize;
varying vec2 vQ; varying float vLh; varying float vR;
void main(){
  float R = max(vR, 1e-3);
  vec2 q = vec2(sign(vQ.x) * max(abs(vQ.x) - vLh, 0.), -vQ.y) / R; // as gl_PointCoord * 2 - 1, from the nearest point of the path
  float blur = (3.1416 * R + vLh) / (3.1416 * R + 4. * vLh);      // a moving dot spreads its light along its streak
  vec3 c; float a;
  if (vType > 5.5) {
    float b = max(abs(q.x), abs(q.y));
    float aa = fwidth(b) * 1.5;
    float fill = 1. - smoothstep(.7 - aa, .7 + aa, b);
    c = vColor * uBright + vec3(vFlash * .7);
    a = fill * vAlpha * uAlpha * uPaper.y;
  } else {
    float r = length(q);
    float aa = fwidth(r) * 1.4;
    float core = 1. - smoothstep(1. - aa * 2., 1., r);
    float soft = exp(-r * r * 3.6) * (1. - smoothstep(.85, 1., r));
    a = mix(core, soft, uSoft) * vAlpha * uAlpha;
    if (uShade > .5) {
      vec3 n = vec3(q.x, -q.y, sqrt(max(0., 1. - r * r)));
      vec3 L = normalize(vec3(-.45, .62, .64));
      c = vColor * (.5 + .5 * max(0., dot(n, L))) * uBright + pow(max(0., dot(reflect(-L, n), vec3(0., 0., 1.))), 22.) * .3;
    } else {
      c = vColor * uBright * (1. + .35 * (1. - r) * (1. - uSoft) * (1. - uFlat));
    }
    // hubs as hollow rings, like the nodes of the product's flow diagram
    if (uRing > .5 && vHub > .5) {
      float w = min(.5, 2.6 / max(1., vSize));
      float stroke = smoothstep(1. - w - aa, 1. - w + aa, r);
      c = mix(uBg, c, stroke);
      a = core * vAlpha * uAlpha;
    }
    // a dark rim keeps overlapping dots apart (only where the dot is big enough to carry it)
    float rim = smoothstep(1. - uRim - aa, 1. - uRim + aa, r) * smoothstep(4.5, 8., vSize) * step(.001, uRim) * (1. - step(.5, uRing) * step(.5, vHub));
    c = mix(c, c * .12, rim);
    c += vec3(vFlash);
  }
  a *= blur;
  if (a < .008) discard;
  gl_FragColor = uAdd > .5 ? vec4(c * a, 1.) : vec4(c, a);
}`;

// edges: quadratic arcs that grow from their first endpoint, fading softly where they meet the nodes
const edgeVert = /* glsl */ `
${COMMON}
// both ends of an edge (position = a's target), packed to stay within the attribute limit
attribute vec4 aA1; attribute vec4 aA2; attribute vec4 aA3; attribute vec4 aA4; // a: source · birth, start of its paper · seed, dock · morph delay, flat · mode
attribute vec4 aB0; attribute vec4 aB1; attribute vec4 aB2; attribute vec4 aB3; attribute vec4 aB4; // b: target · t along the arc, then as for a
attribute vec4 aE1; // type * 3 + hub level of a and b, clusters of a and b
attribute vec4 aE2; // kind, edge birth, until, a * 4096 + b
uniform float uFocusCluster; uniform float uFocusAmt; uniform float uBridge; uniform float uGrow; uniform float uFogNear; uniform float uFogFar;
uniform float uHiCluster; uniform float uHiAmt; uniform float uEdgeFade; uniform vec4 uSel; uniform float uSelAmt; uniform vec3 uColors[7]; uniform float uEdgeGain; uniform vec3 uEdgeColor; uniform float uEdgeTint; uniform float uSpokes; uniform float uDpr;
uniform vec3 uCluster[12]; uniform float uByCluster; uniform float uKeep; uniform float uStraight; uniform vec3 uTint; uniform float uTintAmt;
varying vec3 vColor; varying float vAlpha;
float inSel(float i){ return (abs(i - uSel.x) < .5 || abs(i - uSel.y) < .5 || abs(i - uSel.z) < .5 || abs(i - uSel.w) < .5) ? 1. : 0.; }
void main(){
  vec2 aTypes = floor((aE1.xy + .5) / 3.), aHubs = aE1.xy - aTypes * 3., aClus = aE1.zw;
  float t = aB0.w, aKind = aE2.x, aEdgeBirth = aE2.y, aUntil = aE2.z, aCluster = aClus.x;
  float keep = ((aHubs.x > .5 || aTypes.x > 5.5 || aA2.w <= uKeep) && (aHubs.y > .5 || aTypes.y > 5.5 || aB2.w <= uKeep)) ? 1. : 0.;
  vec3 A = morphPos(nodeAt(aA1.xyz, position, aA2.xyz, aA3.xyz, aA1.w, aA2.w, aA4.w, uF), aA4.xyz, aA3.w);
  vec3 B = morphPos(nodeAt(aB1.xyz, aB0.xyz, aB2.xyz, aB3.xyz, aB1.w, aB2.w, aB4.w, uF), aB4.xyz, aB3.w);
  float g = clamp((uF - aEdgeBirth) / uGrow, 0., 1.);
  g = 1. - pow(1. - g, 3.);
  vec3 ctrl = arcCtrl(A, B);
  ctrl = mix(ctrl, (A + B) * .5, uStraight * (1. - smoothstep(2.5, 7., length(B - A)))); // short spokes run straight
  vec3 p = arcAt(A, ctrl, B, min(t, g));
  vec4 mv = modelViewMatrix * vec4(p, 1.);
  gl_Position = projectionMatrix * mv;
  float on = step(aEdgeBirth, uF) * (1. - smoothstep(aUntil, aUntil + 10., uF)) * keep;
  float fresh = exp(-max(0., uF - aEdgeBirth - uGrow) * 0.06) * on;
  // a paper's spokes are bright while it is a little constellation on the wall; as its pieces lift off they settle into
  // the graph's quiet paper → content lines, so only the pieces themselves are seen flying
  float settled = sstep5(0., .25, clamp((uF - aA1.w) / uFly, 0., 1.));
  float base = aKind > 3.5 ? mix(.4, .05 * uSpokes, settled) : aKind > 2.5 ? .4 : aKind > 1.5 ? .12 : aKind > .5 ? .08 : aKind > .2 ? .3 : aKind > .05 ? .016 : .12;
  base *= .12 + .88 * smoothstep(11., 3.5, length(B - A)); // long cross-cluster threads stay quiet
  vec3 col = mix(uEdgeColor, mix(uColors[int(aTypes.x) == 0 ? 2 : int(aTypes.x)], uColors[int(aTypes.y) == 0 ? 2 : int(aTypes.y)], t), uEdgeTint);
  if (uByCluster > .5 && (aKind < 2.5 || aKind > 3.5)) {
    vec3 ca = aClus.x < -.5 ? vec3(.93, .92, .88) : uCluster[int(aClus.x)];
    vec3 cb = aClus.y < -.5 ? vec3(.93, .92, .88) : uCluster[int(aClus.y)];
    vec3 cc = mix(uEdgeColor, mix(ca, cb, t), uEdgeTint);
    col = aKind > 3.5 ? mix(col, cc, settled) : cc;
  }
  if (aKind > 3.5 && uByCluster < .5) col = vec3(.86, .85, .82);
  col = mix(col, uTint, uTintAmt * uMorph);
  if (aKind > .5 && aKind < 1.5) { col = mix(col, vec3(1., .72, .3), uBridge); base *= 1. + uBridge * 1.6; }
  float hiC = aCluster == uHiCluster ? uHiAmt : 0.;
  col = mix(col, vec3(1., .74, .3), hiC);
  base *= 1. + hiC * 1.6;
  float focus = mix(1., aCluster == uFocusCluster ? 1.5 : 0.1, uFocusAmt);
  float fog = 1. - smoothstep(uFogNear, uFogFar, -mv.z) * 0.85;
  float prof = .3 + .7 * smoothstep(0., .22, t) * smoothstep(1., .78, t);
  float ia = floor(aE2.w / 4096. + 1e-4), ib = aE2.w - ia * 4096.;
  float selE = inSel(ia) * inSel(ib);
  vColor = col * (1. + fresh * 1.5) * fog * mix(1., 1. + selE * .5, uSelAmt);
  vAlpha = on * base * focus * uEdgeFade * prof * uEdgeGain * (1. + (uDpr - 1.) * .75) * mix(1., mix(.08, 4., selE), uSelAmt); // finer lines when supersampled
}`;

const edgeFrag = /* glsl */ `
uniform float uAlpha; uniform float uEdgeNormal;
varying vec3 vColor; varying float vAlpha;
void main(){ gl_FragColor = uEdgeNormal > .5 ? vec4(vColor, min(1., vAlpha * uAlpha)) : vec4(vColor * vAlpha * uAlpha, 1.); }`;

const SEG = 8; // segments per arc

/**
 * Build GPU buffers. All callbacks get (i, nodeRecord).
 *  source → start [x,y,z] (graph-local) · birth → frame the node starts flying · appear → frame it pops in (default birth)
 *  flat → morph target [x,y,z] (graph-local, unrotated) · delay → morph delay in [0, 0.45]
 *  extraEdges → [[a, b, kind, edgeBirth, until]] drawn in addition to the graph's own edges
 *  edgeBirth(a, b, kind, e, def) → the frame an edge starts to grow (def: edgeDelay + up to edgeJitter after both ends land)
 *  seedOf → per-node seed in [0, 1) (flight arcs; leaves above the look's `keep` are not drawn)
 *  modeOf (or easeOf) → 0: the node lifts off from rest; 1: it leaves already moving (eases out only); 2: it travels with
 *  its paper — group(i) → {grp, dock}: where the paper starts and where it lands (graph-local; dock unrotated)
 */
export const useGraphBuffers = ({graph = G, source, birth, appear, flat, delay, extraEdges = [], key, edgeDelay = 18, edgeJitter = 24, edgeBirth = null,
  seedOf = null, easeOf = null, modeOf = null, group = null}) => useMemo(() => {
  const N = graph.nodes.length;
  const pos = new Float32Array(N * 3), src = new Float32Array(N * 3), flt = new Float32Array(N * 3), grp = new Float32Array(N * 3), dock = new Float32Array(N * 3);
  const type = new Float32Array(N), size = new Float32Array(N), bth = new Float32Array(N), app = new Float32Array(N), dly = new Float32Array(N), mode = new Float32Array(N);
  const seed = new Float32Array(N), cl = new Float32Array(N), hub = new Float32Array(N), idx = new Float32Array(N);
  graph.nodes.forEach((n, i) => {
    const s0 = source(i, n), gr = group ? group(i, n) : null;
    pos.set([n[0], n[1], n[2]], i * 3);
    src.set(s0, i * 3);
    flt.set(flat ? flat(i, n) : [n[0], n[1], n[2]], i * 3);
    grp.set(gr ? gr.grp : s0, i * 3);
    dock.set(gr ? gr.dock : [n[0], n[1], n[2]], i * 3);
    type[i] = n[3]; size[i] = n[5]; bth[i] = birth(i, n); app[i] = appear ? appear(i, n) : bth[i];
    dly[i] = delay ? delay(i, n) : 0; seed[i] = seedOf ? seedOf(i, n) : hash(i * 1.37); cl[i] = n[4];
    mode[i] = modeOf ? modeOf(i, n) : easeOf ? easeOf(i, n) : 0;
    hub[i] = n[5] > 3 ? 2 : n[5] > 1.6 ? 1 : 0; idx[i] = i;
  });
  const ng = new THREE.InstancedBufferGeometry();
  ng.setAttribute('position', new THREE.Float32BufferAttribute([-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0], 3));
  ng.setIndex([0, 1, 2, 0, 2, 3]);
  const nA = new Float32Array(N * 4), nB = new Float32Array(N * 4), nC = new Float32Array(N * 2);
  for (let i = 0; i < N; i++) {
    nA.set([type[i], size[i], bth[i], seed[i]], i * 4);
    nB.set([cl[i], hub[i], idx[i], app[i]], i * 4);
    nC.set([dly[i], mode[i]], i * 2);
  }
  const nodeAttr = {aTgt: [pos, 3], aSrc: [src, 3], aFlat: [flt, 3], aGrp: [grp, 3], aDock: [dock, 3], aNodeA: [nA, 4], aNodeB: [nB, 4], aNodeC: [nC, 2]};
  Object.entries(nodeAttr).forEach(([k, [arr, s]]) => ng.setAttribute(k, new THREE.InstancedBufferAttribute(arr, s)));
  ng.instanceCount = N;

  const all = [
    ...graph.edges.map(([a0, b0, kind], e) => {
      const [a, b] = bth[a0] <= bth[b0] ? [a0, b0] : [b0, a0];
      const def = Math.max(bth[a], bth[b]) + 60 + edgeDelay + hash(e) * edgeJitter;
      return {a, b, kind, birth: edgeBirth ? edgeBirth(a, b, kind, e, def) : def, until: 1e6};
    }),
    ...extraEdges.map(([a, b, kind, eb, until]) => ({a, b, kind, birth: eb, until})),
  ];
  const E = all.length, V = E * SEG * 2;
  const buf = (k) => new Float32Array(V * k);
  const ep = buf(3), A1 = buf(4), A2 = buf(4), A3 = buf(4), A4 = buf(4), B0 = buf(4), B1 = buf(4), B2 = buf(4), B3 = buf(4), B4 = buf(4), E1 = buf(4), E2 = buf(4);
  let v = 0;
  const at3 = (arr, i) => [arr[i * 3], arr[i * 3 + 1], arr[i * 3 + 2]];
  all.forEach(({a, b, kind, birth: eb, until}) => {
    const k = kind === 0 && hub[a] >= 1 && hub[b] >= 1 ? 0.25 : kind === 0 && hub[a] === 0 && hub[b] === 0 ? 0.1 : kind; // skeleton · cross-links
    const ends = (i) => [[...at3(src, i), bth[i]], [...at3(grp, i), seed[i]], [...at3(dock, i), dly[i]], [...at3(flt, i), mode[i]]];
    const ea = ends(a), eb4 = ends(b);
    for (let sgm = 0; sgm < SEG; sgm++) {
      for (const t of [sgm / SEG, (sgm + 1) / SEG]) {
        ep.set(at3(pos, a), v * 3);
        A1.set(ea[0], v * 4); A2.set(ea[1], v * 4); A3.set(ea[2], v * 4); A4.set(ea[3], v * 4);
        B0.set([...at3(pos, b), t], v * 4); B1.set(eb4[0], v * 4); B2.set(eb4[1], v * 4); B3.set(eb4[2], v * 4); B4.set(eb4[3], v * 4);
        E1.set([type[a] * 3 + hub[a], type[b] * 3 + hub[b], cl[a], cl[b]], v * 4);
        E2.set([k, eb, until, a * 4096 + b], v * 4);
        v++;
      }
    }
  });
  const eg = new THREE.BufferGeometry();
  const edgeAttr = {position: [ep, 3], aA1: [A1, 4], aA2: [A2, 4], aA3: [A3, 4], aA4: [A4, 4], aB0: [B0, 4], aB1: [B1, 4], aB2: [B2, 4], aB3: [B3, 4], aB4: [B4, 4],
    aE1: [E1, 4], aE2: [E2, 4]};
  Object.entries(edgeAttr).forEach(([k, [arr, s]]) => eg.setAttribute(k, new THREE.BufferAttribute(arr, s)));

  return {ng, eg, births: bth};
}, [key]);

const makeUniforms = () => ({
  uF: {value: 0}, uFly: {value: 60}, uRot: {value: new THREE.Matrix3()}, uBreath: {value: 1}, uMorph: {value: 0}, uMorphPrev: {value: 0}, uBend: {value: 0.16},
  uSwirl: {value: 0}, uCompact: {value: 1}, uShutter: {value: 0.5}, uViewport: {value: new THREE.Vector2(1920, 1080)},
  uScale: {value: 260}, uFocusCluster: {value: -9}, uFocusAmt: {value: 0}, uHiNode: {value: -1},
  uHiCluster: {value: -9}, uHiAmt: {value: 0}, uEdgeFade: {value: 1}, uSel: {value: new THREE.Vector4(-9, -9, -9, -9)}, uSelAmt: {value: 0},
  uColors: {value: TYPE_COLORS.map((h) => new THREE.Color(h))}, uBright: {value: 1}, uAlpha: {value: 1},
  uSizes: {value: new THREE.Vector3(.8, .66, .6)}, uMaxPx: {value: new THREE.Vector3(44, 44, 44)}, uLeafDim: {value: 1}, uPaper: {value: new THREE.Vector2(.85, 1)},
  uShade: {value: 0}, uSoft: {value: 0}, uAdd: {value: 0}, uEdgeGain: {value: 1}, uEdgeColor: {value: new THREE.Color('#9fd6ce')}, uEdgeTint: {value: 1}, uStem: {value: 0}, uSpokes: {value: 1}, uDpr: {value: 1},
  uBridge: {value: 0}, uGrow: {value: 26}, uFogNear: {value: 20}, uFogFar: {value: 90},
  uCluster: {value: Array.from({length: 12}, () => new THREE.Color('#ffffff'))}, uByCluster: {value: 0}, uRim: {value: 0}, uFlat: {value: 0}, uEdgeNormal: {value: 0},
  uRing: {value: 0}, uBg: {value: new THREE.Color('#080a0b')}, uKeep: {value: 1}, uStraight: {value: 0}, uTint: {value: new THREE.Color('#6ee3d7')}, uTintAmt: {value: 0}, uFlashAmt: {value: 1}, uOpen: {value: 0},
});
const normalEdge = {transparent: true, depthWrite: false, depthTest: true, blending: THREE.NormalBlending};

const additive = {transparent: true, depthWrite: false, depthTest: true, blending: THREE.AdditiveBlending};
const solid = {transparent: true, depthWrite: true, depthTest: true, blending: THREE.NormalBlending};

/**
 * <Graph> — full graph render; all state is a pure function of the props.
 * rotY: rotation applied to targets. swirl: how far (radians) paths travelling with their paper bend around the axis;
 * compact: how small a paper's constellation draws in while it travels. shutter: motion blur, in frames.
 * morph: 0..1 → nodes move onto their flat layout (morphPrev: its value half a frame earlier, for motion blur).
 * hiCluster/hiAmt: light one cluster's findings gold.
 * sel/selAmt: up to four node indices stay lit (with the edges among them) while everything else dims.
 */
export const Graph = ({buffers, f, rotY = 0, rotX = 0, fly = 60, scale = 260, alpha = 1, edgeAlpha = 1, bridge = 0,
  focusCluster = -9, focusAmt = 0, hiNode = -1, bright = 1, breath = 1, position = [0, 0, 0], scaleAll = 1, grow = 26,
  fog = [20, 90], morph = 0, morphPrev = null, hiCluster = -9, hiAmt = 0, keepEdges = false, sel = null, selAmt = 0, bend = 0.16, look = LOOK, tint = null,
  swirl = 0, compact = 1, shutter = 0.5}) => {
  const {ng, eg} = buffers;
  const {gl} = useThree();
  const mats = useMemo(() => {
    const u = makeUniforms();
    const node = new THREE.ShaderMaterial({vertexShader: nodeVert, fragmentShader: nodeFrag, uniforms: u, ...solid});
    const nodeAdd = new THREE.ShaderMaterial({vertexShader: nodeVert, fragmentShader: nodeFrag, uniforms: u, ...additive});
    const edge = new THREE.ShaderMaterial({vertexShader: edgeVert, fragmentShader: edgeFrag, uniforms: {...u, uAlpha: {value: 1}}, ...additive});
    const edgeN = new THREE.ShaderMaterial({vertexShader: edgeVert, fragmentShader: edgeFrag, uniforms: edge.uniforms, ...normalEdge});
    return {u, node, nodeAdd, edge, edgeN};
  }, []);
  const {u} = mats;
  u.uF.value = f; u.uFly.value = fly; u.uScale.value = scale; u.uAlpha.value = alpha; u.uBridge.value = bridge;
  u.uFocusCluster.value = focusCluster; u.uFocusAmt.value = focusAmt; u.uHiNode.value = hiNode; u.uBright.value = bright; u.uBreath.value = breath;
  u.uGrow.value = grow; u.uFogNear.value = fog[0]; u.uFogFar.value = fog[1]; u.uMorph.value = morph; u.uMorphPrev.value = morphPrev ?? morph; u.uBend.value = bend;
  u.uSwirl.value = swirl; u.uCompact.value = compact; u.uShutter.value = shutter; gl.getDrawingBufferSize(u.uViewport.value);
  u.uHiCluster.value = hiCluster; u.uHiAmt.value = hiAmt; u.uSelAmt.value = selAmt;
  u.uSizes.value.set(...look.sizes); u.uMaxPx.value.set(...look.maxPx); u.uLeafDim.value = look.leafDim; u.uPaper.value.set(...look.paper);
  u.uShade.value = look.shade ? 1 : 0; u.uSoft.value = look.soft; u.uAdd.value = look.add ? 1 : 0;
  u.uEdgeGain.value = look.edge[0]; u.uEdgeTint.value = look.edge[1]; u.uEdgeColor.value.set(look.edge[2]);
  u.uStem.value = look.stem ?? 0; u.uSpokes.value = look.spokes ?? 1; u.uDpr.value = gl.getPixelRatio();
  look.palette.forEach((h, k) => u.uColors.value[k].set(h));
  u.uRing.value = look.ring ? 1 : 0; u.uFlashAmt.value = look.flash ?? 1; u.uOpen.value = look.open ?? 0; u.uTintAmt.value = tint ? 1 : 0; if (tint) u.uTint.value.set(tint); u.uKeep.value = look.keep ?? 1; u.uStraight.value = look.straight ?? 0;
  u.uByCluster.value = look.byCluster ? 1 : 0; u.uRim.value = look.rim ?? 0; u.uFlat.value = look.flat ?? 0; u.uEdgeNormal.value = look.edgeNormal ? 1 : 0;
  (look.clusters || []).forEach((h, k) => u.uCluster.value[k].set(h));
  u.uSel.value.set(...[0, 1, 2, 3].map((k) => (sel && sel[k] != null ? sel[k] : -9))); u.uEdgeFade.value = keepEdges ? 1 : 1 - Math.min(1, morph * 2.2);
  mats.edge.uniforms.uAlpha.value = alpha * edgeAlpha;
  const m3 = new THREE.Matrix4().makeRotationY(rotY).multiply(new THREE.Matrix4().makeRotationX(rotX));
  u.uRot.value.setFromMatrix4(m3);
  useLayoutEffect(() => () => { [mats.node, mats.nodeAdd, mats.edge, mats.edgeN].forEach((m) => m.dispose()); }, [mats]);
  return (
    <group position={position} scale={scaleAll}>
      <lineSegments geometry={eg} material={look.edgeNormal ? mats.edgeN : mats.edge} frustumCulled={false} />
      <mesh geometry={ng} material={look.add ? mats.nodeAdd : mats.node} frustumCulled={false} />
    </group>
  );
};

// JS mirror of the shader's final (arrived) position, for overlays
export const nodeWorld = (i, rotY = 0, rotX = 0, position = [0, 0, 0], scaleAll = 1, graph = G) => {
  const n = graph.nodes[i];
  const v = new THREE.Vector3(n[0], n[1], n[2]).applyMatrix4(new THREE.Matrix4().makeRotationY(rotY).multiply(new THREE.Matrix4().makeRotationX(rotX)));
  return [v.x * scaleAll + position[0], v.y * scaleAll + position[1], v.z * scaleAll + position[2]];
};
