import React from 'react';
import {Audio} from '@remotion/media';
import {staticFile} from 'remotion';
import {ProductFilmV52} from '../product-v52/ProductFilm';
export const ProductFilmV64=()=> <>
 <Audio src={staticFile('story/product-v64-soundtrack.wav')}/>
 <ProductFilmV52 researcherDuration={292}/>
</>;
