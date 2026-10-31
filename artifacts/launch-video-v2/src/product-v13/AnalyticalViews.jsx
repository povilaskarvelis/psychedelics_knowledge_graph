import React from 'react';
import {useCurrentFrame} from 'remotion';
import {TransitionSeries,linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {Stage,Title,Svg,p} from '../product/shared';
import {AreaBreakdown} from './AreaBreakdown';
import {ResearchTrends} from './ResearchTrends';
import {Researchers} from '../product-v11/Researchers';
const ResearcherScene=()=>{
 const f=useCurrentFrame();
 return <Stage><Title size={104} opacity={p(f,12,22)}>See who’s driving the research</Title><Svg><Researchers frame={f}/></Svg></Stage>;
};
export const AnalyticalViews=()=> <TransitionSeries>
 <TransitionSeries.Sequence durationInFrames={240} name="Research-area publication breakdown"><AreaBreakdown/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence durationInFrames={300} name="Research-area composition over time"><ResearchTrends/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence durationInFrames={330} name="Researchers and topic connections"><ResearcherScene/></TransitionSeries.Sequence>
</TransitionSeries>;
