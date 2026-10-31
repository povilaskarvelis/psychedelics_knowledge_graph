import React, {useMemo, useLayoutEffect} from 'react';
import * as THREE from 'three';

const vert = /* glsl */ `
attribute vec3 aColor; attribute float aSize; attribute float aAlpha;
uniform float uScale;
varying vec3 vColor; varying float vAlpha;
void main(){
  vec4 mv = modelViewMatrix * vec4(position, 1.);
  gl_PointSize = aSize * uScale / max(0.05, -mv.z);
  gl_Position = projectionMatrix * mv;
  vColor = aColor; vAlpha = aAlpha;
}`;
const frag = /* glsl */ `
varying vec3 vColor; varying float vAlpha;
void main(){
  float d = length(gl_PointCoord - .5) * 2.;
  if (d > 1. || vAlpha < 0.002) discard;
  float c = smoothstep(.5, 0., d) * 1.6 + exp(-d * d * 4.) * .5;
  gl_FragColor = vec4(vColor * c * vAlpha, 1.);
}`;

/** CPU-driven point cloud. update(i, o) sets o.x,o.y,o.z,o.r,o.g,o.b,o.size,o.alpha. */
export const Particles = ({count, update, scale = 200}) => {
  const {geo, mat} = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(new Float32Array(count * 3), 3));
    g.setAttribute('aSize', new THREE.BufferAttribute(new Float32Array(count), 1));
    g.setAttribute('aAlpha', new THREE.BufferAttribute(new Float32Array(count), 1));
    const m = new THREE.ShaderMaterial({vertexShader: vert, fragmentShader: frag, uniforms: {uScale: {value: scale}},
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending});
    return {geo: g, mat: m};
  }, [count]);
  const P = geo.getAttribute('position').array, Cc = geo.getAttribute('aColor').array, S = geo.getAttribute('aSize').array, A = geo.getAttribute('aAlpha').array;
  const o = {};
  for (let i = 0; i < count; i++) {
    o.x = 0; o.y = 0; o.z = 0; o.r = 1; o.g = 1; o.b = 1; o.size = 1; o.alpha = 0;
    update(i, o);
    P[i * 3] = o.x; P[i * 3 + 1] = o.y; P[i * 3 + 2] = o.z;
    Cc[i * 3] = o.r; Cc[i * 3 + 1] = o.g; Cc[i * 3 + 2] = o.b;
    S[i] = o.size; A[i] = o.alpha;
  }
  ['position', 'aColor', 'aSize', 'aAlpha'].forEach((k) => (geo.getAttribute(k).needsUpdate = true));
  mat.uniforms.uScale.value = scale;
  useLayoutEffect(() => () => { geo.dispose(); mat.dispose(); }, [geo, mat]);
  return <points geometry={geo} material={mat} frustumCulled={false} />;
};

// Luminous sheet of light in the YZ plane at x = 0
const sheetVert = /* glsl */ `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.); }`;
const sheetFrag = /* glsl */ `
uniform float uT; uniform float uOpen; uniform vec3 uColor; uniform float uIntensity; uniform float uWidth; uniform float uZ; uniform float uFocusZ; uniform float uSpread;
varying vec2 vUv;
void main(){
  float y = abs(vUv.y - .5) * 2.;
  float open = smoothstep(uOpen, uOpen - .06, y);
  float fall = pow(max(0., 1. - y), 2.2);
  // world z along the sheet
  float z = uZ - (vUv.x - .5) * uWidth;
  float dz = (z - uFocusZ) / uSpread;
  float focus = exp(-dz * dz);
  float ends = smoothstep(0., .12, vUv.x) * smoothstep(1., .75, vUv.x);
  float stri = .7 + .3 * sin(z * 9. + uT * .05) * sin(z * 3.1 - uT * .03);
  float eq = (y - uOpen + .015) * 60.;
  float edge = exp(-eq * eq) * step(.02, uOpen);
  float a = (fall * stri * (.035 + focus) + edge * (.25 + focus)) * open * ends;
  gl_FragColor = vec4(uColor * a * uIntensity, 1.);
}`;

export const LightSheet = ({f, open = 1, intensity = 1, width = 44, height = 13, z = -10, focusZ = 0, spread = 1.2, x = 0}) => {
  const mat = useMemo(() => new THREE.ShaderMaterial({vertexShader: sheetVert, fragmentShader: sheetFrag,
    uniforms: {uT: {value: 0}, uOpen: {value: 1}, uColor: {value: new THREE.Color('#6ee3d7')}, uIntensity: {value: 1}, uWidth: {value: 44}, uZ: {value: -10}, uFocusZ: {value: 0}, uSpread: {value: 1.2}},
    transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending}), []);
  mat.uniforms.uT.value = f; mat.uniforms.uOpen.value = open; mat.uniforms.uIntensity.value = intensity;
  mat.uniforms.uWidth.value = width; mat.uniforms.uZ.value = z; mat.uniforms.uFocusZ.value = focusZ; mat.uniforms.uSpread.value = spread;
  return (
    <mesh position={[x, 0, z]} rotation={[0, Math.PI / 2, 0]} material={mat}>
      <planeGeometry args={[width, height]} />
    </mesh>
  );
};
