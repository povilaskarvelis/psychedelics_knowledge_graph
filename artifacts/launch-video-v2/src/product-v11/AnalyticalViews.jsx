import React from 'react';
import {useCurrentFrame} from 'remotion';
import {TransitionSeries,linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {Stage,Title,Svg} from '../product/shared';
import {PublicationTypes} from './PublicationTypes';
import {AreaBreakdown} from './AreaBreakdown';
import {ResearchTrends} from './ResearchTrends';
import {Researchers} from './Researchers';
const ResearcherScene=()=>{
 const f=useCurrentFrame();
 return <Stage><Title size={104}>See who’s driving the research</Title><Svg><Researchers frame={f}/></Svg></Stage>;
};
export const AnalyticalViews=()=> <TransitionSeries>
 <TransitionSeries.Sequence durationInFrames={300} name="Publication types and history"><PublicationTypes/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence durationInFrames={240} name="Research-area publication breakdown"><AreaBreakdown/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence durationInFrames={240} name="Changing research activity"><ResearchTrends/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence durationInFrames={330} name="Researchers and topic connections"><ResearcherScene/></TransitionSeries.Sequence>
</TransitionSeries>;
