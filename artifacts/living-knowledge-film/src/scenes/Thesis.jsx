import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {C, SPACE} from '../lib/theme';
import {band, eo3, eo5, lin, mix} from '../lib/ease';
import {Caption} from '../ui/Type';

// The turn, on black: storage, synthesis and access, one per beat (15 frames).
const WORDS = [['stored.', 45], ['synthesized.', 60], ['accessed.', 75]];

const Slam = ({f, word, at}) => {
  const t = lin(f, at, at + 9);
  if (f < at) return <span style={{opacity: 0, marginRight: 34}}>{word}</span>;
  const s = mix(1.28, 1, eo5(t));
  const out = lin(f, 108, 118);
  const flash = band(f, at, at + 1, at + 2, at + 8);
  return (
    <span style={{display: 'inline-block', marginRight: 34, transform: `scale(${s}) translateY(${eo3(out) * -10}px)`, opacity: (0.4 + 0.6 * eo3(t)) * (1 - out),
      filter: `blur(${(1 - eo3(t)) * 6 + out * 6}px)`, color: C.gold, textShadow: `0 0 ${20 + flash * 50}px rgba(241,183,75,${0.25 + flash * 0.5})`}}>{word}</span>
  );
};

export const Thesis = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{background: '#050607'}}>
      <Caption f={f} at={4} until={106} align="center" y={500} size={64} color={C.fg}
        lines={["It's time to rethink how scientific knowledge is"]} exit={12} />
      <div style={{position: 'absolute', left: 0, right: 0, top: 600, textAlign: 'center', fontFamily: SPACE, fontWeight: 600, fontSize: 112, letterSpacing: '-0.035em'}}>
        {WORDS.map(([w, at]) => <Slam key={w} f={f} word={w} at={at} />)}
      </div>
    </AbsoluteFill>
  );
};
