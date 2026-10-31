import React from 'react';
import {staticFile} from 'remotion';
import {Audio} from '@remotion/media';
import {TransitionSeries,linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {Foundation} from './Foundation';
import {Explore} from './Explore';
import {Analyze} from './Analyze';
import {Living} from './Living';
import {Access} from './Access';
import {Outro} from './Outro';
export const ProductFilm=()=> <><Audio src={staticFile('story/product-soundtrack.wav')} volume={.62}/><TransitionSeries>
 <TransitionSeries.Sequence name="Papers become connected knowledge" durationInFrames={450}><Foundation/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Explore and compare studies" durationInFrames={690}><Explore/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Analyze patterns and connections" durationInFrames={825}><Analyze/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="New papers join the graph" durationInFrames={300}><Living/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Programmatic access" durationInFrames={255}><Access/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Product identity" durationInFrames={180}><Outro/></TransitionSeries.Sequence>
</TransitionSeries></>;
