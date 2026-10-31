import React from 'react';
import {AbsoluteFill} from 'remotion';
import {journalPage} from '../lib/textures';
import {C, MONO} from '../lib/theme';

// Look-development sheet: pages at full resolution with their highlight marks outlined. By default the twelve atlas
// pages; pass inputProps {specs: [...]} to compare one-off pages.
export const PAGE_CANDIDATES = [
  ...[9001, 9007, 9013, 9019, 9025, 9031].map((seed) => ({seed, titleLines: 3, figure: {kind: 0, colors: ['#90baff', '#f1b74b']}, rule: '#90baff'})),
  ...[9101, 9107, 9113, 9119, 9125, 9131].map((seed) => ({seed, titleLines: 2, figure: {kind: 0, colors: ['#7d8388', '#b3b8bb']}, rule: '#8f969a'})),
];
export const Pages = ({specs = null}) => (
  <AbsoluteFill style={{background: C.bg, display: 'flex', flexWrap: 'wrap', gap: 14, padding: 14, alignContent: 'flex-start'}}>
    {(specs || Array.from({length: 12}, (_, v) => v)).map((spec, k) => {
      const p = journalPage(spec, 900), S = 300, H = S / 0.772;
      return (
        <div key={k} style={{position: 'relative', width: S, height: H}}>
          <img src={p.tex.image.toDataURL()} style={{width: S, height: H}} />
          {p.segs.map((s, j) => <div key={j} style={{position: 'absolute', left: s.u0 * S, width: (s.u1 - s.u0) * S, top: (1 - s.v1) * H,
            height: (s.v1 - s.v0) * H, outline: '1px solid #f080a3'}} />)}
          <div style={{position: 'absolute', left: 6, top: 4, fontFamily: MONO, fontSize: 16, color: '#c33'}}>{typeof spec === 'object' ? spec.seed : spec}</div>
        </div>
      );
    })}
  </AbsoluteFill>
);
