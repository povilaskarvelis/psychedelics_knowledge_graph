import React from 'react';
import {SPACE, MONO, C} from '../lib/theme';
import {clamp, eoExpo, eo3, lin, mix} from '../lib/ease';

// "plain **accent** plain" → segments
// "plain **accent** [[word|#hex]]" → segments (accent = theme gold; [[..|colour]] = explicit colour)
const parse = (line) => line.split(/(\*\*[^*]+\*\*|\[\[[^\]]+\]\])/).filter(Boolean).map((s) => {
  if (s.startsWith('**')) return {t: s.slice(2, -2), a: true};
  if (s.startsWith('[[')) { const [t, color] = s.slice(2, -2).split('|'); return {t, color}; }
  return {t: s, a: false};
});

/**
 * Kinetic caption. f = local frame. Words rise through a line mask with blur.
 * lines: array of strings with **accent** markup.
 */
export const Caption = ({f, at, until, lines, size = 64, x = 120, y = 820, align = 'left', accent = C.gold,
  weight = 500, stagger = 1.5, lineDelay = 6, eyebrow, eyebrowColor = C.teal, width = 1680, color = C.fg, exit = 10, lh = 1.08, tracking = -0.032}) => {
  if (f < at - 1 || f > until + exit + 2) return null;
  const out = lin(f, until, until + exit);
  let wi = 0;
  const anchorStyle = align === 'center'
    ? {left: 0, right: 0, textAlign: 'center', top: y}
    : {left: x, top: y, width, textAlign: align};
  return (
    <div style={{position: 'absolute', ...anchorStyle, transform: `translateY(-100%)`, fontFamily: SPACE, fontWeight: weight,
      fontSize: size, lineHeight: lh, letterSpacing: `${tracking}em`, color, textShadow: '0 0 5px rgba(0,0,0,0.85), 0 0 16px rgba(0,0,0,0.8), 0 0 40px rgba(0,0,0,0.65)'}}>
      {eyebrow && (
        <Eyebrow f={f - at} text={eyebrow} color={eyebrowColor} out={out} align={align} />
      )}
      {lines.map((line, li) => (
        <div key={li} style={{overflow: 'hidden', paddingBottom: size * 0.16, marginBottom: -size * 0.16, paddingTop: size * 0.06}}>
          {parse(line).map((seg, si) => seg.t.split(/(\s+)/).filter(Boolean).map((w, k) => {
            if (/^\s+$/.test(w)) return <span key={`${si}-${k}`}>{' '}</span>;
            const i = wi++;
            const t0 = at + li * lineDelay + i * stagger;
            const pin = eoExpo(lin(f, t0, t0 + 14));
            const vis = pin * (1 - eo3(out));
            return (
              <span key={`${si}-${k}`} style={{
                display: 'inline-block',
                transform: `translateY(${mix(0.9, 0, pin) * 100 - eo3(out) * 18}%)`,
                opacity: clamp(vis * 1.4),
                filter: `blur(${(1 - pin) * 8 + eo3(out) * 6}px)`,
                color: seg.color || (seg.a ? accent : undefined),
              }}>{w}</span>
            );
          }))}
        </div>
      ))}
    </div>
  );
};

export const Eyebrow = ({f, text, color = C.teal, out = 0, align = 'left'}) => {
  const a = eo3(lin(f, 0, 18));
  const w = eoExpo(lin(f, 4, 34));
  return (
    <div style={{display: 'flex', alignItems: 'center', justifyContent: align === 'center' ? 'center' : 'flex-start', gap: 18, marginBottom: 26,
      fontFamily: MONO, fontSize: 19, fontWeight: 500, letterSpacing: '0.22em', color, opacity: a * (1 - out), textShadow: 'none'}}>
      <span style={{display: 'inline-block', width: 56 * w, height: 2, background: color, boxShadow: `0 0 12px ${color}`}} />
      <span style={{transform: `translateX(${(1 - a) * -14}px)`}}>{text}</span>
    </div>
  );
};

// Small HUD label (mono)
export const Hud = ({children, style, color = C.muted, size = 16}) => (
  <div style={{position: 'absolute', fontFamily: MONO, fontSize: size, letterSpacing: '0.14em', color, textTransform: 'uppercase', ...style}}>{children}</div>
);

const SHADOW = '0 0 5px rgba(0,0,0,0.85), 0 0 16px rgba(0,0,0,0.8), 0 0 40px rgba(0,0,0,0.65)';
const hexRgb = (h) => { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
const mixHex = (a, b, t) => { const p = hexRgb(a), q = hexRgb(b); return `rgb(${p.map((v, k) => Math.round(v + (q[k] - v) * t)).join(',')})`; };
const rgba = (h, a) => `rgba(${hexRgb(h).join(',')},${a})`;
// "plain **accent** [[word|#hex]] [[word|#hex|12]]": the last form takes its colour 12 frames after `at`,
// with a highlighter stroke sweeping in behind it (the same mark the page highlights use).
const parseMarks = (line) => line.split(/(\*\*[^*]+\*\*|\[\[[^\]]+\]\])/).filter(Boolean).map((s) => {
  if (s.startsWith('**')) return {t: s.slice(2, -2), a: true};
  if (s.startsWith('[[')) { const [t, color, d] = s.slice(2, -2).split('|'); return {t, color, mark: d != null ? +d : null}; }
  return {t: s, a: false};
});

/**
 * A block of set type, composed into the frame (not a subtitle). Lines are broken by hand; each line has its own mask,
 * words rise through it. anchor: 'center' | 'top' | 'bottom' (relative to y). lineAt: optional start frame per line.
 */
export const Block = ({f, at, until, lines, x = 1110, y = 540, anchor = 'center', width = 720, size = 58, weight = 500, lh = 1.12,
  stagger = 1.6, lineDelay = 5, lineAt = null, exit = 12, color = C.fg, accent = C.gold, tracking = -0.03, align = 'left', opacity = 1}) => {
  if (f < at - 1 || f > until + exit + 2) return null;
  const out = eo3(lin(f, until, until + exit));
  const ty = anchor === 'center' ? -50 : anchor === 'bottom' ? -100 : 0;
  return (
    <div style={{position: 'absolute', left: x, top: y, width, transform: `translateY(${ty}%)`, textAlign: align, opacity,
      fontFamily: SPACE, fontWeight: weight, fontSize: size, lineHeight: lh, letterSpacing: `${tracking}em`, color, textShadow: SHADOW}}>
      {lines.map((line, li) => {
        let wi = 0;
        const l0 = lineAt ? lineAt[li] : at + li * lineDelay;
        return (
          <div key={li} style={{overflow: 'hidden', paddingBottom: size * 0.18, marginBottom: -size * 0.18, paddingTop: size * 0.06, whiteSpace: 'nowrap'}}>
            {parseMarks(line).map((seg, si) => seg.t.split(/(\s+)/).filter(Boolean).map((w, k) => {
              if (/^\s+$/.test(w)) return <span key={`${si}-${k}`}>{' '}</span>;
              const t0 = l0 + (wi++) * stagger;
              const pin = eoExpo(lin(f, t0, t0 + 14));
              const m = seg.mark != null ? eo3(lin(f, at + seg.mark, at + seg.mark + 9)) : 1;
              const col = seg.color ? (seg.mark != null ? mixHex(color, seg.color, m) : seg.color) : seg.a ? accent : undefined;
              return (
                <span key={`${si}-${k}`} style={{display: 'inline-block', transform: `translateY(${mix(0.95, 0, pin) * 100 - out * 22}%)`,
                  opacity: clamp(pin * 1.4) * (1 - out), filter: `blur(${(1 - pin) * 8 + out * 6}px)`, color: col,
                  ...(seg.mark != null ? {backgroundImage: `linear-gradient(90deg, ${rgba(seg.color, 0.24)} ${m * 100}%, transparent ${m * 100}%)`,
                    borderRadius: size * 0.1, padding: `0 ${size * 0.07}px`, margin: `0 ${-size * 0.07}px`} : {})}}>{w}</span>
              );
            }))}
          </div>
        );
      })}
    </div>
  );
};
