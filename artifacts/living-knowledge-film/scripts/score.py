"""Score v12 — driving electronic score at 120 bpm, synced to the picture (15 frames = 1 beat, 60 frames = 1 bar).

Structure (bars): 1665, one page 0–1.5 · the trickle 1.5–3 · the explosion 3–5 (hit on 2026) · groove A 5–11.5 ·
out of date, search, from scratch 11.5–17 · thesis 17–19 · build 19–24 · DROP 24–29 · psychedelic science 29–45 (the
whole field at a glance 37.5–42.5, agents 42.5–45) · lift 45 · all of science 46–50 · end chord 50–53.
Everything is synthesized here. Output: public/audio/score.wav (48 kHz stereo).
"""
import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
FPS = 30
BPM = 120
BEAT = 60 / BPM            # 0.5 s
BAR = BEAT * 4             # 2 s
END_F = 3180
DUR = END_F / FPS + 3.0
N = int(DUR * SR)
rng = np.random.default_rng(11)

sec = lambda f: f / FPS
bar = lambda b: b * BAR

# picture landmarks (global frames) — mirror src/Film.jsx (acts at 0 · 1020 · 1140 · 1740 · 2760) and the scene constants
EV = dict(
    # Act I (A = era 88, 2026 at 300, the paper lifts off 298, prose 376, links 466, synth 556, dated 656, search 750, scratch 880)
    page=2, era=90, y0=92, ym=172, y1=300, pick=316, highlights=[382, 385, 388, 391, 394, 397], links=[462, 466, 470, 474],
    arcs=[496, 502, 508, 514, 520, 526], gather0=558, gather1=606, review=624, dated=656, search=750, typing=(786, 800), typing2=(892, 906),
    scan1=810, scratch=880, scan2=914, cut=1020,
    # thesis (at 1020)
    slams=[1065, 1080, 1095], act2=1140,
    # Act II (at 1140; B = sweep 90, grid 240, drop 300, living 420, title 480)
    statement=1146, blade=1208, sweep=1230, grid=1380, drop=1440, bridges=1496, living=1560, arrive0=1528, arrive1=1736, title=1562,
    # Act III (at 1740; S = explore 150, hover 196, click 232, edge 300, list 336, pick 408, paper 456, analyze 510 (the
    # publication history's bars rise from 526, one every 2 frames; the evidence bars from 560, the gaps fill from 586), meta 690,
    # gaps 722 + 4k, agents 810, graph 960)
    act3=1740, land=1800, explore=1890, hover=1936, click=1972, edge=2040, list=2076, fpick=2148, paper=2196, analyze=2250,
    history=(2266, 2316), bars=2300, cells=2326, meta=2430, gaps=[2462, 2466, 2470, 2474, 2478, 2482], agents=2550,
    ask=(2570, 2588), calls=[2592, 2612], results2=[2604, 2628], answer=2640, graph=2700, gold=2714,
    # Act IV (at 2760; D = tagline 120, card 240)
    act4=2760, arcs4=2818, tagline=2880, card=3000,
)

# ---- note helpers -------------------------------------------------------------
NAMES = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5, 'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}
def hz(n):
    return 440.0 * 2 ** ((NAMES[n[:-1]] + 12 * (int(n[-1]) + 1) - 69) / 12)

CH = {
    'F#m': dict(root='F#1', saw=['F#3', 'C#4', 'F#4', 'A4'], arp=['F#4', 'A4', 'C#5', 'E5']),
    'D': dict(root='D1', saw=['D3', 'A3', 'D4', 'F#4'], arp=['D4', 'F#4', 'A4', 'C#5']),
    'A': dict(root='A1', saw=['A2', 'E3', 'A3', 'C#4'], arp=['A4', 'C#5', 'E5', 'B4']),
    'E': dict(root='E1', saw=['E3', 'B3', 'E4', 'G#4'], arp=['E4', 'G#4', 'B4', 'D#5']),
    'Bm': dict(root='B0', saw=['B2', 'F#3', 'B3', 'D4'], arp=['B4', 'D5', 'F#5', 'A4']),
}

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

def sweep_lp(x, f0, f1, curve=1.0, q=0.8):
    """time-varying lowpass (block-wise, state carried)."""
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

# ---- instruments ------------------------------------------------------------------
def kick(level=1.0):
    n = int(0.42 * SR); t = np.arange(n) / SR
    fr = 46 + 95 * np.exp(-t * 30) + 40 * np.exp(-t * 200)
    body = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-t * 7.5)
    click = hp(rng.standard_normal(n), 2500) * np.exp(-t * 300) * 0.35
    return np.tanh((body + click) * 1.6) * 0.9 * level

def clap(level=1.0):
    n = int(0.35 * SR); t = np.arange(n) / SR
    x = np.zeros(n)
    for k, d in enumerate([0, 0.009, 0.019, 0.03]):
        i = int(d * SR)
        x[i:] += rng.standard_normal(n - i) * np.exp(-(t[:n - i]) * (160 if k < 3 else 22)) * (0.7 if k < 3 else 1.0)
    x = bp(x, 900, 5200)
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 40) * 0.4
    return (x * 0.9 + body) * level

def hat(open_=False, level=1.0):
    n = int((0.22 if open_ else 0.06) * SR); t = np.arange(n) / SR
    x = hp(rng.standard_normal(n), 7500, 4) * np.exp(-t * (18 if open_ else 90))
    return x * level

def bass_note(f, dur, cutoff=420, drive=1.8):
    n = int(dur * SR); t = np.arange(n) / SR
    x = saw(f, n) * 0.7 + saw(f * 1.004, n, 0.3) * 0.5 + np.sin(2 * np.pi * f * t) * 0.9
    env_f = cutoff * (1 + 3.5 * np.exp(-t * 14))
    x = sweep_lp(x, env_f[0], env_f[-1] if n > 1 else cutoff, 0.35)
    x = np.tanh(x * drive) / np.tanh(drive)
    amp = np.minimum(1, t / 0.004) * np.exp(-t * 2.2)
    rel = np.ones(n); r = min(n, int(0.02 * SR)); rel[-r:] = np.linspace(1, 0, r)
    return x * amp * rel

def supersaw(notes, dur, cutoff=3800, voices=7, spread=0.22):
    n = int(dur * SR)
    out = np.zeros((n, 2))
    for nm in notes:
        f = hz(nm)
        for v in range(voices):
            det = (v - (voices - 1) / 2) / ((voices - 1) / 2) * spread
            fv = f * 2 ** (det / 12)
            x = saw(fv, n, rng.random())
            pan = det / spread * 0.85
            out[:, 0] += x * np.cos((pan + 1) * np.pi / 4)
            out[:, 1] += x * np.sin((pan + 1) * np.pi / 4)
    out /= voices * len(notes) ** 0.5
    out = lp(out, cutoff, 2)
    t = np.arange(n) / SR
    env = np.minimum(1, t / 0.01) * (0.85 + 0.15 * np.exp(-t * 3))
    r = int(0.05 * SR); env[-r:] *= np.linspace(1, 0, r)
    return out * env[:, None]

def pad(notes, dur, cutoff=1400, a=1.2, r=1.5):
    n = int(dur * SR); out = np.zeros((n, 2))
    for nm in notes:
        for v in range(4):
            fv = hz(nm) * 2 ** ((v - 1.5) * 0.08 / 12)
            x = saw(fv, n, rng.random())
            pan = (v / 3) * 1.4 - 0.7
            out[:, 0] += x * np.cos((pan + 1) * np.pi / 4); out[:, 1] += x * np.sin((pan + 1) * np.pi / 4)
    out = lp(out / (4 * len(notes) ** 0.5), cutoff)
    t = np.arange(n) / SR
    env = np.minimum(1, t / a) * np.minimum(1, (dur - t) / r).clip(0, 1)
    return out * env[:, None]

def pluck(f, dur=0.35, cutoff=5000, decay=0.16):
    n = int(dur * SR); t = np.arange(n) / SR
    x = saw(f, n) * 0.55 + (2 * (np.sin(2 * np.pi * f * t) > 0) - 1) * 0.35
    x = sweep_lp(x, cutoff, 500, 0.5)
    return x * np.exp(-t / decay) * np.minimum(1, t / 0.002)

def bell(f, dur=1.6, decay=0.7):
    n = int(dur * SR); t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t * 4) + 0.2 * np.sin(2 * np.pi * f * 3.01 * t) * np.exp(-t * 7)
    return x * np.exp(-t / decay) * np.minimum(1, t / 0.002)

def impact(level=1.0, dur=2.6):
    n = int(dur * SR); t = np.arange(n) / SR
    fr = 30 + 90 * np.exp(-t * 9)
    boom = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-t * 1.9)
    crack = lp(rng.standard_normal(n), 3000) * np.exp(-t * 18) * 0.6
    air = hp(rng.standard_normal(n), 4000) * np.exp(-t * 3.5) * 0.12
    x = np.tanh((boom * 1.3 + crack + air) * 1.4)
    return np.stack([x, np.roll(x, 150)], axis=1) * level

def riser(dur, level=1.0):
    n = int(dur * SR); t = np.linspace(0, 1, n)
    noise = hp(rng.standard_normal(n), 600)
    noise = sweep_lp(noise, 800, 14000, 1.4)
    tone = np.sin(2 * np.pi * np.cumsum(220 * 2 ** (t * 2.2)) / SR) * 0.25
    e = t ** 2.2
    y = (noise * 0.7 + tone) * e
    return np.stack([y, np.roll(y, 300)], axis=1) * level

def reverse_cymbal(dur=1.0, level=1.0):
    n = int(dur * SR); t = np.linspace(0, 1, n)
    y = hp(rng.standard_normal(n), 5000) * t ** 3
    return np.stack([y, np.roll(y, 200)], axis=1) * level

def whoosh(dur=1.2, level=1.0, up=True):
    n = int(dur * SR); t = np.linspace(0, 1, n)
    x = rng.standard_normal(n)
    x = sweep_lp(x, 500 if up else 6000, 7000 if up else 400, 1.0)
    e = np.sin(np.pi * t) ** 2
    pan = (t - 0.5) * 1.4
    return np.stack([x * e * np.cos((pan + 1) * np.pi / 4), x * e * np.sin((pan + 1) * np.pi / 4)], axis=1) * level

def blip(f, level=1.0):
    n = int(0.12 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * f * t) * np.exp(-t * 40) * level

def tick(level=1.0):
    n = int(0.03 * SR); t = np.arange(n) / SR
    return hp(rng.standard_normal(n), 4000) * np.exp(-t * 300) * level

# ---- reverb / delay -----------------------------------------------------------------
def make_ir(rt=2.2):
    n = int(rt * 1.2 * SR); t = np.arange(n) / SR
    ir = np.stack([rng.standard_normal(n) * np.exp(-6.9 * t / rt) for _ in range(2)], axis=1)
    ir = lp(ir, 5000)
    return ir / np.sqrt((ir ** 2).sum() / 2)

def reverb(x, ir, wet):
    return np.stack([signal.fftconvolve(x[:, c], ir[:, c])[:len(x)] for c in range(2)], axis=1) * wet

def delay(x, d=BEAT * 0.75, fb=0.35, mix=0.3):
    D = int(d * SR); y = x.copy(); src = x.copy()
    for k in range(1, 5):
        sh = np.zeros_like(x); sh[D * k:] = src[:-D * k]
        y += (sh[:, ::-1] if k % 2 else sh) * mix * fb ** (k - 1)
    return y

# =====================================================================================
drums, bass, chords, arps, pads, fx, keys_ = buf(), buf(), buf(), buf(), buf(), buf(), buf()
kicks = []

def drum_bar(b, kick_on=True, clap_on=False, hats='8', open_hat=False, level=1.0, kick_beats=(0, 1, 2, 3), clap_beats=(1, 3), clap_level=1.0):
    t0 = bar(b)
    for q in range(4):
        tb = t0 + q * BEAT
        if kick_on and q in kick_beats:
            place(drums, tb, kick(level), gain=0.95); kicks.append(tb)
        if clap_on and q in clap_beats:
            place(drums, tb, clap(level * clap_level), gain=0.42)
        if hats == '8':
            place(drums, tb + BEAT / 2, hat(level=level), pan=0.25, gain=0.13)
        elif hats == '16':
            for s in range(4):
                place(drums, tb + s * BEAT / 4, hat(level=level * (1 if s == 2 else 0.5)), pan=0.25, gain=0.11)
        if open_hat:
            place(drums, tb + BEAT / 2, hat(True, level), pan=-0.2, gain=0.08)

def bass_bar(b, chord, style='offbeat', level=1.0, cutoff=420):
    f = hz(CH[chord]['root'])
    t0 = bar(b)
    if style == 'offbeat':
        for q in range(4):
            place(bass, t0 + q * BEAT + BEAT / 2, bass_note(f, BEAT / 2, cutoff), gain=0.5 * level)
    elif style == 'rolling':
        for s in range(16):
            if s % 4 == 0:
                continue
            ff = f * (2 if s % 4 == 2 else 1)
            place(bass, t0 + s * BEAT / 4, bass_note(ff, BEAT / 4, cutoff + 200), gain=0.42 * level)
    elif style == 'pulse':
        for s in range(8):
            place(bass, t0 + s * BEAT / 2, bass_note(f, BEAT / 2, cutoff), gain=0.4 * level)

def arp_bar(b, chord, level=1.0, cutoff=5200, pattern=(0, 1, 2, 3, 2, 1, 2, 3, 0, 2, 1, 3, 2, 3, 1, 2)):
    tones = CH[chord]['arp']
    for s in range(16):
        f = hz(tones[pattern[s]]) * (2 if s in (7, 15) else 1)
        place(arps, bar(b) + s * BEAT / 4, pluck(f, 0.3, cutoff), pan=np.sin(s * 0.9) * 0.45, gain=0.075 * level * (1.0 if s % 4 == 0 else 0.7))

def saw_bar(b, chord, level=1.0, cutoff=3800, bars=1):
    place(chords, bar(b), supersaw(CH[chord]['saw'], BAR * bars, cutoff), gain=0.34 * level)

def scratch(dur, level=1.0):
    """a pen stroke: a short band of paper-noise"""
    n = int(dur * SR); t = np.arange(n) / SR
    x = bp(rng.standard_normal(n), 1900, 7000)
    return x * np.minimum(1, t / 0.004) * np.minimum(1, (dur - t) / 0.012).clip(0, 1) * level

def aging(dur, f0, level=1.0):
    """a held tone that slowly sags and darkens — synthesis falling out of date"""
    n = int(dur * SR); t = np.arange(n) / SR
    bend = 2 ** (-(t / dur) ** 1.6 * 1.6 / 12)
    ph = 2 * np.pi * np.cumsum(f0 * bend) / SR
    x = np.sin(ph) + 0.35 * np.sin(2 * ph + 0.4) + 0.15 * np.sin(3 * ph)
    x = sweep_lp(x, 3000, 500, 0.8)
    env = np.minimum(1, t / 0.4) * np.minimum(1, (dur - t) / 0.8).clip(0, 1)
    y = x * env * level
    return np.stack([y, np.roll(y, 240)], axis=1)

def tape_stop(dur=0.5, level=1.0):
    n = int(dur * SR); t = np.arange(n) / SR
    f = 180 * (1 - t / dur) ** 2 + 30
    x = np.tanh(np.sin(2 * np.pi * np.cumsum(f) / SR) * 2) * (1 - t / dur)
    return np.stack([x, x], axis=1) * level

# ---- I · 1665 (bars 0–1.5): one page -------------------------------------------------------------------
place(pads, 0, pad(['F#3', 'C#4', 'A4'], bar(3) + 1.0, 750, a=1.6), gain=0.3)
place(keys_, sec(EV['page']), bell(hz('C#6'), 3.5, 1.5), gain=0.07)
place(keys_, sec(EV['page']) + 0.08, bell(hz('F#5'), 3.5, 1.5), gain=0.05, pan=-0.3)
for q in range(6):
    place(drums, bar(0) + q * BEAT, tick(0.25), pan=0.3, gain=0.18)

# ---- I · THE TRICKLE, THEN THE EXPLOSION (bars 1.5–5): one grain per paper, hit on 2026 ----------------------
Y0, YM, Y1 = EV['y0'], EV['ym'], EV['y1']
def frame_of_year(y):
    return Y0 + (YM - Y0) * max(0.0, (y - 1665) / 235) ** (1 / 1.6) if y <= 1900 else YM + (Y1 - YM) * ((y - 1900) / 126) ** (1 / 1.15)
colN = [max(1, round(1.4 * np.exp(0.19 * c))) for c in range(37)]
land = np.sort(np.array([frame_of_year(1665 + 10 * c + 10 * (k + 0.5) / n) for c, n in enumerate(colN) for k in range(n)]))
dens = np.array([np.sum(np.abs(land - x) < 1.5) / 0.1 for x in land])
for x, d in zip(land, dens):
    u = min(1.0, max(0.0, (x - Y0) / (Y1 - Y0)))
    g = min(0.22, 0.22 * (max(1.0, d / 6)) ** -0.45)
    if d < 12:   # the early papers land one by one: a soft wooden tap each
        place(keys_, sec(x), pluck(hz(rng.choice(['F#5', 'A5', 'C#6', 'E6'])), 0.25, 3000, 0.08), pan=-0.6 + 1.2 * u, gain=0.08)
    place(keys_, sec(x) + rng.random() / FPS, blip(1300 * 2 ** (u * 1.8 + rng.random() * 0.3), 0.7), pan=-0.8 + 1.6 * u + rng.uniform(-0.2, 0.2), gain=g * 0.45)
    place(drums, sec(x) + rng.random() / FPS, tick(0.8), pan=rng.uniform(-0.6, 0.6), gain=g * 0.6)
for b in range(1, 3):
    bass_bar(b + 0.5 - 0.5, 'F#m', 'pulse', level=0.3 + 0.12 * b, cutoff=230 + b * 50)
for b in range(3, 5):
    drum_bar(b, kick_on=True, clap_on=b == 4, hats='16' if b == 4 else '8', level=0.7 + 0.1 * (b - 3))
    bass_bar(b, 'F#m', 'pulse', level=0.6 + 0.15 * (b - 3), cutoff=320 + (b - 3) * 120)
    arp_bar(b, 'F#m', level=0.35 + 0.25 * (b - 3), cutoff=2400 + (b - 3) * 1800)
place(fx, sec(YM), riser(sec(Y1 - YM), 0.9), gain=0.45)
for k in range(9):          # papers rushing past the lens
    t = sec(236) + (k / 9) ** 0.7 * sec(62)
    place(fx, t, whoosh(0.6 + rng.random() * 0.4, 0.3), pan=rng.choice([-0.7, 0.7]), gain=0.16 + 0.03 * k)
place(fx, sec(Y1) - 0.6, reverse_cymbal(0.6), gain=0.35)
place(fx, sec(Y1), impact(1.1, 3.2), gain=0.75)
place(drums, sec(Y1), kick(1.0), gain=1.0); kicks.append(sec(Y1))
place(chords, sec(Y1), supersaw(CH['A']['saw'], 1.2, 3600) * np.linspace(1, 0, int(1.2 * SR))[:, None], gain=0.4)

# ---- I · GROOVE A (bars 5–11.5): F#m – D – A – E, tense and driving -------------------------------------------
prog_a = ['F#m', 'D', 'A', 'E']
for b in range(5, 12):
    ch = prog_a[(b - 5) % 4]
    drum_bar(b, kick_on=True, clap_on=b >= 7, hats='16' if b >= 6 else '8', open_hat=b >= 9, level=0.82 + 0.04 * (b >= 7))
    bass_bar(b, ch, 'offbeat', level=0.9, cutoff=380 + (b - 5) * 26)
    arp_bar(b, ch, level=(0.5 + 0.05 * (b - 5)) * (0.55 if b >= 9 else 1), cutoff=1800 + (b - 5) * 300)
    place(pads, bar(b), pad(CH[ch]['saw'], BAR + 0.3, 1100 + (b - 5) * 130, a=0.3, r=0.3), gain=0.26)
place(fx, sec(EV['pick']) - 0.2, whoosh(1.4, 0.45), gain=0.3)
for k, fr in enumerate(EV['highlights']):          # findings · methods · context light up
    place(keys_, sec(fr), blip(hz(['F#5', 'A5', 'C#6', 'E6', 'F#6', 'A6'][k]), 1.0), pan=-0.3 + k * 0.12, gain=0.12)
for k, fr in enumerate(EV['links']):
    place(fx, sec(fr), whoosh(0.7, 0.25), pan=[-0.6, 0.6, -0.5, 0.5][k], gain=0.18)
for k, fr in enumerate(EV['arcs']):
    place(keys_, sec(fr), bell(hz(['C#6', 'E6', 'F#6', 'A6', 'E6', 'C#6'][k]), 0.9, 0.3), pan=[-0.5, 0.5, -0.4, 0.4, -0.2, 0.2][k], gain=0.05)
place(fx, sec(EV['search']), whoosh(1.6, 0.4, up=False), gain=0.3)     # the new studies join thousands of search results
t0, t1 = EV['typing']
for k in range(23):
    place(keys_, sec(t0 + k * (t1 - t0) / 23) + rng.random() * 0.012, tick(0.7), pan=0.2, gain=0.22)
def scan(start, end, seed):
    r2 = np.random.default_rng(seed); k = 0
    while start + k * 1.6 < end:
        tt = sec(start + k * 1.6)
        place(keys_, tt, tick(0.8), pan=r2.uniform(-0.6, 0.6), gain=0.11)
        if r2.random() < 0.11:
            place(keys_, tt, blip(hz('A6'), 0.9), pan=0.2, gain=0.05)
        k += 1
scan(EV['scan1'], EV['scratch'], 5)

# ---- I · SYNTHESIS, OUT OF DATE, FROM SCRATCH (bars 11.5–17) ------------------------------------------------------
for b in range(12, 17):
    drum_bar(b, kick_on=b not in (14,), clap_on=b == 12, hats='8' if b < 15 else None, level=0.72)
    bass_bar(b, ['D', 'A', 'F#m', 'F#m', 'E'][b - 12], 'pulse', level=0.72, cutoff=300 + (b - 12) * 40)
    place(pads, bar(b), pad(CH[['D', 'A', 'F#m', 'F#m', 'E'][b - 12]]['saw'], BAR + 0.3, 900, a=0.4, r=0.4), gain=0.22)
for k in range(28):                                # the relevant studies fly into a pile
    tt = EV['gather0'] + (k / 28) ** 0.8 * (EV['gather1'] - EV['gather0'])
    place(drums, sec(tt), tick(0.9), pan=0.4, gain=0.26)
place(fx, sec(EV['review']), impact(0.6, 1.8), gain=0.42)           # … bound into one review
place(keys_, sec(EV['review']), bell(hz('F#5'), 2.2, 0.8), gain=0.07)
place(fx, sec(EV['dated']) + 0.3, aging(sec(EV['search'] - EV['dated']) + 0.3, hz('C#5'), 1.0), gain=0.05)
for k in range(65):                                # new studies land on the timeline after the review, year by year
    tt = EV['dated'] + 16 + (k / 65) ** 0.85 * 72
    place(keys_, sec(tt), pluck(hz(rng.choice(['F#5', 'A5', 'C#6', 'E6'])), 0.22, 2600, 0.06), pan=-0.1 + 0.6 * k / 65, gain=0.07)
    place(drums, sec(tt) + rng.random() / FPS, tick(0.6), pan=0.1 + 0.5 * k / 65, gain=0.1)
place(fx, sec(EV['scratch']) - 0.25, tape_stop(0.5, 1.0), gain=0.3)   # … and the next reader starts over
t0, t1 = EV['typing2']                             # the query, typed again from nothing
for k in range(23):
    place(keys_, sec(t0 + k * (t1 - t0) / 23) + rng.random() * 0.012, tick(0.7), pan=0.2, gain=0.2)
place(fx, sec(EV['scratch']), whoosh(1.2, 0.35), gain=0.22)
scan(EV['scan2'], EV['cut'] - 8, 9)
for q in range(16):
    place(drums, bar(16) + q * BEAT / 4, clap(0.3 + q / 16 * 0.6), gain=0.16 + q * 0.01)
place(fx, bar(15.5), riser(bar(1.5), 0.8), gain=0.4)
place(fx, sec(EV['cut']) - 0.5, reverse_cymbal(0.5), gain=0.3)

# ---- THESIS (bars 17–19): "It's time to rethink how scientific knowledge is — stored. synthesized. accessed." ----
place(fx, sec(EV['cut']), impact(1.0, 3.0), gain=0.6)
place(pads, sec(EV['cut']), pad(['F#2', 'C#3', 'F#3'], BAR * 2, 500, a=0.05, r=1.0), gain=0.3)
for k, fr in enumerate(EV['slams']):
    t = sec(fr)
    place(drums, t, kick(1.0), gain=1.0); kicks.append(t)
    place(drums, t, clap(1.0), gain=0.45)
    place(fx, t, impact(0.55, 1.4), gain=0.35)
    place(chords, t, supersaw(CH[['F#m', 'D', 'E'][k]]['saw'], 0.42, 3200), gain=0.42)
place(fx, sec(EV['act2']) - 1.4, riser(1.4, 0.8), gain=0.35)
place(fx, sec(EV['act2']) - 0.5, reverse_cymbal(0.5), gain=0.3)

# ---- II · BUILD (bars 19–24): the blade sweeps the whole field ----------------------------------------------------
prog_b = ['D', 'E', 'F#m', 'D', 'E']
for i, b in enumerate(range(19, 24)):
    ch = prog_b[i]
    drum_bar(b, kick_on=(b >= 21), clap_on=False, hats='16' if b >= 22 else '8', level=0.7 + 0.06 * i)
    bass_bar(b, ch, 'pulse', level=0.7 + 0.06 * i, cutoff=300 + i * 70)
    arp_bar(b, ch, level=0.75 + 0.06 * i, cutoff=2400 + i * 600)
    place(pads, bar(b), pad(CH[ch]['saw'], BAR + 0.3, 1600 + i * 350, a=0.4, r=0.3), gain=0.3)
place(fx, sec(EV['act2']), impact(0.5, 2.0), gain=0.3)
place(fx, sec(EV['blade']), whoosh(1.6, 0.4), gain=0.25)
PENTA = ['A5', 'B5', 'C#6', 'E6', 'F#6', 'A6', 'B6', 'C#7', 'E7']
for k in range(150):   # every paper opening into what it reports: a rising shimmer that follows the blade
    u = k / 150
    t = sec(EV['sweep']) + u * sec(EV['grid'] - EV['sweep']) + rng.random() * 0.03
    nm = PENTA[min(len(PENTA) - 1, int(u * len(PENTA) + rng.random() * 2))]
    place(keys_, t, blip(hz(nm), 0.5 + 0.3 * rng.random()), pan=0.8 - 1.6 * u, gain=0.045)   # the blade reads right to left
for q in range(32):
    place(drums, bar(22) + q * BEAT / 4, clap(0.3 + q / 32 * 0.7), gain=0.14 + q * 0.008)
place(fx, bar(22), riser(bar(2), 1.0), gain=0.5)
place(fx, sec(EV['drop']) - 1.0, reverse_cymbal(1.0), gain=0.35)

# ---- II · DROP (bars 24–29): A – E – F#m – D – A; the last bar hands over to Act III's D without stopping -------------
prog_c = ['A', 'E', 'F#m', 'D']
place(fx, sec(EV['drop']), impact(1.0, 3.4), gain=0.75)
for b in range(24, 29):
    ch = prog_c[(b - 24) % 4]
    last = b == 28                                 # the hand-over bar: the groove keeps going while the drop closes its filter
    drum_bar(b, kick_on=True, clap_on=True, hats='8' if last else '16', open_hat=not last, level=0.9 if last else 1.0)
    if last:
        for s in range(16):
            if s % 4:
                place(bass, bar(b) + s * BEAT / 4, bass_note(hz(CH[ch]['root']) * (2 if s % 4 == 2 else 1), BEAT / 4, 720 - 340 * s / 16), gain=0.4)
        place(chords, bar(b), sweep_lp(supersaw(CH[ch]['saw'], BAR, 5200), 5200, 700, 0.9), gain=0.3)
    else:
        bass_bar(b, ch, 'rolling', level=1.0, cutoff=520)
        saw_bar(b, ch, level=1.0, cutoff=4200 if b < 27 else 5200)
    arp_bar(b, ch, level=0.9 if last else 1.0, cutoff=5200 if last else 6500)
place(keys_, sec(EV['bridges']), bell(hz('E6'), 2.4, 1.2), gain=0.1)
place(fx, sec(EV['living']) - 0.2, whoosh(1.8, 0.35), gain=0.22)
place(fx, sec(EV['title']), impact(0.7, 2.4), gain=0.4)
place(drums, sec(EV['title']), hat(True, 1.2), gain=0.3)
for q in range(8):                                 # a clap roll leads into the cut
    place(drums, bar(28) + 2 * BEAT + q * BEAT / 4, clap(0.35 + q * 0.08), gain=0.13 + q * 0.012)
place(fx, sec(EV['act3']) - 0.8, reverse_cymbal(0.8), gain=0.3)

# ---- III · PSYCHEDELIC SCIENCE (bars 29–45): the product as motion graphics, then agents ------------------------------
prog_d = ['D', 'A', 'E', 'F#m']
place(pads, sec(EV['act3']), pad(CH['D']['saw'], BAR * 1.4, 1900, a=0.35, r=0.8), gain=0.34)   # the chord that carries the cut
place(fx, sec(EV['act3']), whoosh(2.2, 0.5), gain=0.24)
place(fx, sec(EV['act3']), impact(0.45, 2.2), gain=0.26)                  # the cut lands on the downbeat
for k in range(40):                                # the flow diagram draws on
    place(keys_, sec(EV['act3'] + 44 + k * 0.9) + rng.random() * 0.02, blip(hz(PENTA[k % len(PENTA)]), 0.5), pan=-0.7 + 1.4 * k / 40, gain=0.035)
place(fx, sec(EV['land']), impact(0.45, 2.0), gain=0.3)          # it lands on the bar
place(keys_, sec(EV['land']), bell(hz('A5'), 2.0, 0.9), gain=0.09)
place(keys_, sec(EV['land']) + 0.06, bell(hz('E6'), 2.0, 0.9), gain=0.07, pan=0.3)
for b in range(29, 45):
    ch = prog_d[(b - 29) % 4]
    intro = b == 29                                # the beat goes half-time while the graph becomes the diagram, whole again as it lands
    busy = 38 <= b < 42                            # the whole field at a glance
    turn = b == 42                                 # hand-over to the agent's session: the last clap falls just before the cut to it
    calm = b >= 43                                 # the agent's session
    drum_bar(b, kick_on=True, kick_beats=(0, 2) if intro else (0, 1, 2, 3), clap_on=(b >= 32 and not calm), clap_beats=(1,) if turn else (1, 3),
             clap_level=0.7 if turn else 1.0, hats='8' if b < 31 else '16', open_hat=busy, level=0.72 if intro else 0.8 + 0.08 * busy - 0.04 * turn - 0.08 * calm)
    bass_bar(b, ch, 'offbeat', level=0.75 if intro else 0.85, cutoff=400 if intro else 460 + 90 * busy - 40 * turn)
    arp_bar(b, ch, level=0.8 * (0.65 if calm else 0.82 if turn else 1), cutoff=4600 if intro else 5200 + 800 * busy)
    place(pads, bar(b), pad(CH[ch]['saw'], BAR + 0.3, 2200, a=0.3, r=0.3), gain=0.24)
place(fx, sec(EV['explore']) - 0.2, whoosh(1.0, 0.3), gain=0.18)
place(keys_, sec(EV['hover']), blip(hz('E6'), 0.8), gain=0.07)
for fr, nm in [(EV['click'], 'A6'), (EV['edge'], 'C#7'), (EV['fpick'], 'E6'), (EV['paper'], 'A6')]:   # each click goes one level deeper
    place(keys_, sec(fr), tick(1.2), gain=0.35)
    place(keys_, sec(fr), blip(hz(nm), 0.8), gain=0.07)
for k in range(7):                                 # the findings list fills in
    place(keys_, sec(EV['list'] + 2 + k * 3), tick(0.6), pan=0.4, gain=0.12)
place(fx, sec(EV['fpick']), whoosh(0.8, 0.25), gain=0.16)
place(fx, sec(EV['paper']) + 0.1, whoosh(0.9, 0.28), gain=0.18)
place(keys_, sec(EV['paper']) + 0.2, bell(hz('E6'), 1.6, 0.7), gain=0.06)
place(fx, sec(EV['analyze']) - 0.3, whoosh(1.2, 0.35), gain=0.24)
t0, t1 = EV['history']                             # the publication history rises, a bar a year: a rising run across the stereo field
for k in range(26):
    place(keys_, sec(t0 + (k / 25) * (t1 - t0)), blip(hz(PENTA[min(len(PENTA) - 1, k // 3)]), 0.4), pan=-0.8 + 1.6 * k / 25, gain=0.026)
for k in range(6):                                 # the evidence bars, one compound after another
    place(keys_, sec(EV['bars'] + k * 5), pluck(hz(['A5', 'C#6', 'E6', 'F#6', 'A6', 'B6'][k]), 0.25, 2800, 0.07), pan=-0.5 + k * 0.08, gain=0.06)
for k in range(16):                                # the gaps matrix fills in
    place(keys_, sec(EV['cells'] + k * 1.6) + rng.random() * 0.02, tick(0.5), pan=0.3 + 0.03 * k, gain=0.09)
place(keys_, sec(EV['meta']), tick(1.1), gain=0.3)  # one click: meta-analyses, and the matrix re-draws column by column
for q in range(6):
    place(keys_, sec(EV['meta'] + 3) + q * 0.075, blip(hz(PENTA[(8 - q) % len(PENTA)]), 0.4), pan=0.1 + q * 0.12, gain=0.03)
for k, fr in enumerate(EV['gaps']):                # the gaps, outlined one after another
    place(keys_, sec(fr), pluck(hz(['E6', 'F#6', 'A6', 'B6', 'C#7', 'E7'][k]), 0.3, 3200, 0.1), pan=0.2 + k * 0.1, gain=0.06)
place(fx, sec(EV['agents']) - 0.7, reverse_cymbal(0.7), gain=0.22)       # into the agent's session
place(fx, sec(EV['agents']), whoosh(1.2, 0.35), gain=0.25)
t0, t1 = EV['ask']
for k in range(30):
    place(keys_, sec(t0 + k * (t1 - t0) / 30) + rng.random() * 0.01, tick(0.6), pan=0.3, gain=0.22)
for fr in EV['calls']:
    place(keys_, sec(fr), blip(hz('E6'), 0.9), pan=0.4, gain=0.08)
for fr in EV['results2']:
    place(keys_, sec(fr), blip(hz('A6'), 0.9), pan=0.4, gain=0.08)
for k, nm in enumerate(['A5', 'C#6', 'E6']):       # the answer, and its three links drawing to PTSD
    place(keys_, sec(EV['answer']) + k * 0.2, bell(hz(nm), 1.4, 0.6), pan=-0.2 + k * 0.2, gain=0.06)

# ---- III · LIFT (bar 45): the graph returns, the evidence lights up gold ------------------------------------------------
drum_bar(45, kick_on=True, clap_on=False, hats='16', level=0.85)
bass_bar(45, 'E', 'pulse', level=0.9, cutoff=560)
arp_bar(45, 'E', level=0.95, cutoff=6200)
place(pads, bar(45), pad(CH['E']['saw'], BAR + 0.3, 3200, a=0.3, r=0.3), gain=0.3)
for i in range(5):
    place(keys_, sec(EV['gold'] + i * 8), bell(hz(['A5', 'C#6', 'E6', 'F#6', 'A6'][i]), 1.4, 0.6), pan=-0.3 + i * 0.15, gain=0.08)
for q in range(16):
    place(drums, bar(45) + q * BEAT / 4, clap(0.3 + q / 16 * 0.6), gain=0.16 + q * 0.01)
place(fx, bar(44.5), riser(bar(1.5), 0.9), gain=0.4)
place(fx, sec(EV['act4']) - 1.0, reverse_cymbal(1.0), gain=0.35)

# ---- IV · ALL OF SCIENCE (bars 46–50): the pull-back is the peak ----------------------------------------------------------
prog_e = ['F#m', 'D', 'A', 'E']
place(fx, sec(EV['act4']), impact(1.1, 3.4), gain=0.75)
place(fx, sec(EV['act4']), whoosh(2.6, 0.45), gain=0.3)
for i, b in enumerate(range(46, 50)):
    ch = prog_e[i]
    drum_bar(b, kick_on=True, clap_on=True, hats='16', open_hat=True, level=1.0)
    bass_bar(b, ch, 'rolling', level=1.0, cutoff=540)
    saw_bar(b, ch, level=0.9, cutoff=4600 + i * 300)
    arp_bar(b, ch, level=1.0, cutoff=7000)
for k in range(24):                                # links between fields drawing on
    place(keys_, sec(EV['arcs4']) + k * 0.12 + rng.random() * 0.05, blip(hz(PENTA[(k * 3) % len(PENTA)]), 0.55), pan=rng.uniform(-0.8, 0.8), gain=0.04)
place(fx, sec(EV['tagline']), whoosh(1.4, 0.3), gain=0.2)
place(fx, sec(EV['card']) - 1.0, reverse_cymbal(1.0), gain=0.35)

# ---- END CARD (bars 50–53) --------------------------------------------------------------------------------------------------
tc = sec(EV['card'])
place(fx, tc, impact(0.9, 4.0), gain=0.55)
place(drums, tc, kick(1.0), gain=1.0); kicks.append(tc)
place(chords, tc, supersaw(['A2', 'E3', 'A3', 'C#4', 'E4', 'A4'], 5.5, 3600) * np.linspace(1, 0, int(5.5 * SR))[:, None] ** 1.5, gain=0.5)
place(bass, tc, bass_note(hz('A1'), 4.5, 300, 1.2) * 1.2, gain=0.6)
for k, nm in enumerate(['A5', 'C#6', 'E6', 'A6']):
    place(keys_, tc + 0.05 + k * 0.12, bell(hz(nm), 4.0, 1.8), pan=-0.4 + k * 0.27, gain=0.1)

# ---- mix ----------------------------------------------------------------------------------------------------
# sidechain: duck bass / chords / pads / arps after each kick
duck = np.ones(N)
L = int(0.3 * SR); curve = 1 - 0.72 * np.exp(-np.arange(L) / SR / 0.11)
for t in kicks:
    i = int(t * SR)
    if i < N:
        j = min(N, i + L); duck[i:j] = np.minimum(duck[i:j], curve[:j - i])
dk = duck[:, None]
bass *= dk; chords *= dk ** 1.2; pads *= dk; arps *= dk ** 0.6

ir = make_ir(2.4)
arps = delay(arps)
wet = reverb(chords * 0.35 + arps * 0.5 + pads * 0.4 + keys_ * 0.8 + drums * 0.08 + fx * 0.3, ir, 0.45)
mix = drums * 1.0 + bass * 1.0 + chords * 1.0 + arps * 1.0 + pads * 0.9 + fx * 0.8 + keys_ * 1.0 + wet
mix = hp(mix, 30)
# section dynamics (bars → gain): restrained problem, full-power drop and finale
curve_pts = [(0, 0.55), (1.5, 0.58), (3, 0.66), (4.9, 0.9), (5, 1.0), (5.5, 0.8), (9, 0.78), (11.5, 0.76), (14.6, 0.72), (16.9, 0.84), (17, 0.95),
             (19, 0.55), (22, 0.7), (23.9, 0.82), (24, 1.0), (27.5, 1.0), (28.0, 0.97), (29.0, 0.87), (30.0, 0.8), (37.9, 0.8), (38, 0.86),
             (42.0, 0.86), (42.5, 0.81), (43.0, 0.77), (44.9, 0.82), (45, 0.86), (45.9, 0.9), (46, 1.0), (54, 1.0), (57, 1.0)]
tb = np.arange(N) / SR / BAR
gcurve = np.interp(tb, [c[0] for c in curve_pts], [c[1] for c in curve_pts])
gcurve = signal.lfilter([0.002], [1, -0.998], gcurve)  # smooth steps slightly
mix *= gcurve[:, None]
# glue compression + limiter (gentle: keeps the drop taller than the verses)
env = signal.lfilter([1 - 0.9993], [1, -0.9993], np.abs(mix).max(axis=1))
mix = mix / np.maximum(1, (env / 0.42) ** 0.3)[:, None]
fade = np.clip((sec(END_F) + 2.0 - np.arange(N) / SR) / 2.5, 0, 1)
mix *= fade[:, None]
mix = np.tanh(mix * 1.25) / np.tanh(1.25)
mix = mix / np.abs(mix).max() * 0.92
print(f'duration {DUR:.1f}s  rms {20 * np.log10(np.sqrt((mix ** 2).mean())):.1f} dBFS  kicks {len(kicks)}')
wavfile.write('public/audio/score.wav', SR, (mix * 32767).astype(np.int16))
