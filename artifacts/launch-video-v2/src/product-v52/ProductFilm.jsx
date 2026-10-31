import React from 'react';
import {TransitionSeries,linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {Opening} from './Opening';
import {Drilldown} from './Drilldown';
import {AnalyticalViews} from '../product-v23/AnalyticalViews';
import {Living} from '../product-v24/Living';
import {Access} from '../product-v9/Access';
import {Outro} from '../product/Outro';

const headlineSize=96;
const researcherCompounds=['Ketamine','Psilocybin','MDMA','LSD','DMT','Ayahuasca','Mescaline'];

export const ProductFilmV52=({researcherDuration=330,smoothConditionLabel=false,smoothConditionLabelEnd=268,cohesiveConditionLabel=false,studyTitleStart=null,clickSelectedEdge=false,totalPaperCount=21000})=> <TransitionSeries>
 <TransitionSeries.Sequence name="Research growth, breadth, synthesis bottleneck, and continuous solution reveal" durationInFrames={662}><Opening totalPaperCount={totalPaperCount}/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence name="Explore study context and sample sizes over time" durationInFrames={780}><Drilldown smoothConditionLabel={smoothConditionLabel} smoothConditionLabelEnd={smoothConditionLabelEnd} cohesiveConditionLabel={cohesiveConditionLabel} studyTitleStart={studyTitleStart} clickSelectedEdge={clickSelectedEdge}/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Research areas over time and researchers" durationInFrames={440+researcherDuration}><AnalyticalViews headlineSize={headlineSize} researcherCompounds={researcherCompounds} researcherDuration={researcherDuration}/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Connect the graph to your tools" durationInFrames={270}><Access headlineSize={headlineSize}/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="New papers update the knowledge graph and data visualizations together" durationInFrames={330}><Living headlineSize={headlineSize} compactLabels alignIngestionWithDivider rightPanelLabel="Data visualizations"/></TransitionSeries.Sequence>
 <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
 <TransitionSeries.Sequence name="Product identity" durationInFrames={180}><Outro/></TransitionSeries.Sequence>
</TransitionSeries>;
