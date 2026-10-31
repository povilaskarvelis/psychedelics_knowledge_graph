import {useEffect, useMemo} from 'react';
import {useThree, useFrame} from '@react-three/fiber';
import * as THREE from 'three';
import {EffectComposer, RenderPass, EffectPass, BloomEffect, VignetteEffect, KernelSize} from 'postprocessing';

// Direct postprocessing pipeline; takes over R3F's render when mounted.
export const Post = ({bloom = 1.2, threshold = 0.15, smoothing = 0.3, radius = 0.75, vignette = 0.55}) => {
  const {gl, scene, camera, size} = useThree();
  const composer = useMemo(() => {
    const c = new EffectComposer(gl, {frameBufferType: THREE.HalfFloatType, multisampling: 4});
    c.addPass(new RenderPass(scene, camera));
    const b = new BloomEffect({intensity: bloom, luminanceThreshold: threshold, luminanceSmoothing: smoothing, mipmapBlur: true, radius});
    c.addPass(new EffectPass(camera, b, new VignetteEffect({darkness: vignette, offset: 0.3})));
    c.bloom = b;
    return c;
  }, [gl, scene, camera]);
  useEffect(() => { composer.setSize(size.width, size.height); }, [composer, size]);
  useEffect(() => { composer.bloom.intensity = bloom; }, [composer, bloom]);
  useEffect(() => () => composer.dispose(), [composer]);
  useFrame(() => { composer.render(); }, 1);
  return null;
};
