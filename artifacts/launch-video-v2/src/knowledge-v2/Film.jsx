import React from 'react';
import {TransitionSeries,linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {Shape} from './01-Shape';
import {Papers} from './02-Papers';
import {Snapshot} from './03-Snapshot';
import {Turn} from './04-Turn';
import {Structure} from './05-Structure';
import {Scale} from './06-Scale';
import {Living} from './07-Living';
import {Example} from './08-Example';

export const KnowledgeSynthesisFilmV2=()=> <TransitionSeries>
  <TransitionSeries.Sequence name="Science advances through connections" durationInFrames={270}><Shape/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:18})}/>
  <TransitionSeries.Sequence name="The published record is paper-shaped" durationInFrames={270}><Papers/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:18})}/>
  <TransitionSeries.Sequence name="Focused synthesis is a snapshot" durationInFrames={300}><Snapshot/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:18})}/>
  <TransitionSeries.Sequence name="Make the connections explicit and durable" durationInFrames={380}><Turn/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:18})}/>
  <TransitionSeries.Sequence name="Structure reports and preserve source traceability" durationInFrames={370}><Structure/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:18})}/>
  <TransitionSeries.Sequence name="Zoom from a study detail to broader patterns" durationInFrames={390}><Scale/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:18})}/>
  <TransitionSeries.Sequence name="A living memory that grows with new research" durationInFrames={330}><Living/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:18})}/>
  <TransitionSeries.Sequence name="Psychedelics Knowledge Graph application" durationInFrames={190}><Example/></TransitionSeries.Sequence>
</TransitionSeries>;
