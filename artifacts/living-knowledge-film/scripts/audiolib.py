"""Sampled instruments, a hall reverb and mixing helpers for the film's score.

Real recordings instead of oscillators:
  - Salamander Grand Piano V3 (Yamaha C5, 16 velocity layers; Alexander Holm, CC-BY)
  - VSCO 2 Community Edition (Versilian Studios, CC0): violin, viola and cello sections (sustain, spiccato, pizzicato,
    tremolo), harp, timpani and orchestral percussion
Effects and dynamics come from Spotify's Pedalboard.

The libraries live outside the project, in $CLAUDE_AUDIO (default ~/Music/claude-audio):
  salamander/                 git clone https://github.com/sfzinstruments/SalamanderGrandPiano
  vsco2/                      sparse clone of https://github.com/sgossner/VSCO-2-CE (Strings, Percussion)

Every function returns stereo float32 arrays (n, 2) at SR. Pitches are MIDI numbers (60 = middle C, C4).
"""
import functools
import os
import re
from fractions import Fraction

import numpy as np
import soundfile as sf
from scipy import signal

SR = 48000
LIB = os.environ.get('CLAUDE_AUDIO', os.path.expanduser('~/Music/claude-audio'))
NOTE = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9,
        'A#': 10, 'Bb': 10, 'B': 11}
rng = np.random.default_rng(3)


def m(name):
    """'F#3' -> 54"""
    g = re.fullmatch(r'([A-G][#b]?)(-?\d)', name)
    return NOTE[g.group(1)] + 12 * (int(g.group(2)) + 1)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


# ---- loading and repitching ---------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def load(path, max_s=None):
    x, sr = sf.read(path, dtype='float32', always_2d=True)
    if max_s:
        x = x[:int(max_s * sr)]
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    x = x[:, :2]
    if sr != SR:
        g = np.gcd(SR, sr)
        x = signal.resample_poly(x, SR // g, sr // g, axis=0).astype(np.float32)
    return x


@functools.lru_cache(maxsize=None)
def repitched(path, semis, max_s=None):
    """the sample played faster or slower by `semis` semitones (resampled, so its length changes)"""
    x = load(path, max_s)
    if abs(semis) < 1e-4:
        return x
    r = Fraction(2 ** (semis / 12)).limit_denominator(600)  # playback rate
    return signal.resample_poly(x, r.denominator, r.numerator, axis=0).astype(np.float32)


def shape(x, dur=None, attack=0.0, release=0.25, start=0.0):
    """cut a sample to a note: optional fade-in, then held for `dur` seconds and released over `release`"""
    i0 = int(start * SR)
    x = x[i0:]
    if dur is not None:
        nd, nr = int(dur * SR), int(release * SR)
        n = nd + nr
        if len(x) < n:
            x = np.concatenate([x, np.zeros((n - len(x), 2), np.float32)])
        x = x[:n].copy()
        if nr > 0:
            x[nd:nd + nr] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, nr)))[:, None]
    else:
        x = x.copy()
    na = int(attack * SR)
    if na > 1:
        x[:na] *= (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, na)))[:, None]
    else:  # de-click the very start
        k = min(len(x), 48)
        x[:k] *= np.linspace(0, 1, k)[:, None]
    return x


# ---- the piano --------------------------------------------------------------------------------------------------
SAL = os.path.join(LIB, 'salamander', 'Samples')
SAL_ROOTS = [21 + 3 * k for k in range(30)]  # A0, C1, D#1, F#1, … C8
SAL_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
SAL_VEL = [26, 34, 36, 43, 46, 50, 56, 64, 72, 80, 88, 96, 104, 112, 120, 127]  # top of each of the 16 layers


def piano(note, vel=70, dur=1.5, release=0.6, max_s=12):
    """one key of the Salamander grand: nearest sampled key, repitched; the velocity picks the layer"""
    root = min(SAL_ROOTS, key=lambda r: abs(r - note))
    layer = next(i for i, top in enumerate(SAL_VEL) if vel <= top) + 1
    name = f'{SAL_NAMES[root % 12]}{root // 12 - 1}'
    x = repitched(os.path.join(SAL, f'{name}v{layer}.flac'), float(note - root), max_s)
    gain = 1 - 0.27 * (1 - (vel / 127) ** 2)  # the layers carry most of the dynamics
    return shape(x, dur, release=release) * gain


# ---- the string sections, harp and timpani (VSCO 2) ----------------------------------------------------------------
VS = os.path.join(LIB, 'vsco2')
STRINGS = {
    'violins': 'Strings/Violin Section', 'violas': 'Strings/Viola Section', 'cellos': 'Strings/Cello Section',
}
ART = {  # articulation folders per section
    'violins': {'sus': 'susVib', 'spic': 'Spic', 'pizz': 'Pizz', 'trem': 'Trem'},
    'violas': {'sus': 'susvib', 'spic': 'spic', 'pizz': 'pizz', 'trem': 'trem'},
    'cellos': {'sus': 'susvib', 'spic': 'spic', 'pizz': 'pizzT', 'trem': 'trem'},
}


@functools.lru_cache(maxsize=None)
def bank(folder, octave_shift=12):
    """parse a folder of samples named like '…_G2_v1_rr2.wav' into {midi: {layer: [paths]}}.
    VSCO's string sections name octaves one lower than scientific pitch (their 'C2' sounds as C3): octave_shift=12."""
    out = {}
    d = os.path.join(VS, folder)
    for f in sorted(os.listdir(d)):
        if not f.endswith('.wav'):
            continue
        g = re.search(r'_([A-G]#?)(\d)_(?:v(\d)|(pp|p|mp|mf|f|ff))', f)
        if not g:
            continue
        note = NOTE[g.group(1)] + 12 * (int(g.group(2)) + 1) + octave_shift
        layer = int(g.group(3)) if g.group(3) else {'pp': 1, 'p': 1, 'mp': 1, 'mf': 2, 'f': 2, 'ff': 3}[g.group(4)]
        out.setdefault(note, {}).setdefault(layer, []).append(os.path.join(d, f))
    return out


def _pick(b, note, layer, rr):
    root = min(b, key=lambda r: (abs(r - note), r < note))  # nearest sample; on a tie, shift down rather than up
    layers = b[root]
    lay = min(layers, key=lambda l: abs(l - layer))
    paths = layers[lay]
    return root, paths[rr % len(paths)]


def strings(section, note, dur, layer=1, art='sus', attack=0.12, release=0.5, rr=0, start=0.0):
    """a note from a string section: art = sus | spic | pizz | trem; layer 1 soft … 2 loud"""
    b = bank(f'{STRINGS[section]}/{ART[section][art]}')
    root, path = _pick(b, note, layer, rr)
    x = repitched(path, float(note - root), 16)
    return shape(x, dur, attack=attack, release=release, start=start)


def harp(note, dur=3.0, loud=False, release=1.2):
    b = bank('Strings/Harp', octave_shift=0)
    root, path = _pick(b, note, 2 if loud else 1, 0)
    return shape(repitched(path, float(note - root) + 0.12, 10), dur, release=release)  # the harp samples sit ~12 cents flat


TIMP = {'B1': 'Timpani2', 'C#2': 'Timpani3', 'F#2': 'Timpani5'}  # measured pitches of the drums


def timpani(note, vel=3, rr=1, roll=False, dur=None):
    """a timpani hit (vel 1–4) or roll, tuned from the nearest drum; uses the nearest velocity layer that exists"""
    best = min(TIMP, key=lambda n: abs(m(n) - note))
    drum = TIMP[best]
    folder = os.path.join(VS, 'Percussion/Timpani', 'Rolls' if roll else '')
    kind = 'Roll' if roll else 'Hit'
    have = sorted(f for f in os.listdir(folder) if f.startswith(f'{drum}_{kind}_v'))
    want = vel + (1 if roll else 0)
    pick = min(have, key=lambda f: (abs(int(re.search(r'_v(\d)', f).group(1)) - want), f'rr{rr}' not in f))
    x = repitched(os.path.join(folder, pick), float(note - m(best)), 12 if not roll else 30)
    return shape(x, dur, release=0.8) if dur else shape(x)


def perc(name, dur=None, release=0.3):
    """an orchestral percussion one-shot by file stem, e.g. 'BDrumNewhit_v5_rr1_Sum', 'susCymb1-cresc-Long_v1'"""
    x = load(os.path.join(VS, 'Percussion', name + '.wav'))
    return shape(x, dur, release=release) if dur else shape(x)


# ---- small synthesized parts: sub bass, kick, clap, UI ticks ---------------------------------------------------------
def sub(note, dur, level=1.0):
    n = int((dur + 0.08) * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * hz(note) * t) + 0.08 * np.sin(4 * np.pi * hz(note) * t)
    env = np.minimum(1, t / 0.012) * np.clip((dur + 0.08 - t) / 0.08, 0, 1)
    return np.repeat((x * env * level).astype(np.float32)[:, None], 2, axis=1)


def kick(level=1.0, tone=52):
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    f = tone + 70 * np.exp(-t * 32) + 50 * np.exp(-t * 300)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7.0)
    click = signal.sosfilt(signal.butter(2, [2000, 6000], 'band', fs=SR, output='sos'), rng.standard_normal(n)) * np.exp(-t * 400) * 0.09
    click *= np.minimum(1, t / 0.0006)  # a rounded attack: present, never a tick
    x = np.tanh((body + click) * 1.3) * level
    return np.repeat(x.astype(np.float32)[:, None], 2, axis=1)


def clap(level=1.0):
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for k, d in enumerate([0, 0.008, 0.017, 0.027]):
        i = int(d * SR)
        x[i:] += rng.standard_normal(n - i) * np.exp(-t[:n - i] * (150 if k < 3 else 20)) * (0.6 if k < 3 else 1.0)
    x = signal.sosfilt(signal.butter(2, [1000, 6500], 'band', fs=SR, output='sos'), x)
    return np.stack([x, np.roll(x, 90)], axis=1).astype(np.float32) * level


def tick(level=1.0):
    """a soft interface tick: band-limited, with a 1 ms rise so it never clicks"""
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    x = signal.sosfilt(signal.butter(2, [1800, 6000], 'band', fs=SR, output='sos'), rng.standard_normal(n)) * np.exp(-t * 260)
    x *= np.minimum(1, t / 0.001) * level
    return np.repeat(x.astype(np.float32)[:, None], 2, axis=1)


# ---- a hall: convolution with a generated impulse response whose highs die faster than its lows ---------------------
@functools.lru_cache(maxsize=None)
def hall_ir(rt_low=2.8, rt_high=1.1, predelay=0.022, seconds=4.0, seed=5):
    g = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    edges = [0, 250, 700, 1800, 4500, 9000, 20000]
    ir = np.zeros((n, 2))
    for k in range(len(edges) - 1):
        lo, hi = max(edges[k], 20), edges[k + 1]
        rt = rt_low * (rt_high / rt_low) ** (k / (len(edges) - 2))
        for c in range(2):
            noise = g.standard_normal(n)
            sos = signal.butter(4, [lo, min(hi, SR / 2 - 100)], 'band', fs=SR, output='sos')
            ir[:, c] += signal.sosfilt(sos, noise) * np.exp(-6.9 * t / rt)
    ir *= np.minimum(1, t / 0.012)[:, None]  # soften the onset of the tail
    for k in range(12):  # a few early reflections
        d = int((0.006 + 0.004 * k + g.random() * 0.006) * SR)
        ir[d, k % 2] += 0.6 * (0.85 ** k) * g.choice([-1, 1])
    ir = np.concatenate([np.zeros((int(predelay * SR), 2)), ir])
    return (ir / np.sqrt((ir ** 2).sum() / 2)).astype(np.float32)


def reverb(x, wet=0.3, **kw):
    ir = hall_ir(**kw)
    y = np.stack([signal.fftconvolve(x[:, c], ir[:, c])[:len(x)] for c in range(2)], axis=1)
    return (y * wet).astype(np.float32)


# ---- a timeline to place sounds on -----------------------------------------------------------------------------------
class Bus:
    def __init__(self, seconds):
        self.x = np.zeros((int(seconds * SR), 2), np.float32)

    def add(self, t, sig, gain=1.0, pan=0.0):
        """place a stereo (n, 2) or mono (n,) sound at time t (seconds); pan −1 … 1 (equal power)"""
        if sig.ndim == 1:
            sig = np.repeat(sig[:, None], 2, axis=1)
        if pan:
            a = (pan + 1) * np.pi / 4
            sig = sig * np.array([np.cos(a), np.sin(a)], np.float32) * np.sqrt(2)
        i = int(round(t * SR))
        j0 = max(0, -i)
        j1 = min(len(sig), len(self.x) - i)
        if j1 > j0:
            self.x[i + j0:i + j1] += sig[j0:j1] * gain


def process(x, board):
    """run a Pedalboard chain over a (n, 2) array"""
    return board(x.T.copy(), SR).T.astype(np.float32)
