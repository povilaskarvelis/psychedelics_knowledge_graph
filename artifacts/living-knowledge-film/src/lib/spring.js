// Closed-form damped springs: motion with mass, still a pure function of time (deterministic per frame).
const FPS = 30;

export const SPR = {
  pop: {stiffness: 320, damping: 17},      // visible overshoot: nodes, markers
  snappy: {stiffness: 380, damping: 30},   // small overshoot: UI controls, cursor
  ui: {stiffness: 200, damping: 25},       // cards, panels
  soft: {stiffness: 110, damping: 20},     // large UI moves
  heavy: {stiffness: 60, damping: 15.5},   // critically damped: big type, objects
  camera: {stiffness: 14, damping: 7.48},  // critically damped, ~1 s
  slow: {stiffness: 5, damping: 4.47},     // critically damped, ~2 s
  drift: {stiffness: 2.2, damping: 2.97},  // critically damped, ~3 s
};

// unit step response x(t): 0 → 1
export const springT = (t, {stiffness, damping, mass = 1}) => {
  if (t <= 0) return 0;
  const w0 = Math.sqrt(stiffness / mass);
  const zeta = damping / (2 * Math.sqrt(stiffness * mass));
  if (zeta < 0.999) {
    const wd = w0 * Math.sqrt(1 - zeta * zeta);
    return 1 - Math.exp(-zeta * w0 * t) * (Math.cos(wd * t) + (zeta * w0 / wd) * Math.sin(wd * t));
  }
  if (zeta <= 1.001) return 1 - Math.exp(-w0 * t) * (1 + w0 * t);
  const s = Math.sqrt(zeta * zeta - 1);
  const r1 = -w0 * (zeta - s), r2 = -w0 * (zeta + s);
  return 1 - (r2 * Math.exp(r1 * t) - r1 * Math.exp(r2 * t)) / (r2 - r1);
};

const preset = (p) => (typeof p === 'string' ? SPR[p] : p);

// spring progress for an event at frame `start`
export const sp = (f, start, p = 'ui') => springT((f - start) / FPS, preset(p));

/**
 * A value with several targets. keys: [[frame, value, preset?], ...] (value: number or array).
 * Every change adds its own spring from its own start, so motion stays continuous and any frame can be
 * evaluated without simulating the ones before it.
 */
export const track = (f, keys, p = 'camera') => {
  const arr = Array.isArray(keys[0][1]);
  let v = arr ? [...keys[0][1]] : keys[0][1];
  for (let i = 1; i < keys.length; i++) {
    const s = sp(f, keys[i][0], keys[i][2] || p);
    if (arr) v = v.map((x, k) => x + (keys[i][1][k] - keys[i - 1][1][k]) * s);
    else v += (keys[i][1] - keys[i - 1][1]) * s;
  }
  return v;
};

export const trackPose = (f, keys, p = 'camera') => {
  // keys: [[frame, {pos, look, fov, roll}, preset?], ...]
  const pick = (k) => keys.map(([fr, pose, pr]) => [fr, pose[k], pr]);
  return {pos: track(f, pick('pos'), p), look: track(f, pick('look'), p), fov: track(f, pick('fov'), p), roll: track(f, pick('roll'), p)};
};
