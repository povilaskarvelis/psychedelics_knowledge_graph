import React, {useMemo, useLayoutEffect} from 'react';
import * as THREE from 'three';
import {useThree} from '@react-three/fiber';
import {paperAtlas, ATLAS_COLS, ATLAS_ROWS} from '../lib/textures';

// Pieces of pages. Each instance is a rectangle of a page, drawn with the page's texture and lit like a page; once it has
// broken off it can round off into a dot of the graph, drawn exactly like the graph's nodes. Everything that moves is
// motion-blurred over a half-frame shutter: a piece of paper is averaged over the ground it swept (pieces still on their
// page are blurred as the whole page, so no seam opens between them), and a dot stretches along its path like a node.
const vert = /* glsl */ `
attribute vec3 iPos; attribute vec3 iPrev; attribute vec3 iAx; attribute vec3 iAy;
attribute vec4 iUV;   // the piece's rectangle on its page: u0, v0, u1, v1
attribute vec4 iCol;  // its colour, how far the highlighter has swept across it
attribute vec4 iMisc; // atlas page, drawn as a dot (0/1), corner rounding, alpha
attribute vec4 iDot;  // node size, pixel cap, square (paper) or round, how far it has taken its colour
attribute vec4 iPg;   // the page it is still part of, in the piece's coordinates (its own rectangle once it has left)
uniform vec2 uViewport; uniform float uDpr; uniform float uScale; uniform float uCols;
varying vec2 vLocal; varying vec2 vDl; varying vec4 vRect; varying vec2 vCell; varying vec4 vPg; varying vec4 vCol; varying vec4 vMisc; varying vec4 vDot;
varying vec2 vQ; varying float vLh; varying float vR; varying float vShade; varying float vSpec; varying float vDepth; varying float vSize;
void main(){
  vRect = iUV; vPg = iPg; vCol = iCol; vMisc = iMisc; vDot = iDot;
  vCell = vec2(mod(iMisc.x, uCols), floor(iMisc.x / uCols + 1e-3));
  vLocal = position.xy; vDl = vec2(0.);
  vQ = vec2(0.); vLh = 0.; vR = 1.; vShade = 1.; vSpec = 0.; vSize = 0.;
  if (iMisc.y < .5) {
    // its motion over the shutter in its own coordinates (the rectangle spans -1..1); the quad reaches back over the
    // ground it swept
    vec3 m = iPos - iPrev;
    vDl = vec2(dot(m, iAx) / max(dot(iAx, iAx), 1e-8), dot(m, iAy) / max(dot(iAy, iAy), 1e-8));
    vLocal = mix(min(vec2(-1.), -1. - vDl) - .02, max(vec2(1.), 1. - vDl) + .02, position.xy * .5 + .5); // a hair over, so no crack opens
    vec3 wp = iPos + iAx * vLocal.x + iAy * vLocal.y;
    vec4 mv = viewMatrix * vec4(wp, 1.);
    gl_Position = projectionMatrix * mv;
    vec3 n = normalize(cross(iAx, iAy));
    vShade = .5 + .5 * abs(dot(n, normalize(vec3(.35, .55, .75))));
    vSpec = pow(abs(dot(n, normalize(normalize(vec3(-.5, .8, .4)) + normalize(cameraPosition - wp)))), 60.);
    vDepth = -mv.z;
  } else {
    vec4 mv = viewMatrix * vec4(iPos, 1.);
    vec4 c0 = projectionMatrix * mv, c1 = projectionMatrix * (viewMatrix * vec4(iPrev, 1.));
    float S = min(iDot.x * uScale / max(.1, -mv.z), iDot.y) * uDpr;
    vec2 hv = .5 * uViewport;
    vec2 s0 = c0.xy / c0.w * hv, s1 = c1.w > .01 ? c1.xy / c1.w * hv : s0;
    float L = length(s0 - s1);
    bool moving = L > .3;
    vec2 dir = moving ? (s0 - s1) / L : vec2(1., 0.);
    float R = .5 * S, Lh = moving ? .5 * L : 0.;
    vec2 mid = moving ? .5 * (s0 + s1) : s0;
    gl_Position = vec4((mid + dir * position.x * (Lh + R) + vec2(-dir.y, dir.x) * position.y * R) / hv * c0.w, c0.zw);
    vQ = vec2(position.x * (Lh + R), position.y * R); vLh = Lh; vR = R;
    vDepth = -mv.z; vSize = S / uDpr;
  }
}`;

const frag = /* glsl */ `
uniform sampler2D uMap; uniform vec3 uBg; uniform vec2 uFog; uniform vec2 uDotFog; uniform float uBright; uniform float uRim;
uniform float uCols; uniform float uRows;
varying vec2 vLocal; varying vec2 vDl; varying vec4 vRect; varying vec2 vCell; varying vec4 vPg; varying vec4 vCol; varying vec4 vMisc; varying vec4 vDot;
varying vec2 vQ; varying float vLh; varying float vR; varying float vShade; varying float vSpec; varying float vDepth; varying float vSize;
float edge(float lo, float hi, float x, float aa) { return smoothstep(lo - aa, lo + aa, x) * (1. - smoothstep(hi - aa, hi + aa, x)); }
void main(){
  vec3 c; float a;
  float dotFog = 1. - smoothstep(uDotFog.x, uDotFog.y, vDepth) * .85; // as the graph fogs its nodes
  if (vMisc.y < .5) {
    float rr = vMisc.z; // 0: a square-cornered piece of paper → 1: round
    vec2 px = fwidth(vLocal) + 1e-5, fw = px * .6;
    float front = -1.15 + 2.3 * vCol.w;
    vec2 cells = vec2(uCols, uRows), uv0 = vec2(vCell.x, uRows - 1. - vCell.y);
    vec2 uvB = (mix(vRect.xy, vRect.zw, vLocal * .5 + .5) + uv0) / cells, gx = dFdx(uvB), gy = dFdy(uvB);
    // one sample per pixel or so of travel, dithered per pixel, so the blur is smooth rather than a row of copies
    int n = int(clamp(ceil(length(vDl / px) / 1.2), 4., 48.));
    float jit = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(.06711056, .00583715))));
    vec3 acc = vec3(0.); float cov = 0., found = 0., own = 0.;
    for (int k = 0; k < 48; k++) { // where this point was on the piece over the shutter
      if (k >= n) break;
      vec2 l = vLocal + vDl * ((float(k) + jit) / float(n));
      float inPage = edge(vPg.x, vPg.z, l.x, fw.x) * edge(vPg.y, vPg.w, l.y, fw.y);
      float d = length(max(abs(l) - (1. - rr), 0.)) / max(rr, 1e-3);
      float s = rr > .001 ? 1. - smoothstep(1. - max(fw.x, fw.y) * 2. / rr, 1., d) : inPage;
      // the first moment the point is on the page decides which piece draws it, so neighbours never overlap
      float first = (1. - found) * step(.5, inPage);
      own += first * step(max(abs(l.x), abs(l.y)), 1.0003);
      found = max(found, step(.5, inPage));
      vec3 t = textureGrad(uMap, (mix(vRect.xy, vRect.zw, l * .5 + .5) + uv0) / cells, gx, gy).rgb * uBright * vShade + vSpec * .35;
      // a highlighter sweeps across the piece in its colour
      t = mix(t, t * vCol.rgb * 1.25, (1. - smoothstep(front - .12, front + .12, l.x)) * .85);
      acc += t * s; cov += s;
    }
    if (own < .5 || cov < 1e-4) discard;
    c = acc / cov;
    a = cov / float(n) * vMisc.w;
    c = mix(c, uBg, smoothstep(uFog.x, uFog.y, vDepth));
    c = mix(c, vCol.rgb * dotFog, vDot.w); // then it takes the colour as it becomes a node
  } else {
    float R = max(vR, 1e-3);
    vec2 q = vec2(sign(vQ.x) * max(abs(vQ.x) - vLh, 0.), -vQ.y) / R;
    c = vCol.rgb * dotFog;
    if (vDot.z > .5) {
      float b = max(abs(q.x), abs(q.y)), aa = fwidth(b) * 1.5;
      a = (1. - smoothstep(.7 - aa, .7 + aa, b)) * vMisc.w;
    } else {
      float r = length(q), aa = fwidth(r) * 1.4;
      a = (1. - smoothstep(1. - aa * 2., 1., r)) * vMisc.w;
      c = mix(c, c * .12, smoothstep(1. - uRim - aa, 1. - uRim + aa, r) * smoothstep(4.5, 8., vSize) * step(.001, uRim));
    }
    a *= (3.1416 * R + vLh) / (3.1416 * R + 4. * vLh);
  }
  if (a < .008) discard;
  gl_FragColor = vec4(c, a);
}`;

const ATTRS = {iPos: 3, iPrev: 3, iAx: 3, iAy: 3, iUV: 4, iCol: 4, iMisc: 4, iDot: 4, iPg: 4};
const OWN = [-1, -1, 1, 1];

// layout(i, o) fills o: pos, prev (half a frame earlier), ax, ay (half extents), uv [u0, v0, u1, v1], col [r, g, b],
// wash, page (atlas variant), pg (the page rectangle in the piece's coordinates while it is still part of it), dot,
// round, alpha, size, cap, paper, solid. o.alpha = 0 hides the piece.
export const Shards = ({count, layout, fog = [20, 90], dotFog = [20, 72], bright = 0.8, scale = 320, rim = 0.3}) => {
  const {gl} = useThree();
  const {geo, mat, mesh} = useMemo(() => {
    const g = new THREE.InstancedBufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute([-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0], 3));
    g.setIndex([0, 1, 2, 0, 2, 3]);
    Object.entries(ATTRS).forEach(([k, s]) => g.setAttribute(k, new THREE.InstancedBufferAttribute(new Float32Array(count * s), s)));
    g.instanceCount = count;
    const m = new THREE.ShaderMaterial({vertexShader: vert, fragmentShader: frag, transparent: true, depthWrite: false, depthTest: true,
      uniforms: {uMap: {value: paperAtlas()}, uCols: {value: ATLAS_COLS}, uRows: {value: ATLAS_ROWS}, uBg: {value: new THREE.Color('#080a0b')},
        uFog: {value: new THREE.Vector2()}, uDotFog: {value: new THREE.Vector2()}, uBright: {value: 0.8}, uRim: {value: 0.3},
        uViewport: {value: new THREE.Vector2(1920, 1080)}, uDpr: {value: 1}, uScale: {value: 320}}});
    const ms = new THREE.Mesh(g, m);
    ms.frustumCulled = false;
    ms.renderOrder = 10; // after the graph, so a page covers what is behind it
    return {geo: g, mat: m, mesh: ms};
  }, [count]);
  const o = useMemo(() => ({}), []);
  const A = Object.fromEntries(Object.keys(ATTRS).map((k) => [k, geo.getAttribute(k)]));
  for (let i = 0; i < count; i++) {
    o.alpha = 0; o.pg = OWN;
    layout(i, o);
    if (o.alpha <= 0) { A.iMisc.array[i * 4 + 3] = 0; A.iPos.array.set([0, 0, 0], i * 3); A.iPrev.array.set([0, 0, 0], i * 3); continue; }
    A.iPos.array.set(o.pos, i * 3); A.iPrev.array.set(o.prev, i * 3); A.iAx.array.set(o.ax, i * 3); A.iAy.array.set(o.ay, i * 3);
    A.iUV.array.set(o.uv, i * 4); A.iPg.array.set(o.pg, i * 4);
    A.iCol.array.set([o.col[0], o.col[1], o.col[2], o.wash], i * 4);
    A.iMisc.array.set([o.page, o.dot, o.round, o.alpha], i * 4);
    A.iDot.array.set([o.size, o.cap, o.paper, o.solid], i * 4);
  }
  Object.values(A).forEach((at) => { at.needsUpdate = true; });
  mat.uniforms.uFog.value.set(...fog); mat.uniforms.uDotFog.value.set(...dotFog); mat.uniforms.uBright.value = bright; mat.uniforms.uRim.value = rim;
  mat.uniforms.uScale.value = scale; mat.uniforms.uDpr.value = gl.getPixelRatio(); gl.getDrawingBufferSize(mat.uniforms.uViewport.value);
  useLayoutEffect(() => () => { geo.dispose(); mat.dispose(); }, [geo, mat]);
  return <primitive object={mesh} />;
};
