import React from 'react';
import {Audio} from '@remotion/media';
import {staticFile} from 'remotion';
import {ProductFilmV52} from '../product-v52/ProductFilm';
export const ProductFilmV58=()=> <>
 <Audio src={staticFile('story/product-v58-soundtrack.wav')}/>
 <ProductFilmV52/>
</>;
