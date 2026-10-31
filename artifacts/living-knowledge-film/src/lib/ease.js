export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const mix = (a, b, t) => a + (b - a) * t;
export const lin = (f, a, b) => clamp((f - a) / (b - a));
export const eio = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
export const eo3 = (t) => 1 - Math.pow(1 - t, 3);
export const eo5 = (t) => 1 - Math.pow(1 - t, 5);
export const ei3 = (t) => t * t * t;
export const eoExpo = (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));
export const eioExpo = (t) => t <= 0 ? 0 : t >= 1 ? 1 : t < 0.5 ? Math.pow(2, 20 * t - 10) / 2 : (2 - Math.pow(2, -20 * t + 10)) / 2;
export const eioQuint = (t) => (t < 0.5 ? 16 * t ** 5 : 1 - Math.pow(-2 * t + 2, 5) / 2);
export const smooth = (t) => t * t * (3 - 2 * t);

// progress helpers in frames
export const p = (f, a, b, e = eio) => e(lin(f, a, b));
// fade in over [a,b], out over [c,d]
export const band = (f, a, b, c, d) => Math.min(lin(f, a, b), 1 - lin(f, c, d));

// deterministic PRNG
export const rng = (seed) => {
  let s = seed >>> 0 || 1;
  return () => {
    s |= 0; s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};
export const hash = (i) => {
  const x = Math.sin(i * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};

// piecewise keyframe interpolation: keys = [[frame, value], ...] with easing per segment
export const keys = (f, ks, e = eio) => {
  if (f <= ks[0][0]) return ks[0][1];
  for (let i = 1; i < ks.length; i++) {
    if (f <= ks[i][0]) {
      const [f0, v0] = ks[i - 1];
      const [f1, v1, ee] = ks[i];
      const t = (ee || e)((f - f0) / (f1 - f0));
      if (Array.isArray(v0)) return v0.map((v, j) => mix(v, v1[j], t));
      return mix(v0, v1, t);
    }
  }
  return ks[ks.length - 1][1];
};
