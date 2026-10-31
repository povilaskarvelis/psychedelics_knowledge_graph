import React from 'react';
import {AbsoluteFill, Sequence, Audio, staticFile} from 'remotion';
import {Genesis} from './Genesis';
import {ActThree as Product} from './Product';
import {ActFour as Finale} from './Finale';
import {C} from '../lib/theme';

// The calm cut: one idea, one move — the paper, buried in prose, extracted and connected into a living graph; the first
// one we built (psychedelic science); every field. 90 bpm: 20 frames = 1 beat, 80 = 1 bar.
export const TC = {genesis: [0, 960], product: [960, 960], finale: [1920, 400]};
export const CALM_LENGTH = TC.finale[0] + TC.finale[1];
export const CalmFilm = ({withAudio = true}) => (
  <AbsoluteFill style={{background: C.bg}}>
    <Sequence from={TC.genesis[0]} durationInFrames={TC.genesis[1]}><Genesis /></Sequence>
    <Sequence from={TC.product[0]} durationInFrames={TC.product[1]}><Product /></Sequence>
    <Sequence from={TC.finale[0]} durationInFrames={TC.finale[1]}><Finale /></Sequence>
    {withAudio && <Audio src={staticFile('audio/score-calm.wav')} />}
  </AbsoluteFill>
);
