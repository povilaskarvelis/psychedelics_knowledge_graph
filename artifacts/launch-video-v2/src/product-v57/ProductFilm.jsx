import React from 'react';
import {Audio} from '@remotion/media';
import {staticFile} from 'remotion';
import {ProductFilmV52} from '../product-v52/ProductFilm';

export const ProductFilmV57=()=> <>
 <Audio src={staticFile('story/product-v57-soundtrack.wav')}/>
 <ProductFilmV52/>
</>;
