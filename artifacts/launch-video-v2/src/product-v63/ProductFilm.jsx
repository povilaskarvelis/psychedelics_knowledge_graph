import React from 'react';
import {Audio} from '@remotion/media';
import {staticFile} from 'remotion';
import {ProductFilmV52} from '../product-v52/ProductFilm';
export const ProductFilmV63=()=> <>
 <Audio src={staticFile('story/product-v63-soundtrack.wav')}/>
 <ProductFilmV52 researcherDuration={292}/>
</>;
