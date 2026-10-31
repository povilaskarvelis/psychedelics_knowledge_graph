import React, {useMemo, useLayoutEffect} from 'react';
import * as THREE from 'three';
import {paperAtlas, ATLAS_COLS, ATLAS_ROWS, PAPER_ASPECT} from '../lib/textures';

export const NOISE_GLSL = /* glsl */ `
float h21(vec2 p){ p = fract(p*vec2(123.34, 456.21)); p += dot(p, p+45.32); return fract(p.x*p.y); }
float vnoise(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
  return mix(mix(h21(i),h21(i+vec2(1,0)),f.x), mix(h21(i+vec2(0,1)),h21(i+vec2(1,1)),f.x), f.y); }
float fbm(vec2 p){ float a=.5, s=0.; for(int i=0;i<4;i++){ s+=a*vnoise(p); p*=2.03; a*=.5;} return s; }
`;

const vert = /* glsl */ `
attribute float aVar;
attribute vec4 aState;   // x alpha, y glow, z desat/age, w border glow
varying vec2 vUv; varying vec2 vLocal; varying vec4 vState; varying float vShade; varying float vSpec; varying float vDepth; varying vec3 vWorld;
uniform float uCols; uniform float uRows;
void main(){
  float col = mod(aVar, uCols);
  float row = floor(aVar / uCols);
  vLocal = uv;
  vUv = vec2((uv.x + col) / uCols, (uv.y + (uRows - 1. - row)) / uRows);
  vState = aState;
  vec4 wp = modelMatrix * instanceMatrix * vec4(position, 1.);
  vWorld = wp.xyz;
  vec3 n = normalize(mat3(modelMatrix) * mat3(instanceMatrix) * vec3(0., 0., 1.));
  vec3 viewDir = normalize(cameraPosition - wp.xyz);
  float ndl = dot(n, normalize(vec3(0.35, 0.55, 0.75)));
  vShade = 0.5 + 0.5 * abs(ndl);
  vec3 h = normalize(normalize(vec3(-0.5, 0.8, 0.4)) + viewDir);
  vSpec = pow(abs(dot(n, h)), 60.);
  vec4 mv = viewMatrix * wp;
  vDepth = -mv.z;
  gl_Position = projectionMatrix * mv;
}`;

const frag = /* glsl */ `
uniform sampler2D uMap; uniform vec3 uBg; uniform vec2 uFog; uniform vec3 uGlow; uniform vec3 uEdge;
uniform float uBright; uniform float uPlaneX; uniform float uDissolve; uniform float uTime; uniform float uDir;
uniform sampler2D uReveal; uniform float uRevealOn; uniform float uWrite; uniform vec3 uPaper;
varying vec2 vUv; varying vec2 vLocal; varying vec4 vState; varying float vShade; varying float vSpec; varying float vDepth; varying vec3 vWorld;
${NOISE_GLSL}
void main(){
  float alpha = vState.x;
  if (alpha < 0.003) discard;
  vec3 c = gl_FrontFacing ? texture2D(uMap, vUv).rgb : vec3(0.62, 0.6, 0.57);
  // write-on: ink appears in writing order
  if (uRevealOn > .5 && gl_FrontFacing) {
    float ord = texture2D(uReveal, vUv).r;
    if (ord > 0.004 && ord > uWrite) c = uPaper;
  }
  c *= uBright * vShade;
  c += vSpec * 0.35;
  // age: drain colour, darken, warm slightly
  float g = dot(c, vec3(0.299, 0.587, 0.114));
  c = mix(c, vec3(g) * vec3(0.95, 0.9, 0.82) * 0.55, vState.z);
  // edge glow (selection) + overall glow (arrival flash)
  vec2 e = min(vLocal, 1. - vLocal);
  float edge = 1. - smoothstep(0.0, 0.025, min(e.x * ${PAPER_ASPECT.toFixed(3)}, e.y));
  c += uGlow * vState.y * (0.6 + 2.2 * edge);
  c += uEdge * vState.w * edge * 3.;
  // dissolve through a plane of light at world x = uPlaneX
  if (uDissolve > 0.5) {
    float n = fbm(vLocal * vec2(9., 12.)) * 0.22;
    float d = uDir * (vWorld.x - uPlaneX) + n - 0.11;
    if (d > 0.) discard;
    float burn = 1. - smoothstep(0., 0.06, -d);
    c = mix(c, vec3(0.43, 0.89, 0.84) * 1.5, burn);
  }
  // fog to background
  float fog = smoothstep(uFog.x, uFog.y, vDepth);
  c = mix(c, uBg, fog);
  c = mix(uBg, c, alpha);
  gl_FragColor = vec4(c, 1.);
}`;

export const makePaperMaterial = ({map, cols = ATLAS_COLS, rows = ATLAS_ROWS, fog = [30, 120], bright = 0.82, glow = '#f1b74b', edge = '#6ee3d7'}) =>
  new THREE.ShaderMaterial({
    vertexShader: vert,
    fragmentShader: frag,
    side: THREE.DoubleSide,
    uniforms: {
      uMap: {value: map},
      uCols: {value: cols},
      uRows: {value: rows},
      uBg: {value: new THREE.Color('#080a0b')},
      uFog: {value: new THREE.Vector2(...fog)},
      uGlow: {value: new THREE.Color(glow)},
      uEdge: {value: new THREE.Color(edge)},
      uBright: {value: bright},
      uPlaneX: {value: 0},
      uDissolve: {value: 0},
      uDir: {value: 1},
      uReveal: {value: null},
      uRevealOn: {value: 0},
      uWrite: {value: 1},
      uPaper: {value: new THREE.Color('#efebe3')},
      uTime: {value: 0},
    },
  });

const m4 = new THREE.Matrix4();
const q = new THREE.Quaternion();
const eul = new THREE.Euler();
const pv = new THREE.Vector3();
const sv = new THREE.Vector3();

// layout(i, o) must set o.x,o.y,o.z,o.rx,o.ry,o.rz,o.s,o.alpha,o.glow,o.age,o.edge
export const PaperField = ({count, layout, variant = (i) => i % (ATLAS_COLS * ATLAS_ROWS), fog, bright, dissolveX = null, dissolveDir = 1, map, cols, rows, glow, edge, reveal = null, write = 1}) => {
  const {geo, mat, mesh} = useMemo(() => {
    const g = new THREE.PlaneGeometry(PAPER_ASPECT, 1);
    const mt = makePaperMaterial({map: map || paperAtlas(), cols, rows, fog, bright, glow, edge});
    const ms = new THREE.InstancedMesh(g, mt, count);
    ms.frustumCulled = false;
    const vars = new Float32Array(count);
    for (let i = 0; i < count; i++) vars[i] = variant(i);
    g.setAttribute('aVar', new THREE.InstancedBufferAttribute(vars, 1));
    g.setAttribute('aState', new THREE.InstancedBufferAttribute(new Float32Array(count * 4), 4));
    return {geo: g, mat: mt, mesh: ms};
  }, [count]);

  const o = useMemo(() => ({}), []);
  const st = geo.getAttribute('aState');
  for (let i = 0; i < count; i++) {
    o.x = 0; o.y = 0; o.z = 0; o.rx = 0; o.ry = 0; o.rz = 0; o.s = 1; o.alpha = 1; o.glow = 0; o.age = 0; o.edge = 0;
    layout(i, o);
    eul.set(o.rx, o.ry, o.rz);
    q.setFromEuler(eul);
    pv.set(o.x, o.y, o.z);
    sv.set(o.s, o.s, o.s);
    m4.compose(pv, q, sv);
    mesh.setMatrixAt(i, m4);
    st.array[i * 4] = o.alpha;
    st.array[i * 4 + 1] = o.glow;
    st.array[i * 4 + 2] = o.age;
    st.array[i * 4 + 3] = o.edge;
  }
  mesh.instanceMatrix.needsUpdate = true;
  st.needsUpdate = true;
  if (fog) mat.uniforms.uFog.value.set(fog[0], fog[1]);
  if (bright != null) mat.uniforms.uBright.value = bright;
  mat.uniforms.uDissolve.value = dissolveX == null ? 0 : 1;
  mat.uniforms.uPlaneX.value = dissolveX ?? 0;
  mat.uniforms.uDir.value = dissolveDir;
  mat.uniforms.uRevealOn.value = reveal ? 1 : 0;
  if (reveal) mat.uniforms.uReveal.value = reveal;
  mat.uniforms.uWrite.value = write;
  useLayoutEffect(() => () => { geo.dispose(); mat.dispose(); }, [geo, mat]);
  return <primitive object={mesh} />;
};
