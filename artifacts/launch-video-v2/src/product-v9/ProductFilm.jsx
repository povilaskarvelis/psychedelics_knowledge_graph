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
export const ProductFilmV9=()=> <><Audio src={staticFile('story/product-v9-soundtrack.wav')} volume={.62}/><TransitionSeries>
 <TransitionSeries.Sequence name="Papers, compounds, connected knowledge" durationInFrames={720}><Opening/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence name="Conditions unfold into study context" durationInFrames={660}><Drilldown/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Publication types, trends, researchers and coverage" durationInFrames={1050}><AnalyticalViews/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="New papers update the graph and views" durationInFrames={330}><Living/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Connect the graph to your tools" durationInFrames={270}><Access/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Product identity" durationInFrames={180}><Outro/></TransitionSeries.Sequence>
</TransitionSeries></>;
