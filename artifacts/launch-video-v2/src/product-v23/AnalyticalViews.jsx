import React from 'react';
import {useCurrentFrame} from 'remotion';
import {TransitionSeries,linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {Stage,Title,Svg,p} from '../product/shared';
import {AreaBreakdown} from '../product-v13/AreaBreakdown';
import {ResearchTrends} from './ResearchTrends';
import {Researchers} from '../product-v11/Researchers';
const ResearcherScene=({headlineSize=104,researcherCompounds,researcherDuration=330})=>{
 const f=useCurrentFrame()*330/researcherDuration;
 return <Stage><Title size={headlineSize} opacity={p(f,12,22)}>See who’s driving the research</Title><Svg><Researchers frame={f} compoundNames={researcherCompounds}/></Svg></Stage>;
};
export const AnalyticalViews=({headlineSize,researcherCompounds,researcherDuration=330})=> <TransitionSeries>
 <TransitionSeries.Sequence durationInFrames={240} name="Research-area publication breakdown"><AreaBreakdown headlineSize={headlineSize}/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence durationInFrames={224} name="Research-area composition over time"><ResearchTrends headlineSize={headlineSize}/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence durationInFrames={researcherDuration} name="Researchers and topic connections"><ResearcherScene headlineSize={headlineSize} researcherCompounds={researcherCompounds} researcherDuration={researcherDuration}/></TransitionSeries.Sequence>
</TransitionSeries>;
