import React from 'react';
import {Composition} from 'remotion';
import {ActOne} from './scenes/ActOne';
import {ActTwo} from './scenes/ActTwo';
import {ActThree} from './scenes/ActThree';
import {ActFour} from './scenes/ActFour';
import {Thesis} from './scenes/Thesis';
import {Film, FILM_LENGTH} from './Film';
import {GraphLook} from './scenes/GraphLook';
import {Pages} from './scenes/Pages';

const V = {fps: 30, width: 1920, height: 1080};
export const Root = () => <>
  <Composition id="LivingKnowledge" component={Film} durationInFrames={FILM_LENGTH} {...V} defaultProps={{withAudio: true}} />
  <Composition id="LivingKnowledgeSilent" component={Film} durationInFrames={FILM_LENGTH} {...V} defaultProps={{withAudio: false}} />
  <Composition id="ActOne" component={ActOne} durationInFrames={1020} {...V} />
  <Composition id="Thesis" component={Thesis} durationInFrames={120} {...V} />
  <Composition id="ActTwo" component={ActTwo} durationInFrames={600} {...V} />
  <Composition id="ActThree" component={ActThree} durationInFrames={1020} {...V} />
  <Composition id="ActFour" component={ActFour} durationInFrames={420} {...V} />
  <Composition id="GraphLook" component={GraphLook} durationInFrames={400} {...V} />
  <Composition id="Pages" component={Pages} durationInFrames={1} fps={30} width={1900} height={820} />
</>;
