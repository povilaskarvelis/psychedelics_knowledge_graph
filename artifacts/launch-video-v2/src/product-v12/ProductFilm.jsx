import React from 'react';
import {staticFile} from 'remotion';
import {Audio} from '@remotion/media';
import {TransitionSeries,linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {Opening} from './Opening';
import {Drilldown} from './Drilldown';
import {AnalyticalViews} from '../product-v11/AnalyticalViews';
import {Living} from '../product-v9/Living';
import {Access} from '../product-v9/Access';
import {Outro} from '../product/Outro';
export const ProductFilmV12=()=> <><Audio src={staticFile('story/product-v11-soundtrack.wav')} volume={.62}/><TransitionSeries>
 <TransitionSeries.Sequence name="Papers, compounds, connected knowledge" durationInFrames={720}><Opening/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence name="Study context and sample sizes over time" durationInFrames={840}><Drilldown/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Publication types, research areas, trends and researchers" durationInFrames={1074}><AnalyticalViews/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="New papers update the graph and views" durationInFrames={330}><Living/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Connect the graph to your tools" durationInFrames={270}><Access/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Product identity" durationInFrames={180}><Outro/></TransitionSeries.Sequence>
</TransitionSeries></>;
