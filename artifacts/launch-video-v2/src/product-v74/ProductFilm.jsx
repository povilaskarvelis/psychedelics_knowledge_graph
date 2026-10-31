import React from 'react';
import {Audio} from '@remotion/media';
import {staticFile} from 'remotion';
import {ProductFilmV52} from '../product-v52/ProductFilm';

export const ProductFilmV74=()=> <>
 <Audio src={staticFile('story/product-v73-soundtrack.wav')}/>
 <ProductFilmV52
  researcherDuration={292}
  smoothConditionLabel
  smoothConditionLabelEnd={248}
  studyTitleStart={150}
  clickSelectedEdge
 />
</>;
