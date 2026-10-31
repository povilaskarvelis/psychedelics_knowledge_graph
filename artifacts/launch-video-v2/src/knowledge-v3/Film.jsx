import React from 'react';
import {TransitionSeries} from '@remotion/transitions';
import {Acceleration} from './01-Acceleration';
import {Unit} from './02-Unit';
import {Implicit} from './03-Implicit';
import {Synthesis} from './04-Synthesis';
import {Reframe} from './05-Reframe';
import {Structure} from './06-Structure';
import {Query} from './07-Query';
import {Navigate} from './08-Navigate';
import {Reuse} from './09-Reuse';
import {Living} from './10-Living';
import {Horizon} from './11-Horizon';

export const KnowledgeSynthesisFilmV3=()=> <TransitionSeries>
 <TransitionSeries.Sequence durationInFrames={210} name="The accelerating archive"><Acceleration/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence durationInFrames={210} name="Question the unit of knowledge"><Unit/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence durationInFrames={210} name="Connections have to be reconstructed"><Implicit/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence durationInFrames={225} name="Synthesis has a scope and a date"><Synthesis/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence durationInFrames={240} name="Make connections part of the record"><Reframe/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence durationInFrames={255} name="AI assisted structure with source traceability"><Structure/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence durationInFrames={240} name="Query study details across literature"><Query/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence durationInFrames={240} name="Navigate between scales"><Navigate/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence durationInFrames={240} name="Reuse structure for new syntheses"><Reuse/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence durationInFrames={240} name="Continuously updated and programmable"><Living/></TransitionSeries.Sequence>
 <TransitionSeries.Sequence durationInFrames={270} name="Toward a connected scientific memory"><Horizon/></TransitionSeries.Sequence>
</TransitionSeries>;
