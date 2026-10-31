"""Score for the calm cut — a warm, piano-led piece at 90 bpm in D major, synced to the picture (20 frames = 1 beat,
80 frames = 1 bar). It breathes rather than drives: piano and pad for the paper and the field, a hush inside the page,
three rising chimes as its pieces lift off, a soft pulse as everything rises and connects, a gentle groove under the
product, and a full, open close for every field.

Bars: the paper 0–3 · the field 3–5 · inside the page 5–6 · extraction 6–8 · release, the graph forms 8–10 · a living
graph 10–12 · the first one (product) 12–24 · every field 24–27 · end chord 27–29.
Everything is synthesized here. Output: public/audio/score-calm.wav (48 kHz stereo).
"""
import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
FPS = 30
BPM = 90
BEAT = 60 / BPM            # 0.667 s = 20 frames
BAR = BEAT * 4             # 2.667 s = 80 frames
END_F = 2320
DUR = END_F / FPS + 4.0
N = int(DUR * SR)
rng = np.random.default_rng(7)
sec = lambda f: f / FPS
bar = lambda b: b * BAR

# picture landmarks (global frames) — mirror src/calm/*.jsx (genesis 0 · product 960 · finale 1920)
EV = dict(
    line1=22, land=(128, 360), line2=240, specks=300, dive=340, line3=400, marks=[408, 411, 414, 417, 420, 423],
    lift=[480, 487, 494], line4=490, release=640, bridges=720, living=800, arrive=(815, 940),
    product=960, draw=(1004, 1060), clicks=[1125, 1205, 1290, 1350], list_=1230, analyze=1410, meta=1570, gaps=[1602, 1606, 1610, 1614, 1618, 1622],
    agents=1680, ask=(1700, 1718), calls=[1722, 1742], results=[1734, 1758], answer=1770, graph=1840, gold=1854,
    finale=1920, arcs=1978, tagline=2046, card=2160,
)

NAMES = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5, 'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}
def hz(n):
    return 440.0 * 2 ** ((NAMES[n[:-1]] + 12 * (int(n[-1]) + 1) - 69) / 12)

# chords: bass, piano voicing (left + right hand), pad voicing
CH = {
    'D':  dict(bass='D2', lh=['D3', 'A3'], rh=['F#4', 'A4', 'C#5', 'E5'], pad=['D3', 'A3', 'E4', 'F#4', 'C#5']),
    'Bm': dict(bass='B1', lh=['B2', 'F#3'], rh=['D4', 'F#4', 'A4', 'C#5'], pad=['B2', 'F#3', 'D4', 'A4', 'C#5']),
    'G':  dict(bass='G1', lh=['G2', 'D3'], rh=['B3', 'D4', 'F#4', 'A4'], pad=['G2', 'D3', 'B3', 'F#4', 'A4']),
    'A':  dict(bass='A1', lh=['A2', 'E3'], rh=['C#4', 'E4', 'A4', 'B4'], pad=['A2', 'E3', 'C#4', 'E4', 'B4']),
    'Asus': dict(bass='A1', lh=['A2', 'E3'], rh=['D4', 'E4', 'A4', 'B4'], pad=['A2', 'E3', 'D4', 'E4', 'B4']),
}
PROG = ['D', 'Bm', 'G', 'D', 'Asus', 'Bm', 'G', 'A', 'D', 'Bm', 'G', 'A',            # genesis (bars 0–11)
        'D', 'Bm', 'G', 'A', 'D', 'Bm', 'G', 'A', 'Bm', 'G', 'Asus', 'A',            # product (12–23)
        'D', 'Bm', 'G', 'D', 'D', 'D']                                               # finale (24–29)

def buf():
    return np.zeros((N, 2))

def place(bus, t, x, pan=0.0, gain=1.0):
    i = int(round(t * SR))
    if i >= N:
        return
    if x.ndim == 1:
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        x = np.stack([x * l, x * r], axis=1)
    j0 = max(0, -i); j1 = min(len(x), N - i)
    if j1 > j0:
        bus[i + j0:i + j1] += x[j0:j1] * gain

def lp(x, fc, order=2):
    b, a = signal.butter(order, min(fc, SR / 2 - 200) / (SR / 2), 'low'); return signal.lfilter(b, a, x, axis=0)
def hp(x, fc, order=2):
    b, a = signal.butter(order, fc / (SR / 2), 'high'); return signal.lfilter(b, a, x, axis=0)
def bp(x, lo, hi, order=2):
    b, a = signal.butter(order, [lo / (SR / 2), min(hi, SR / 2 - 200) / (SR / 2)], 'band'); return signal.lfilter(b, a, x, axis=0)

def saw(f, n, ph=0.0):
    t = np.arange(n) / SR
    return 2 * ((f * t + ph) % 1.0) - 1

def sweep_lp(x, f0, f1, curve=1.0):
    out = np.zeros_like(x); blk = 512; nb = int(np.ceil(len(x) / blk)); zi = None
    mono = x.ndim == 1
    for k in range(nb):
        u = (k / max(1, nb - 1)) ** curve
        fc = f0 * (f1 / f0) ** u
        b, a = signal.butter(2, min(fc, SR / 2 - 400) / (SR / 2), 'low')
        seg = x[k * blk:(k + 1) * blk]
        if zi is None:
            zi = np.zeros((max(len(a), len(b)) - 1,) + (() if mono else (x.shape[1],)))
        y, zi = signal.lfilter(b, a, seg, axis=0, zi=zi)
        out[k * blk:(k + 1) * blk] = y
    return out

# ---- instruments -------------------------------------------------------------------------------------------------
def piano(f, vel=0.7, dur=None):
    """additive piano: slightly inharmonic partials that decay faster the higher they are, two detuned strings, a felt
    hammer. Softer notes are darker."""
    tau0 = float(np.clip(2.6 * (220 / f) ** 0.45, 0.55, 4.5))
    dur = dur or min(5.5, tau0 * 3.2)
    n = int(dur * SR); t = np.arange(n) / SR
    x = np.zeros(n)
    B = 0.00018 * (f / 220) ** 0.5
    nk = 9 if f < 600 else 6
    for k in range(1, nk + 1):
        fk = k * f * np.sqrt(1 + B * k * k)
        if fk > SR / 2 - 2000:
            break
        amp = (1 / k ** 1.25) * np.exp(-(k - 1) * (0.55 - 0.35 * vel))
        tk = tau0 / (1 + 0.42 * (k - 1))
        env = np.exp(-t / tk) * 0.75 + np.exp(-t / (tk * 0.18)) * 0.25
        for d in (-0.35, 0.35):
            x += amp * env * np.sin(2 * np.pi * fk * 2 ** (d / 1200) * t + rng.random() * 6.28) * 0.5
    hammer = lp(rng.standard_normal(min(n, int(0.03 * SR))), 1800 + 2500 * vel) * np.exp(-np.arange(min(n, int(0.03 * SR))) / SR * 120) * 0.05
    x[:len(hammer)] += hammer
    x *= np.minimum(1, t / 0.003)
    r = int(0.08 * SR); x[-r:] *= np.linspace(1, 0, r)
    return x * vel

def pad(notes, dur, cutoff=1200, a=1.5, r=1.8, motion=0.0):
    n = int(dur * SR); out = np.zeros((n, 2))
    for nm in notes:
        for v in range(4):
            fv = hz(nm) * 2 ** ((v - 1.5) * 0.07 / 12)
            x = saw(fv, n, rng.random()) * 0.6 + np.sin(2 * np.pi * fv * np.arange(n) / SR + rng.random() * 6.28) * 0.6
            pan = (v / 3) * 1.2 - 0.6
            out[:, 0] += x * np.cos((pan + 1) * np.pi / 4); out[:, 1] += x * np.sin((pan + 1) * np.pi / 4)
    out = out / (4 * len(notes) ** 0.5)
    out = sweep_lp(out, cutoff, cutoff * (1 + motion), 0.8) if motion else lp(out, cutoff)
    t = np.arange(n) / SR
    env = np.minimum(1, t / a) * np.minimum(1, (dur - t) / r).clip(0, 1)
    return out * env[:, None]

def sub(f, dur, level=1.0):
    n = int(dur * SR); t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.12 * np.sin(4 * np.pi * f * t)
    env = np.minimum(1, t / 0.02) * np.exp(-t * 0.9) * np.minimum(1, (dur - t) / 0.08).clip(0, 1)
    return x * env * level

def soft_kick(level=1.0):
    n = int(0.35 * SR); t = np.arange(n) / SR
    fr = 48 + 55 * np.exp(-t * 28)
    body = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-t * 9)
    return np.tanh(body * 1.1) * level

def shaker(level=1.0):
    n = int(0.09 * SR); t = np.arange(n) / SR
    x = bp(rng.standard_normal(n), 5000, 11000) * np.minimum(1, t / 0.012) * np.exp(-t * 55)
    return x * level

def rim(level=1.0):
    n = int(0.12 * SR); t = np.arange(n) / SR
    x = bp(rng.standard_normal(n), 1400, 4200) * np.exp(-t * 60) * 0.5 + np.sin(2 * np.pi * 820 * t) * np.exp(-t * 70) * 0.5
    return x * level

def bell(f, dur=2.4, decay=0.9):
    n = int(dur * SR); t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t * 3) + 0.15 * np.sin(2 * np.pi * f * 3.01 * t) * np.exp(-t * 6)
    return x * np.exp(-t / decay) * np.minimum(1, t / 0.003)

def tick(level=1.0):
    n = int(0.025 * SR); t = np.arange(n) / SR
    return hp(rng.standard_normal(n), 3500) * np.exp(-t * 320) * level

def blip(f, level=1.0):
    n = int(0.16 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * f * t) * np.exp(-t * 26) * np.minimum(1, t / 0.002) * level

def swell(dur, level=1.0):
    """an airy rise: filtered noise opening up"""
    n = int(dur * SR); t = np.linspace(0, 1, n)
    x = sweep_lp(hp(rng.standard_normal(n), 300), 400, 6000, 1.3) * t ** 2.4
    return np.stack([x, np.roll(x, 400)], axis=1) * level

def make_ir(rt=3.0):
    n = int(rt * 1.2 * SR); t = np.arange(n) / SR
    ir = np.stack([rng.standard_normal(n) * np.exp(-6.9 * t / rt) for _ in range(2)], axis=1)
    ir = lp(ir, 4200)
    return ir / np.sqrt((ir ** 2).sum() / 2)

def reverb(x, ir, wet):
    return np.stack([signal.fftconvolve(x[:, c], ir[:, c])[:len(x)] for c in range(2)], axis=1) * wet

# =====================================================================================================================
keys, pads, bass, drums, fx, chimes = buf(), buf(), buf(), buf(), buf(), buf()
kicks = []

def pchord(b, chord, beats=(0,), vel=0.5, spread=0.025, hands='both', gain=1.0):
    """a piano chord on the given beats of bar b (rolled slightly, low to high)"""
    c = CH[chord]
    notes = (c['lh'] if hands in ('both', 'lh') else []) + (c['rh'] if hands in ('both', 'rh') else [])
    for q in beats:
        for k, nm in enumerate(notes):
            place(keys, bar(b) + q * BEAT + k * spread, piano(hz(nm), vel * (0.85 if k < 2 else 1.0)), pan=-0.35 + 0.7 * k / max(1, len(notes) - 1), gain=0.32 * gain)

def parp(b, chord, pattern, vel=0.45, step=0.5, gain=1.0, octave=1):
    """a piano arpeggio through the chord's right hand, `step` beats apart"""
    tones = CH[chord]['rh']
    for s, idx in enumerate(pattern):
        if idx is None:
            continue
        f = hz(tones[idx % len(tones)]) * (2 if idx >= len(tones) else 1) * octave
        place(keys, bar(b) + s * step * BEAT, piano(f, vel), pan=-0.4 + 0.8 * (idx % len(tones)) / 3, gain=0.3 * gain)

def melody(b, notes, vel=0.55, gain=1.0):
    """notes: [(beat, name, vel?)] within bar b"""
    for item in notes:
        q, nm = item[0], item[1]
        v = item[2] if len(item) > 2 else vel
        place(keys, bar(b) + q * BEAT, piano(hz(nm), v), pan=0.15, gain=0.36 * gain)

def padbar(b, chord, gain=0.18, cutoff=1100, bars=1, motion=0.0):
    place(pads, bar(b), pad(CH[chord]['pad'], BAR * bars + 1.6, cutoff, a=1.0, r=1.6, motion=motion), gain=gain)

def bassbar(b, chord, pattern=(0,), level=0.5, dur=None):
    f = hz(CH[chord]['bass'])
    for q in pattern:
        place(bass, bar(b) + q * BEAT, sub(f, dur or BEAT * 3.6, 1.0), gain=level)

def groove(b, kick_beats=(0, 2), shaker_on=True, rim_beats=(), level=1.0):
    for q in kick_beats:
        t = bar(b) + q * BEAT
        place(drums, t, soft_kick(level), gain=0.55); kicks.append(t)
    if shaker_on:
        for e in range(8):
            place(drums, bar(b) + e * BEAT / 2 + 0.012 * rng.random(), shaker(level * (1.0 if e % 2 else 0.6)), pan=0.3, gain=0.07)
    for q in rim_beats:
        place(drums, bar(b) + q * BEAT, rim(level), pan=-0.15, gain=0.09)

# ---- GENESIS -------------------------------------------------------------------------------------------------------
# bars 0–2: the paper. A quiet motif over held chords.
motif = [[(0, 'F#5', 0.5), (1.5, 'A5', 0.42), (2, 'E5', 0.45)], [(0, 'D5', 0.48), (1.5, 'F#5', 0.4), (2.5, 'C#5', 0.42)],
         [(0, 'B4', 0.46), (1, 'D5', 0.4), (2, 'A4', 0.44), (3, 'F#4', 0.38)]]
for b in range(3):
    pchord(b, PROG[b], beats=(0,), vel=0.38, hands='lh')
    melody(b, motif[b])
    padbar(b, PROG[b], gain=0.09 + 0.02 * b, cutoff=800)
place(chimes, sec(2), bell(hz('A5'), 3.2, 1.4), gain=0.04, pan=-0.2)
# bars 3–4: the field opens to the horizon; pages land everywhere (a fine rain of soft ticks, growing)
for b in (3, 4):
    pchord(b, PROG[b], beats=(0, 2.5), vel=0.42)
    padbar(b, PROG[b], gain=0.16, cutoff=1300, motion=0.6)
    bassbar(b, PROG[b], level=0.32)
melody(3, [(0, 'A5', 0.5), (1, 'F#5', 0.42), (2, 'D5', 0.42), (3, 'E5', 0.4)])
melody(4, [(0, 'E5', 0.45), (2, 'D5', 0.4)])
t0, t1 = EV['land']
for k in range(140):
    u = (k / 140) ** 0.6
    t = sec(t0 + u * (t1 - t0)) + rng.random() * 0.05
    place(drums, t, tick(0.4 + 0.4 * u), pan=rng.uniform(-0.8, 0.8), gain=0.05 + 0.05 * u)
for k in range(18):                                    # highlights appear across the field: a scatter of high notes
    t = sec(EV['specks']) + k * 0.12 + rng.random() * 0.05
    place(chimes, t, bell(hz(['A6', 'C#7', 'E7', 'F#6', 'B6'][k % 5]), 1.2, 0.35), pan=rng.uniform(-0.7, 0.7), gain=0.018)
place(fx, sec(EV['line2']) - 1.2, swell(1.6, 0.6), gain=0.12)
# bar 5: inside the page — a hush; three highlights, three notes
pchord(5, 'Bm', beats=(0,), vel=0.34, hands='lh')
padbar(5, 'Bm', gain=0.08, cutoff=700)
melody(5, [(1, 'F#4', 0.36), (3, 'A4', 0.34)])
for k, fr in enumerate(EV['marks']):
    place(chimes, sec(fr), blip(hz(['D6', 'F#6', 'A6', 'D6', 'F#6', 'A6'][k]), 0.8), pan=-0.3 + 0.12 * k, gain=0.06 if k < 3 else 0.035)
# bars 6–7: the pieces lift off the page; a pulse begins
for k, fr in enumerate(EV['lift']):
    place(chimes, sec(fr), bell(hz(['A5', 'C#6', 'E6'][k]), 2.4, 1.0), pan=[-0.4, 0, 0.4][k], gain=0.07)
for b in (6, 7):
    pchord(b, PROG[b], beats=(0, 2), vel=0.4)
    padbar(b, PROG[b], gain=0.12, cutoff=1000 + 400 * (b - 6))
    bassbar(b, PROG[b], pattern=(0, 2), level=0.3, dur=BEAT * 1.8)
    for e in range(8):
        place(drums, bar(b) + e * BEAT / 2, shaker(0.5 + 0.1 * (b - 6)), pan=0.3, gain=0.045)
parp(7, 'A', [0, 1, 2, 3, 2, 3, 4, 5], vel=0.36)
place(fx, bar(7), swell(BAR, 1.0), gain=0.16)
# bars 8–9: release — everything rises and connects; the warmth opens up
place(fx, sec(EV['release']), bell(hz('D6'), 3.5, 1.6), gain=0.06)
for b in (8, 9):
    pchord(b, PROG[b], beats=(0,), vel=0.5)
    parp(b, PROG[b], [0, 1, 2, 3, 4, 3, 2, 1], vel=0.38)
    padbar(b, PROG[b], gain=0.2, cutoff=1600 + 400 * (b - 8), motion=0.4)
    bassbar(b, PROG[b], pattern=(0, 2), level=0.42, dur=BEAT * 1.9)
    groove(b, kick_beats=(0, 2), level=0.7 + 0.1 * (b - 8))
melody(9, [(0, 'F#5', 0.5), (1.5, 'A5', 0.45), (2, 'B5', 0.48), (3, 'A5', 0.42)])
# bars 10–11: a living graph — gentle groove; a soft pluck for every few arriving papers
for b in (10, 11):
    pchord(b, PROG[b], beats=(0, 2.5), vel=0.46)
    parp(b, PROG[b], [0, 2, 1, 3, 2, 4, 3, 5], vel=0.34)
    padbar(b, PROG[b], gain=0.2, cutoff=2000)
    bassbar(b, PROG[b], pattern=(0, 1.5, 2, 3.5), level=0.4, dur=BEAT * 1.2)
    groove(b, kick_beats=(0, 2), rim_beats=(1, 3), level=0.85)
melody(10, [(0, 'D6', 0.5), (1, 'B5', 0.42), (2, 'A5', 0.45), (3.5, 'F#5', 0.4)])
melody(11, [(0, 'E5', 0.46), (2, 'C#5', 0.4), (3, 'E5', 0.42)])
a0, a1 = EV['arrive']
for k in range(13):
    place(chimes, sec(a0 + (k + 0.5) / 13 * (a1 - a0)), bell(hz(['A6', 'F#6', 'E6', 'D6', 'B6'][k % 5]), 1.0, 0.3), pan=-0.6 + 0.1 * k, gain=0.02)

# ---- THE FIRST ONE (product) ----------------------------------------------------------------------------------------
place(fx, sec(EV['product']), bell(hz('A5'), 3.0, 1.2), gain=0.05)
for k in range(20):                                    # the flow diagram draws on
    t = sec(EV['draw'][0]) + k * (sec(EV['draw'][1]) - sec(EV['draw'][0])) / 20
    place(chimes, t, blip(hz(['D6', 'E6', 'F#6', 'A6', 'B6'][k % 5]), 0.5), pan=-0.7 + 1.4 * k / 20, gain=0.02)
for b in range(12, 24):
    ch = PROG[b]
    first = b == 12
    analyze = 18 <= b < 21
    agents = b >= 21
    pchord(b, ch, beats=(0, 2.5) if not first else (0,), vel=0.44)
    if not first:
        parp(b, ch, [0, 2, 1, 3, 2, 4, 3, 5] if not agents else [0, None, 2, None, 1, None, 3, None], vel=0.3 + 0.04 * analyze)
    padbar(b, ch, gain=0.15, cutoff=1500 + 300 * analyze)
    bassbar(b, ch, pattern=(0, 2) if not analyze else (0, 1.5, 2, 3.5), level=0.36, dur=BEAT * (1.8 if not analyze else 1.2))
    if not first:
        groove(b, kick_beats=(0, 2), rim_beats=(1, 3) if not agents else (), shaker_on=True, level=0.7 + 0.1 * analyze - 0.1 * agents)
for k, fr in enumerate(EV['clicks']):                  # each click goes one level deeper
    place(chimes, sec(fr), tick(1.0), gain=0.22)
    place(chimes, sec(fr), blip(hz(['A5', 'C#6', 'E6', 'A6'][k]), 0.8), gain=0.05)
for k in range(6):
    place(chimes, sec(EV['list_'] + k * 3), tick(0.5), pan=0.4, gain=0.08)
for k in range(26):                                    # the trends draw on, year by year
    t = sec(EV['analyze'] + 14) + (k / 25) ** 1.1 * sec(64)
    place(chimes, t, blip(hz(['D6', 'E6', 'F#6', 'A6', 'B6', 'D7'][min(5, k // 5)]), 0.35), pan=-0.8 + 1.6 * k / 25, gain=0.018)
place(chimes, sec(EV['meta']), tick(1.0), gain=0.22)
for k, fr in enumerate(EV['gaps']):
    place(chimes, sec(fr), bell(hz(['E6', 'F#6', 'A6', 'B6', 'C#7', 'E7'][k]), 0.9, 0.25), pan=0.2 + 0.1 * k, gain=0.03)
t0, t1 = EV['ask']
for k in range(24):
    place(chimes, sec(t0 + k * (t1 - t0) / 24) + rng.random() * 0.01, tick(0.5), pan=0.3, gain=0.12)
for fr in EV['calls'] + EV['results']:
    place(chimes, sec(fr), blip(hz('A6'), 0.7), pan=0.4, gain=0.04)
for k, nm in enumerate(['A5', 'C#6', 'E6']):
    place(chimes, sec(EV['answer']) + k * 0.22, bell(hz(nm), 1.6, 0.6), pan=-0.2 + 0.2 * k, gain=0.04)
place(fx, bar(22.5), swell(BAR * 1.5, 1.0), gain=0.16)  # the lift into every field
for i in range(5):
    place(chimes, sec(EV['gold'] + i * 8), bell(hz(['A5', 'C#6', 'E6', 'F#6', 'A6'][i]), 1.6, 0.6), pan=-0.3 + 0.15 * i, gain=0.04)

# ---- EVERY FIELD (finale) -----------------------------------------------------------------------------------------
place(fx, sec(EV['finale']), bell(hz('D6'), 3.6, 1.6), gain=0.06)
for b in range(24, 27):
    ch = PROG[b]
    pchord(b, ch, beats=(0, 2.5), vel=0.52)
    parp(b, ch, [0, 1, 2, 3, 4, 3, 2, 1], vel=0.38)
    padbar(b, ch, gain=0.24, cutoff=2400)
    bassbar(b, ch, pattern=(0, 1.5, 2, 3.5), level=0.45, dur=BEAT * 1.2)
    groove(b, kick_beats=(0, 2), rim_beats=(1, 3), level=0.95)
melody(24, [(0, 'F#5', 0.55), (1, 'A5', 0.5), (2, 'D6', 0.55), (3, 'C#6', 0.48)])
melody(25, [(0, 'D6', 0.55), (1.5, 'B5', 0.48), (2, 'A5', 0.5), (3, 'F#5', 0.45)])
melody(26, [(0, 'G5', 0.52), (1, 'A5', 0.48), (2, 'B5', 0.52), (3, 'A5', 0.46)])
for k in range(20):                                    # links between fields drawing on
    place(chimes, sec(EV['arcs']) + k * 0.13 + rng.random() * 0.04, blip(hz(['D6', 'E6', 'F#6', 'A6', 'B6'][k % 5]), 0.45), pan=rng.uniform(-0.8, 0.8), gain=0.022)
# the end card: one open chord, left to ring
tc = sec(EV['card'])
for k, nm in enumerate(['D2', 'A2', 'D3', 'A3', 'E4', 'F#4', 'A4', 'C#5', 'E5']):
    place(keys, tc + k * 0.035, piano(hz(nm), 0.5, 6.0), pan=-0.5 + k / 8, gain=0.3)
place(pads, tc, pad(['D3', 'A3', 'E4', 'F#4', 'C#5'], 6.5, 1800, a=0.3, r=4.5), gain=0.24)
place(bass, tc, sub(hz('D2'), 5.5, 1.0), gain=0.42)
place(drums, tc, soft_kick(0.9), gain=0.5); kicks.append(tc)
for k, nm in enumerate(['A5', 'D6', 'F#6', 'A6']):
    place(chimes, tc + 0.05 + k * 0.16, bell(hz(nm), 4.0, 1.8), pan=-0.4 + k * 0.27, gain=0.045)

# ---- mix ----------------------------------------------------------------------------------------------------------
duck = np.ones(N)                                      # a gentle sidechain from the soft kick
L = int(0.3 * SR); curve = 1 - 0.35 * np.exp(-np.arange(L) / SR / 0.1)
for t in kicks:
    i = int(t * SR)
    if i < N:
        j = min(N, i + L); duck[i:j] = np.minimum(duck[i:j], curve[:j - i])
dk = duck[:, None]
bass *= dk; pads *= dk ** 0.7

ir = make_ir(3.2)
wet = reverb(keys * 0.5 + pads * 0.5 + chimes * 0.9 + drums * 0.05 + fx * 0.4, ir, 0.42)
mix = keys * 1.0 + pads * 1.0 + bass * 1.0 + drums * 1.0 + chimes * 1.0 + fx * 1.0 + wet
mix = hp(mix, 28)
# section dynamics (bars → gain): quiet opening, a lift for the graph, steady product, open finale
curve_pts = [(0, 0.62), (3, 0.7), (5, 0.6), (6, 0.66), (7.9, 0.78), (8, 0.88), (10, 0.92), (12, 0.86), (18, 0.9), (21, 0.84), (23, 0.88),
             (24, 0.98), (27, 1.0), (30, 1.0)]
tb = np.arange(N) / SR / BAR
g = np.interp(tb, [c[0] for c in curve_pts], [c[1] for c in curve_pts])
mix *= signal.lfilter([0.002], [1, -0.998], g)[:, None]
env = signal.lfilter([1 - 0.9993], [1, -0.9993], np.abs(mix).max(axis=1))
mix = mix / np.maximum(1, (env / 0.4) ** 0.25)[:, None]
fade = np.clip((sec(END_F) + 1.5 - np.arange(N) / SR) / 2.5, 0, 1)
mix *= fade[:, None]
mix = np.tanh(mix * 1.15) / np.tanh(1.15)
mix = mix / np.abs(mix).max() * 0.92
print(f'duration {DUR:.1f}s  rms {20 * np.log10(np.sqrt((mix ** 2).mean())):.1f} dBFS  kicks {len(kicks)}')
wavfile.write('public/audio/score-calm.wav', SR, (mix * 32767).astype(np.int16))
