import React from 'react';
import {TransitionSeries,linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {Papers} from './01-Papers';
import {Details} from './02-Details';
import {Reviews} from './03-Reviews';
import {Structure} from './04-Structure';
import {Graph} from './05-Graph';
import {Explore} from './06-Explore';
import {Update} from './07-Update';
import {Example} from './08-Example';

export const KnowledgeSynthesisFilm=()=> <TransitionSeries>
  <TransitionSeries.Sequence name="Scientific knowledge grows paper by paper" durationInFrames={240}><Papers/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
  <TransitionSeries.Sequence name="Details live within narrative publications" durationInFrames={250}><Details/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
  <TransitionSeries.Sequence name="Reviews answer bounded questions while literature continues" durationInFrames={250}><Reviews/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
  <TransitionSeries.Sequence name="AI-assisted structuring of reported findings" durationInFrames={300}><Structure/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
  <TransitionSeries.Sequence name="A connected graph of findings" durationInFrames={300}><Graph/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
  <TransitionSeries.Sequence name="Specific questions and broader patterns" durationInFrames={330}><Explore/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
  <TransitionSeries.Sequence name="Growing with new research" durationInFrames={240}><Update/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
  <TransitionSeries.Sequence name="Psychedelics Knowledge Graph as a working example" durationInFrames={180}><Example/></TransitionSeries.Sequence>
</TransitionSeries>;
