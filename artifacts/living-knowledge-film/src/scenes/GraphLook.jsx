import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {Graph, useGraphBuffers, LOOKS} from '../three/Graph';
import {Post} from '../three/Post';
import {Rig} from '../three/rig';
import {EXT} from '../data/extGraph';
import {C} from '../lib/theme';

// Look-development sandbox: frame n % 10 picks a look (in LOOKS order), frames 0–9 the Act II living view, 10–19 closer,
// 20–29 centred wide.
const NAMES = Object.keys(LOOKS);
const GP = [0, 0, -9];
const Scene = ({f}) => {
  const buffers = useGraphBuffers({graph: EXT, source: (i, n) => [n[0], n[1], n[2]], birth: () => -1000, key: 'look-ext'});
  const look = LOOKS[NAMES[(f % 10) % NAMES.length]];
  const bloom = look.byCluster || look.ring ? 0 : 0.45; // the v11 looks carry no glow
  const view = Math.floor(f / 10);
  // view 0: the Act II living shot (graph left of the type column); view 1: closer; view 2: centred wide
  const pose = [{pos: [-11.5, 7.35, 19.65], look: [7.46, 0.3, -6.1], fov: 46, roll: 0.03}, {pos: [-7, 4, 8], look: [2, 0, -9], fov: 46, roll: 0.02},
    {pos: [Math.sin(0.6) * 31, 7, Math.cos(0.6) * 31 - 9], look: GP, fov: 44, roll: 0}][view] ?? {pos: [0, 0, 30], look: GP, fov: 44, roll: 0};
  return <>
    <color attach="background" args={[C.bg]} />
    <Rig pose={pose} />
    <Graph buffers={buffers} f={2000} scale={320} fog={[20, 72]} look={look} position={GP} rotY={0.25} />
    <Post bloom={bloom} threshold={0.72} smoothing={0.15} radius={0.4} vignette={0} grain={0.02} />
  </>;
};
export const GraphLook = () => {
  const f = useCurrentFrame();
  const {width, height} = useVideoConfig();
  return <AbsoluteFill style={{background: C.bg}}>
    <ThreeCanvas width={width} height={height} camera={{fov: 44, position: [0, 0, 30]}} gl={{antialias: false}}><Scene f={f} /></ThreeCanvas>
  </AbsoluteFill>;
};
