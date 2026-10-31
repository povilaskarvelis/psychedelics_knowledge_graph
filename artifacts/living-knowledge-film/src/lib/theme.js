import {loadFont as loadSpace} from '@remotion/google-fonts/SpaceGrotesk';
import {loadFont as loadPlex} from '@remotion/google-fonts/IBMPlexSans';
import {loadFont as loadMono} from '@remotion/google-fonts/IBMPlexMono';

export const SPACE = loadSpace('normal', {weights: ['400', '500', '600', '700'], subsets: ['latin']}).fontFamily;
export const PLEX = loadPlex('normal', {weights: ['400', '500', '600'], subsets: ['latin']}).fontFamily;
export const MONO = loadMono('normal', {weights: ['400', '500'], subsets: ['latin']}).fontFamily;

// Site tokens (ui/styles.css)
export const C = {
  bg: '#080a0b',
  bg2: '#0c1012',
  fg: '#e8ece8',
  muted: '#aeb5b4',
  dim: '#6f7876',
  gold: '#f1b74b',
  teal: '#6ee3d7',
  link: '#65bdad',
  rose: '#f080a3',
  blue: '#90baff',
  green: '#a7be73',
  paper: '#ece8df',
};

// Entity types used across the film
export const TYPES = {
  finding: {label: 'Finding', color: C.gold},
  intervention: {label: 'Intervention', color: C.green},
  population: {label: 'Population', color: C.teal},
  method: {label: 'Method', color: C.rose},
  outcome: {label: 'Outcome', color: C.rose},
  concept: {label: 'Concept', color: '#d9f6f2'},
};

export const hex3 = (h) => {
  const n = parseInt(h.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
};
