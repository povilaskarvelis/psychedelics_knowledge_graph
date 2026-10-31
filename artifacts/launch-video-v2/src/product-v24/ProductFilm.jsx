import React from 'react';
import {TransitionSeries,linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {Opening} from './Opening';
import {Drilldown} from '../product-v22/Drilldown';
import {AnalyticalViews} from '../product-v23/AnalyticalViews';
import {Living} from './Living';
import {Access} from '../product-v9/Access';
import {Outro} from '../product/Outro';
export const ProductFilmV24=()=> <TransitionSeries>
 <TransitionSeries.Sequence name="Research growth becomes a connected graph" durationInFrames={512}><Opening/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence name="Study context and sample sizes over time" durationInFrames={780}><Drilldown/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Research areas over time and researchers" durationInFrames={770}><AnalyticalViews/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Connect the graph to your tools" durationInFrames={270}><Access/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="New papers update the graph and views" durationInFrames={330}><Living/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Product identity" durationInFrames={180}><Outro/></TransitionSeries.Sequence>
</TransitionSeries>;
