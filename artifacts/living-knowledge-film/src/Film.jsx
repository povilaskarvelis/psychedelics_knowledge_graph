import React from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame, interpolate, Audio, staticFile} from 'remotion';
import {ActOne} from './scenes/ActOne';
import {Thesis} from './scenes/Thesis';
import {ActTwo} from './scenes/ActTwo';
import {ActThree} from './scenes/ActThree';
import {ActFour} from './scenes/ActFour';
import {C} from './lib/theme';

// Master timeline (frames @30fps). Overlaps are crossfades.
export const T = {
  one: [0, 1020],
  thesis: [1020, 120],
  two: [1140, 600],
  three: [1740, 1020],
  four: [2760, 420],
};
export const FILM_LENGTH = T.four[0] + T.four[1];

const Fade = ({children, from, dur, inF = 0, outF = 0}) => {
  const f = useCurrentFrame();
  const o = Math.min(inF ? interpolate(f, [from, from + inF], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) : 1,
    outF ? interpolate(f, [from + dur - outF, from + dur], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) : 1);
  return <AbsoluteFill style={{opacity: o}}>{children}</AbsoluteFill>;
};

export const Film = ({withAudio = true}) => (
  <AbsoluteFill style={{background: C.bg}}>
    <Sequence from={T.one[0]} durationInFrames={T.one[1]}><ActOne /></Sequence>
    <Sequence from={T.thesis[0]} durationInFrames={T.thesis[1]}><Thesis /></Sequence>
    <Sequence from={T.two[0]} durationInFrames={T.two[1]}><ActTwo /></Sequence>
    <Sequence from={T.three[0]} durationInFrames={T.three[1]}><ActThree /></Sequence>
    <Sequence from={T.four[0]} durationInFrames={T.four[1]}><ActFour /></Sequence>
    {withAudio && <Audio src={staticFile('audio/score.wav')} />}
  </AbsoluteFill>
);
