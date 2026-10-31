import React from 'react';
import {Audio} from '@remotion/media';
import {staticFile} from 'remotion';
import {ProductFilmV52} from '../product-v52/ProductFilm';

export const ProductFilmV70=()=> <>
 <Audio src={staticFile('story/product-v65-soundtrack.wav')}/>
 <ProductFilmV52 researcherDuration={292} smoothConditionLabel smoothConditionLabelEnd={248}/>
</>;
