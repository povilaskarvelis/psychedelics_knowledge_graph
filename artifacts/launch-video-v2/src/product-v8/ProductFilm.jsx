import React from 'react';
import {staticFile} from 'remotion';
import {Audio} from '@remotion/media';
import {TransitionSeries,linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {Opening} from './Opening';
import {Drilldown} from './Drilldown';
import {AnalyticalViews} from './AnalyticalViews';
import {Living} from './Living';
import {Access} from './Access';
import {Outro} from '../product/Outro';
export const ProductFilmV8=()=> <><Audio src={staticFile('story/product-v8-soundtrack.wav')} volume={.62}/><TransitionSeries>
 <TransitionSeries.Sequence name="Papers, compounds, connected knowledge" durationInFrames={600}><Opening/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence name="Conditions unfold into study context" durationInFrames={660}><Drilldown/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Types of research, trends, authors and coverage" durationInFrames={960}><AnalyticalViews/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Living knowledge synthesis" durationInFrames={300}><Living/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Connect the graph to your tools" durationInFrames={270}><Access/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Product identity" durationInFrames={180}><Outro/></TransitionSeries.Sequence>
</TransitionSeries></>;
