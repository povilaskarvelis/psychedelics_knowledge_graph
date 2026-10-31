import {useEffect, useMemo} from 'react';
import {useThree, useFrame} from '@react-three/fiber';
import * as THREE from 'three';
import {
  EffectComposer, RenderPass, EffectPass, BloomEffect, VignetteEffect,
  DepthOfFieldEffect, ChromaticAberrationEffect, NoiseEffect, BlendFunction,
} from 'postprocessing';

// Direct postprocessing pipeline (the R3F wrapper doesn't render under Remotion's
// frameloop="never"). Mounted inside a ThreeCanvas; takes over rendering.
export const Post = ({bloom = 1.1, threshold = 0.2, smoothing = 0.35, radius = 0.8, vignette = 0.55,
  dof = null, ca = 0, grain = 0.05, seed = 0}) => {
  const {gl, scene, camera, size} = useThree();
  const fx = useMemo(() => {
    gl.toneMapping = THREE.NoToneMapping;
    const c = new EffectComposer(gl, {frameBufferType: THREE.HalfFloatType, multisampling: 4});
    c.addPass(new RenderPass(scene, camera));
    let dofFx = null;
    if (dof) {
      dofFx = new DepthOfFieldEffect(camera, {focusDistance: dof.distance, focusRange: dof.range, bokehScale: dof.bokeh ?? 3, resolutionScale: 0.75});
      c.addPass(new EffectPass(camera, dofFx));
    }
    const b = new BloomEffect({intensity: bloom, luminanceThreshold: threshold, luminanceSmoothing: smoothing, mipmapBlur: true, radius});
    const v = new VignetteEffect({darkness: vignette, offset: 0.28});
    const n = new NoiseEffect({blendFunction: BlendFunction.OVERLAY, premultiply: false});
    n.blendMode.opacity.value = grain;
    c.addPass(new EffectPass(camera, b, v, n));
    const caFx = new ChromaticAberrationEffect({offset: new THREE.Vector2(0, 0), radialModulation: true, modulationOffset: 0.2});
    c.addPass(new EffectPass(camera, caFx));
    return {c, b, v, dofFx, caFx, n};
  }, [gl, scene, camera, !!dof]);
  useEffect(() => { fx.c.setSize(size.width, size.height); }, [fx, size]);
  useEffect(() => () => fx.c.dispose(), [fx]);
  // live parameters
  fx.b.intensity = bloom;
  fx.b.luminanceMaterial.threshold = threshold;
  fx.v.darkness = vignette;
  fx.n.blendMode.opacity.value = grain;
  fx.caFx.offset.set(ca * 0.0035, ca * 0.0022);
  if (fx.dofFx && dof) {
    fx.dofFx.cocMaterial.focusDistance = dof.distance;
    fx.dofFx.cocMaterial.focusRange = dof.range;
    fx.dofFx.bokehScale = dof.bokeh ?? 3;
  }
  useFrame(() => { fx.c.render(0.033); }, 1);
  return null;
};
