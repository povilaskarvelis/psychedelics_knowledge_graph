"""Score v14 — the film's music played by sampled instruments: a Yamaha grand (Salamander), string sections, harp,
timpani and orchestral percussion (VSCO 2), with a light electronic pulse (sub bass, kick) and Pedalboard dynamics.
See scripts/audiolib.py for the instruments and where the sample libraries live.

120 bpm, synced to the picture (15 frames = 1 beat, 60 frames = 1 bar). F# minor, opening into A major.
Bars: 1665, one page 0–1.5 · the trickle 1.5–3 · the explosion 3–5 (hit on 2026) · the paper, buried in prose, links,
synthesis 5–11.5 · out of date, search, from scratch 11.5–17 · thesis 17–19 · the blade reads the field 19–24 · the graph
forms (the anthem) 24–29 · psychedelic science 29–45 (the field at a glance 37.5–42.5, agents 42.5–45) · lift 45 · all of
science 46–50 · end chord 50–53.

    python3 scripts/score_v14.py      # public/audio/score.wav (48 kHz, 24-bit)
"""
import numpy as np
import soundfile as sf
from pedalboard import Pedalboard, Compressor, HighpassFilter, LowpassFilter, HighShelfFilter, LowShelfFilter, PeakFilter

import audiolib as A
from audiolib import m

SR = A.SR
FPS = 30
END_F = 3180
DUR = END_F / FPS + 5.0
rng = np.random.default_rng(14)
sec = lambda f: f / FPS
tb = lambda bar, beat=0.0: bar * 2.0 + beat * 0.5     # 120 bpm: a bar is 2 s, a beat 0.5 s

# picture landmarks (global frames) — mirror src/Film.jsx (acts at 0 · 1020 · 1140 · 1740 · 2760) and the scene constants
EV = dict(
    page=2, era=90, y0=92, ym=172, y1=300, pick=316, highlights=[382, 385, 388, 391, 394, 397], links=[462, 466, 470, 474],
    arcs=[496, 502, 508, 514, 520, 526], gather0=558, gather1=606, review=624, dated=656, search=750, typing=(786, 800), results=798,
    scan1=810, scratch=880, scan2=914, cut=1020, slams=[1065, 1080, 1095], act2=1140,
    statement=1146, blade=1208, sweep=1230, grid=1380, drop=1440, bridges=1496, living=1560, arrive=(1528, 1736), title=1562,
    act3=1740, land=1800, clicks=[1936, 1972, 2040, 2148, 2196], list_=2076, analyze=2250, trends=(2264, 2328), bars=2300,
    cells=2326, meta=2430, gaps=[2462, 2466, 2470, 2474, 2478, 2482], agents=2550, ask=(2570, 2588), calls=[2592, 2612],
    results2=[2604, 2628], answer=2640, graph=2700, gold=2714, act4=2760, arcs4=2818, tagline=2880, card=3000,
)

# ---- harmony: voicings per chord (scientific pitch) ---------------------------------------------------------------
V = {
    'F#m': dict(bass='F#1', vc=['F#2', 'C#3'], va=['A3', 'C#4'], vn=['F#4', 'A4'], arp=['F#3', 'C#4', 'A4', 'C#4'], top=['C#5', 'A4', 'F#4']),
    'D':   dict(bass='D2', vc=['D2', 'A2'], va=['F#3', 'A3'], vn=['D4', 'F#4'], arp=['D3', 'A3', 'F#4', 'A3'], top=['F#5', 'D5', 'A4']),
    'A':   dict(bass='A1', vc=['A2', 'E3'], va=['C#4', 'E4'], vn=['A4', 'C#5'], arp=['A2', 'E3', 'C#4', 'E3'], top=['E5', 'C#5', 'A4']),
    'E':   dict(bass='E2', vc=['E2', 'B2'], va=['G#3', 'B3'], vn=['E4', 'G#4'], arp=['E3', 'B3', 'G#4', 'B3'], top=['B4', 'G#4', 'E4']),
    'Bm':  dict(bass='B1', vc=['B2', 'F#3'], va=['D4', 'F#4'], vn=['B4', 'D5'], arp=['B2', 'F#3', 'D4', 'F#3'], top=['D5', 'B4', 'F#4']),
}
PROG = {}
for b, c in enumerate(['F#m', 'F#m', 'F#m', 'D', 'E',                     # 0–4: the page, the trickle, the explosion
                       'F#m', 'D', 'A', 'E', 'F#m', 'D', 'A',            # 5–11: the paper, prose, links, synthesis
                       'D', 'A', 'F#m', 'F#m', 'E',                       # 12–16: out of date, search, from scratch
                       'F#m', 'E',                                        # 17–18: thesis
                       'D', 'E', 'F#m', 'D', 'E',                         # 19–23: the blade, the build
                       'A', 'E', 'F#m', 'D', 'A',                         # 24–28: the anthem; the last bar thins into Act III
                       'D', 'D', 'A', 'E', 'F#m', 'D', 'A', 'E', 'F#m', 'D', 'A', 'E', 'F#m', 'D', 'A', 'E',  # 29–44: Act III
                       'E',                                               # 45: lift
                       'F#m', 'D', 'A', 'E', 'A', 'A', 'A']):              # 46–52: all of science, end chord
    PROG[b] = c

# ---- buses ------------------------------------------------------------------------------------------------------------
B = {k: A.Bus(DUR) for k in ['piano', 'long', 'short', 'harp', 'orch', 'drums', 'bass', 'fx']}


def pad(bar, chord, bars=1, layer=1, gain=1.0, sections=('vc', 'va', 'vn'), attack=0.45, release=0.9, art='sus'):
    """sustained string chord over `bars` bars, overlapping into the next for a legato change"""
    v = V[chord]
    dur = bars * 2.0
    for key, sect, g in (('vc', 'cellos', 1.0), ('va', 'violas', 0.85), ('vn', 'violins', 0.75)):
        if key not in sections:
            continue
        for k, n in enumerate(v[key]):
            B['long'].add(tb(bar) - 0.08, A.strings(sect, m(n), dur + 0.1, layer=layer, art=art, attack=attack, release=release),
                          gain=0.22 * g * gain, pan=[-0.35, 0.0, 0.35][['vc', 'va', 'vn'].index(key)] + (k - 0.5) * 0.2)


def ostinato(bar, chord, sections=('va', 'vc'), sub=2, layer=1, gain=1.0, accent=True, art='spic'):
    """short string notes on chord tones: sub = notes per beat (2 = eighths, 4 = sixteenths)"""
    v = V[chord]
    for key in sections:
        sect = {'va': 'violas', 'vc': 'cellos', 'vn': 'violins'}[key]
        notes = v[key] + [v[key][0]]
        for s in range(4 * sub):
            n = notes[s % len(notes)] if key != 'vc' else v['vc'][0]
            acc = accent and s % sub == 0
            x = A.strings(sect, m(n), 0.22 if art == 'spic' else 0.3, layer=2 if acc else layer, art=art, attack=0.0, release=0.12, rr=s)
            B['short'].add(tb(bar, s / sub) + rng.normal(0, 0.004), x, gain=(0.30 if acc else 0.22) * gain,
                           pan={'va': 0.25, 'vc': -0.3, 'vn': 0.45}[key])


def piano_arp(bar, chord, vel=48, gain=1.0, pattern=(0, 1, 2, 1, 3, 1, 2, 1), octave=0):
    v = V[chord]['arp']
    for s, idx in enumerate(pattern):
        n = m(v[idx % len(v)]) + (12 if idx >= len(v) else 0) + 12 * octave
        B['piano'].add(tb(bar, s * 0.5), A.piano(n, vel + (6 if s == 0 else 0) + int(rng.integers(-3, 4)), 1.4, release=0.9), gain=0.5 * gain,
                       pan=-0.25 + 0.5 * (idx % len(v)) / 3)


def piano_chord(t, chord, vel=55, dur=1.8, gain=1.0, top=True):
    v = V[chord]
    notes = v['arp'][:3] + ([v['top'][0]] if top else [])
    for k, n in enumerate(notes):
        B['piano'].add(t + k * 0.012, A.piano(m(n), vel - 4 * (k == 0), dur, release=1.0), gain=0.45 * gain, pan=-0.3 + 0.2 * k)


def piano_line(bar, notes, vel=58, gain=1.0):
    """notes: [(beat, name, beats)]"""
    for beat, n, beats in notes:
        B['piano'].add(tb(bar, beat), A.piano(m(n), vel + int(rng.integers(-2, 3)), beats * 0.5, release=0.8), gain=0.55 * gain, pan=0.1)


def melody(bar, notes, layer=2, gain=1.0, section='violins'):
    """a sustained string line: [(beat, name, beats)]"""
    for beat, n, beats in notes:
        B['long'].add(tb(bar, beat) - 0.05, A.strings(section, m(n), beats * 0.5 + 0.05, layer=layer, attack=0.12, release=0.5),
                      gain=0.34 * gain, pan=0.2)


def bassline(bar, chord, beats=(0, 2), dur=0.9, level=1.0):
    for q in beats:
        B['bass'].add(tb(bar, q), A.sub(m(V[chord]['bass']), dur, 0.55 * level))


def groove(bar, kick=(0, 2), snare=(), shaker=True, level=1.0, bassdrum=False):
    for q in kick:
        B['drums'].add(tb(bar, q), A.kick(0.9 * level), gain=0.5)
    if bassdrum:
        B['orch'].add(tb(bar), A.perc(f'BDrumNewhit_v{int(rng.integers(4, 6))}_rr{int(rng.integers(1, 3))}_Sum'), gain=0.32 * level)
    for k, q in enumerate(snare):
        B['drums'].add(tb(bar, q), A.perc(f'Snare2-HitSN_v{[5, 7][k % 2]}_rr{1 + k % 2}_Sum'), gain=0.28 * level)
        B['drums'].add(tb(bar, q), A.clap(0.6 * level), gain=0.10)
    if shaker:
        for e in range(8):
            if e % 2:
                B['drums'].add(tb(bar, e * 0.5) + rng.normal(0, 0.004), A.perc(f'Tamb1-Shake_v1_rr{1 + (e // 2) % 2}_Sum', dur=0.22, release=0.08),
                               gain=0.09 * level, pan=0.3)


def impact(t, size=1.0, timp='F#2', crash=True, gong=False, sub_note='F#1'):
    """a hit: concert bass drum, timpani, cymbal, a sub drop"""
    B['orch'].add(t, A.perc('BDrumNewhit_v7_rr1_Sum' if size > 0.7 else 'BDrumNewhit_v5_rr2_Sum'), gain=0.55 * size)
    B['orch'].add(t, A.timpani(m(timp), vel=4 if size > 0.7 else 3), gain=0.5 * size)
    if crash:
        B['fx'].add(t, A.perc('cymbal-crash1_ff_rr1' if size > 0.7 else 'cymbal-crash1_mf_rr2'), gain=0.22 * size)
    if gong:
        B['fx'].add(t, A.perc('gongHit_mf', dur=6.0, release=2.0), gain=0.25 * size)
    n = int(2.2 * SR)
    tt = np.arange(n) / SR
    drop = np.sin(2 * np.pi * np.cumsum(A.hz(m(sub_note)) * (1 + 1.5 * np.exp(-tt * 9))) / SR) * np.exp(-tt * 1.6)
    B['bass'].add(t, np.repeat(drop.astype(np.float32)[:, None], 2, 1), gain=0.45 * size)


def swell(t_end, length='Median', gain=1.0):
    """a suspended-cymbal crescendo that peaks at t_end"""
    x = A.perc(f'susCymb1-cresc-{length}_v1')
    env = np.abs(x).mean(1)
    k = int(np.argmax(signal_smooth(env)))  # the loudest point of the crescendo
    B['fx'].add(t_end - k / SR, x[:k + int(0.06 * SR)], gain=0.3 * gain)


def signal_smooth(e, w=2400):
    return np.convolve(e, np.ones(w) / w, mode='same')


# ==== ACT I · the page (bars 0–1.5) ===================================================================================
pad(0, 'F#m', bars=3, layer=1, gain=0.55, sections=('vc', 'va'), attack=1.6, release=1.6)
piano_line(0, [(0, 'C#5', 1.5), (1.5, 'B4', 0.5), (2, 'A4', 2)], vel=46)
piano_line(1, [(0, 'F#4', 1), (1, 'A4', 1), (2, 'C#5', 1.5), (3.5, 'E5', 0.5)], vel=44)
piano_line(2, [(0, 'D5', 2), (2, 'C#5', 2)], vel=44)
B['piano'].add(tb(0), A.piano(m('F#2'), 40, 5.5, release=2.0), gain=0.4)

# ---- the trickle: one harp pluck per early paper (bars 1.5–3) ----------------------------------------------------------
Y0, YM, Y1 = EV['y0'], EV['ym'], EV['y1']
def frame_of_year(y):
    return Y0 + (YM - Y0) * max(0.0, (y - 1665) / 235) ** (1 / 1.6) if y <= 1900 else YM + (Y1 - YM) * ((y - 1900) / 126) ** (1 / 1.15)
colN = [max(1, round(1.4 * np.exp(0.19 * c))) for c in range(37)]
land = np.sort(np.array([frame_of_year(1665 + 10 * c + 10 * (k + 0.5) / n) for c, n in enumerate(colN) for k in range(n)]))
PENTA = ['F#5', 'A5', 'B5', 'C#6', 'E6', 'F#6']
early = [x for x in land if x < 205]
for k, x in enumerate(early):
    B['harp'].add(sec(x), A.harp(m(PENTA[(k * 3) % len(PENTA)]), 1.6), gain=0.16, pan=-0.6 + 1.2 * (k / max(1, len(early))))
# ---- the explosion (bars 3–5): the papers pour in; strings accelerate; everything lands on 2026 ---------------------
dense = [x for x in land if 205 <= x < Y1]
for k, x in enumerate(dense[::4]):
    sect = ['violins', 'violas'][k % 2]
    B['short'].add(sec(x), A.strings(sect, m(['C#5', 'A4', 'F#4', 'E5'][k % 4]) - (12 if sect == 'violas' else 0), 0.2, layer=1, art='pizz', attack=0, release=0.1, rr=k),
                   gain=0.10 + 0.10 * k / max(1, len(dense) // 4), pan=rng.uniform(-0.7, 0.7))
pad(3, 'D', bars=1, layer=1, gain=0.7, attack=0.6)
pad(4, 'E', bars=1, layer=2, gain=0.8, attack=0.4)
ostinato(3, 'D', sections=('va',), sub=2, gain=0.6)
ostinato(4, 'E', sections=('va', 'vc'), sub=4, gain=0.8)
B['orch'].add(tb(3.5), A.timpani(m('C#2'), vel=3, roll=True, dur=sec(Y1) - tb(3.5)), gain=0.35)
swell(sec(Y1), 'Median', 1.0)
for k, n in enumerate(['E4', 'F#4', 'G#4', 'A4', 'B4', 'C#5', 'D5', 'E5']):   # the violins climb into the hit
    B['long'].add(tb(4, k * 0.5), A.strings('violins', m(n), 0.55, layer=2, attack=0.05, release=0.2), gain=0.16 + 0.02 * k)
impact(sec(Y1), 1.0, timp='F#2', crash=True)
for n in ['F#1', 'F#2', 'C#3']:
    B['piano'].add(sec(Y1), A.piano(m(n), 96, 2.5, release=1.5), gain=0.45)
pad(5, 'F#m', bars=1, layer=2, gain=0.8, attack=0.02)

# ==== ACT I · the paper, buried in prose, links, synthesis (bars 5–11.5) ===============================================
B['fx'].add(sec(EV['pick']) - 0.4, A.perc('bassdrum_rub2_v1'), gain=0.15)   # one paper lifts off the pile
for b in range(5, 12):
    c = PROG[b]
    pad(b, c, layer=1, gain=0.55, sections=('vc', 'va'), attack=0.5)
    piano_arp(b, c, vel=44 + (b > 7) * 4, gain=0.8)
    ostinato(b, c, sections=('vc',) if b < 7 else ('vc', 'va'), sub=2, gain=0.55 + 0.05 * (b - 5))
    bassline(b, c, beats=(0, 2), dur=0.9, level=0.35)
    groove(b, kick=(0, 2) if b >= 6 else (0,), shaker=b >= 7, level=0.6 + 0.04 * (b - 5))
for k, f in enumerate(EV['highlights']):          # findings, methods, context marked on the page
    B['harp'].add(sec(f), A.harp(m(['A5', 'C#6', 'E6', 'A5', 'C#6', 'E6'][k]), 2.0, loud=k < 3), gain=0.28 if k < 3 else 0.18, pan=-0.3 + 0.12 * k)
for k, f in enumerate(EV['links']):               # links reach between the papers
    B['short'].add(sec(f), A.strings('violins', m(['E5', 'C#5', 'A5', 'F#5'][k]), 0.4, art='pizz', attack=0, release=0.3, rr=k), gain=0.22, pan=[-0.6, 0.6, -0.4, 0.4][k])
for k, f in enumerate(EV['arcs']):                # … and fade
    B['harp'].add(sec(f), A.harp(m(['C#6', 'E6', 'F#6', 'A6', 'E6', 'C#6'][k]), 1.4), gain=0.13 * (1 - k / 8), pan=[-0.5, 0.5, -0.4, 0.4, -0.2, 0.2][k])
for k in range(22):                                # the papers gather into a pile
    tt = EV['gather0'] + (k / 22) ** 0.8 * (EV['gather1'] - EV['gather0'])
    B['drums'].add(sec(tt), A.perc(f'Snare2-taps_v{1 + k % 3}_rr{1 + k % 2}_Sum', dur=0.25, release=0.1), gain=0.10, pan=0.35)
impact(sec(EV['review']), 0.55, timp='B1', crash=False)   # … bound into one review
piano_chord(sec(EV['review']), 'Bm', vel=62, dur=2.5)

# ==== ACT I · out of date, search, from scratch (bars 11.5–17) =========================================================
for b in range(12, 17):
    c = PROG[b]
    pad(b, c, layer=1, gain=0.5, sections=('vc', 'va'), attack=0.6)
    if b != 14:
        piano_arp(b, c, vel=42, gain=0.7)
    ostinato(b, c, sections=('vc',), sub=2, gain=0.45)
    bassline(b, c, beats=(0, 2), dur=0.9, level=0.3)
    groove(b, kick=(0, 2) if b not in (14,) else (), shaker=b < 15, level=0.55)
for k, n in enumerate(['A4', 'G#4', 'F#4', 'E4']):   # the review greys: a falling line in the violas
    B['long'].add(sec(EV['dated']) + 0.3 + k * 0.6, A.strings('violas', m(n), 0.7, layer=1, attack=0.15, release=0.4), gain=0.2)
for k in range(40):                                # new studies land on the timeline, year by year
    tt = EV['dated'] + 16 + (k / 40) ** 0.85 * 72
    B['short'].add(sec(tt), A.strings('violas', m(['F#4', 'A4', 'C#5', 'E5'][k % 4]), 0.15, art='pizz', attack=0, release=0.1, rr=k), gain=0.07, pan=-0.1 + 0.6 * k / 40)
swell(sec(EV['search']), 'Short', 0.8)            # the search
t0, t1 = EV['typing']
for k in range(23):
    B['fx'].add(sec(t0 + k * (t1 - t0) / 23) + rng.random() * 0.012, A.tick(0.7), gain=0.12, pan=0.2)
B['harp'].add(sec(EV['results']), A.harp(m('C#6'), 1.5), gain=0.2)
def scan(start, end):
    k = 0
    while start + k * 3.2 < end:   # screening, paper by paper: a soft, even patter
        B['fx'].add(sec(start + k * 3.2), A.tick(0.5), gain=0.03, pan=float(rng.uniform(-0.5, 0.5)))
        k += 1
scan(EV['scan1'], EV['scratch'])
B['orch'].add(sec(EV['scratch']), A.perc('BDrumNewhit_v4_rr1_Sum'), gain=0.35)  # … and the next reader starts over
scan(EV['scan2'], EV['cut'] - 8)
B['drums'].add(tb(16), A.perc('Snare2-rollNS_v3_rr1_Sum', dur=2.0, release=0.05), gain=0.22)   # a roll into the turn
swell(sec(EV['cut']), 'Median', 0.8)

# ==== THESIS (bars 17–19): three hits ====================================================================================
impact(sec(EV['cut']), 0.75, timp='F#2', crash=False, gong=True)
for k, f in enumerate(EV['slams']):
    c = ['F#m', 'D', 'E'][k]
    impact(sec(f), 0.85, timp=['F#2', 'C#2', 'B1'][k], crash=k == 2, sub_note=V[c]['bass'])
    for key, sect in (('vc', 'cellos'), ('va', 'violas'), ('vn', 'violins')):
        for n in V[c][key]:
            B['short'].add(sec(f), A.strings(sect, m(n), 0.35, layer=2, art='spic', attack=0, release=0.25, rr=k), gain=0.32)
    for n in V[c]['arp'][:2]:
        B['piano'].add(sec(f), A.piano(m(n) - 12, 100, 1.2, release=1.0), gain=0.4)
swell(sec(EV['act2']), 'Short', 0.6)

# ==== ACT II · the blade reads the field (bars 19–24) ======================================================================
impact(sec(EV['statement']), 0.45, timp='F#2', crash=False)
for b in range(19, 24):
    c = PROG[b]
    i = b - 19
    pad(b, c, layer=1 + (b >= 22), gain=0.55 + 0.1 * i, attack=0.5)
    ostinato(b, c, sections=('va', 'vc') if b < 22 else ('va', 'vc', 'vn'), sub=2 if b < 21 else 4, gain=0.45 + 0.12 * i)
    piano_arp(b, c, vel=46 + 3 * i, gain=0.7)
    bassline(b, c, beats=(0, 2), dur=0.9, level=0.5 + 0.08 * i)
    if b >= 21:
        groove(b, kick=(0, 1, 2, 3) if b == 23 else (0, 2), shaker=True, level=0.6 + 0.1 * (b - 21))
B['fx'].add(sec(EV['blade']), A.perc('susCymb1-bow-2', dur=4.0, release=1.5), gain=0.22)   # the blade of light
for k in range(48):                                # every paper opening as the blade passes: a rising shimmer, right to left
    u = k / 48
    tt = sec(EV['sweep']) + u * (sec(EV['grid']) - sec(EV['sweep']))
    B['harp'].add(tt, A.harp(m(['A5', 'B5', 'C#6', 'E6', 'F#6', 'A6', 'B6', 'C#7'][min(7, int(u * 8))]), 1.2), gain=0.09, pan=0.7 - 1.4 * u)
B['orch'].add(tb(22), A.timpani(m('C#2'), vel=4, roll=True, dur=4.0), gain=0.32)
B['drums'].add(tb(23), A.perc('Snare2-rollNS_v5_rr1_Sum', dur=2.0, release=0.02), gain=0.26)
swell(sec(EV['drop']), 'Long', 1.0)

# ==== ACT II · the graph forms — the anthem (bars 24–29) =====================================================================
impact(sec(EV['drop']), 1.0, timp='B1', crash=True, sub_note='A1')
ANTHEM = {24: [(0, 'C#5', 2), (2, 'E5', 2)], 25: [(0, 'B4', 2), (2, 'G#4', 1), (3, 'B4', 1)],
          26: [(0, 'A4', 3), (3, 'C#5', 1)], 27: [(0, 'D5', 2), (2, 'F#5', 1), (3, 'E5', 1)]}
for b in range(24, 29):
    c = PROG[b]
    last = b == 28
    pad(b, c, layer=2 if not last else 1, gain=0.9 if not last else 0.6, attack=0.25)
    if b in ANTHEM:
        melody(b, ANTHEM[b], layer=2, gain=1.0)
        melody(b, [(q, n[:-1] + str(int(n[-1]) - 1), d) for q, n, d in ANTHEM[b]], layer=1, gain=0.5, section='violas')
    ostinato(b, c, sections=('va', 'vc') if not last else ('va',), sub=4 if not last else 2, gain=0.75 if not last else 0.5)
    piano_arp(b, c, vel=56 if not last else 48, gain=0.75)
    bassline(b, c, beats=(0, 1.5, 2, 3.5) if not last else (0, 2), dur=0.45 if not last else 0.9, level=0.85)
    groove(b, kick=(0, 2), snare=(1, 3) if not last else (), shaker=True, level=0.85 if not last else 0.6, bassdrum=not last)
B['harp'].add(sec(EV['bridges']), A.harp(m('E6'), 2.5, loud=True), gain=0.25)
for k, n in enumerate(['A5', 'C#6', 'E6', 'A6']):     # bridges arch between clusters
    B['harp'].add(sec(EV['bridges']) + 0.08 * k, A.harp(m(n), 2.0), gain=0.14)
B['fx'].add(sec(EV['title']), A.perc('cymbal-crash1_mp_rr1'), gain=0.18)     # "A living knowledge graph."
a0, a1 = EV['arrive']
for k in range(14):                                # new papers keep arriving
    B['harp'].add(sec(a0 + (k + 0.5) / 14 * (a1 - a0)), A.harp(m(['A6', 'F#6', 'E6', 'C#6', 'B5'][k % 5]), 1.0), gain=0.07, pan=-0.6 + 0.09 * k)

# ==== ACT III · psychedelic science (bars 29–45) ============================================================================
pad(29, 'D', bars=1, layer=1, gain=0.7, attack=0.3)                      # the chord that carries the cut
for k, n in enumerate(['D5', 'F#5', 'A5', 'D6', 'F#6']):
    B['harp'].add(sec(EV['act3']) + 0.12 * k, A.harp(m(n), 2.5), gain=0.14)
impact(sec(EV['land']), 0.35, timp='C#2', crash=False, sub_note='D2')      # the diagram lands on the bar
for b in range(30, 45):
    c = PROG[b]
    busy = 37 <= b < 42                    # the whole field at a glance
    calm = b >= 42                         # the agent's session
    pad(b, c, layer=1, gain=0.42 + 0.06 * busy, sections=('vc', 'va'), attack=0.4)
    piano_arp(b, c, vel=46 + 4 * busy, gain=0.7 - 0.15 * calm)
    ostinato(b, c, sections=('vn', 'va') if not calm else ('va',), sub=2, gain=0.42 + 0.1 * busy, art='pizz', accent=True)
    if busy:
        ostinato(b, c, sections=('vc',), sub=4, gain=0.42)
    bassline(b, c, beats=(0, 2) if not busy else (0, 1.5, 2, 3.5), dur=0.9 if not busy else 0.45, level=0.55)
    if b >= 31 and not calm:
        groove(b, kick=(0, 2), snare=(1, 3) if b >= 33 else (), shaker=True, level=0.55 + 0.1 * busy)
    elif calm:
        groove(b, kick=(0,), snare=(), shaker=True, level=0.45)
for k, f in enumerate(EV['clicks']):               # each click goes one level deeper
    B['fx'].add(sec(f), A.tick(1.0), gain=0.2)
    B['harp'].add(sec(f), A.harp(m(['A5', 'C#6', 'E6', 'A6', 'C#7'][k]), 1.4), gain=0.16)
for k in range(6):
    B['fx'].add(sec(EV['list_'] + 2 + k * 3), A.tick(0.6), gain=0.08, pan=0.4)
t0, t1 = EV['trends']                              # the trends draw on
for k in range(16):
    B['harp'].add(sec(t0 + (k / 15) * (t1 - t0)), A.harp(m(['D5', 'E5', 'F#5', 'A5', 'B5', 'D6', 'E6', 'F#6'][k // 2]), 1.0), gain=0.07, pan=-0.7 + 1.4 * k / 15)
for k in range(6):
    B['short'].add(sec(EV['bars'] + k * 5), A.strings('violins', m(['A4', 'C#5', 'E5', 'F#5', 'A5', 'B5'][k]), 0.3, art='pizz', attack=0, release=0.2, rr=k), gain=0.12)
B['fx'].add(sec(EV['meta']), A.tick(1.0), gain=0.2)
for k, f in enumerate(EV['gaps']):
    B['harp'].add(sec(f), A.harp(m(['E6', 'F#6', 'A6', 'B6', 'C#7', 'E7'][k]), 1.0), gain=0.1, pan=0.2 + 0.1 * k)
t0, t1 = EV['ask']
for k in range(24):
    B['fx'].add(sec(t0 + k * (t1 - t0) / 24) + rng.random() * 0.01, A.tick(0.5), gain=0.09, pan=0.3)
for f in EV['calls'] + EV['results2']:
    B['harp'].add(sec(f), A.harp(m('A6'), 0.8), gain=0.07, pan=0.4)
for k, n in enumerate(['A5', 'C#6', 'E6']):        # the answer
    B['harp'].add(sec(EV['answer']) + 0.2 * k, A.harp(m(n), 1.6), gain=0.14)

# ---- lift (bar 45) ------------------------------------------------------------------------------------------------------
pad(45, 'E', layer=2, gain=0.8, attack=0.6)
piano_arp(45, 'E', vel=52, gain=0.8, pattern=(0, 1, 2, 3, 2, 3, 4, 5))
bassline(45, 'E', beats=(0, 2), level=0.6)
groove(45, kick=(0, 1, 2, 3), shaker=True, level=0.7)
for i in range(5):                                  # the evidence lights up gold
    B['harp'].add(sec(EV['gold'] + i * 8), A.harp(m(['A5', 'C#6', 'E6', 'F#6', 'A6'][i]), 1.6), gain=0.12)
B['drums'].add(tb(45), A.perc('Snare2-rollNS_v5_rr1_Sum', dur=2.0, release=0.02), gain=0.22)
swell(sec(EV['act4']), 'Median', 0.9)

# ==== ACT IV · all of science (bars 46–50) ===================================================================================
impact(sec(EV['act4']), 1.0, timp='F#2', crash=True)
FINALE = {46: [(0, 'C#5', 2), (2, 'F#5', 2)], 47: [(0, 'F#5', 2), (2, 'E5', 1), (3, 'D5', 1)],
          48: [(0, 'E5', 2), (2, 'C#5', 1), (3, 'E5', 1)], 49: [(0, 'B4', 2), (2, 'E5', 2)]}
for b in range(46, 50):
    c = PROG[b]
    pad(b, c, layer=2, gain=1.0, attack=0.25)
    melody(b, FINALE[b], layer=2, gain=1.1)
    melody(b, [(q, n[:-1] + str(int(n[-1]) - 1), d) for q, n, d in FINALE[b]], layer=2, gain=0.6, section='cellos')
    ostinato(b, c, sections=('va', 'vc'), sub=4, gain=0.75)
    piano_arp(b, c, vel=60, gain=0.8, pattern=(0, 1, 2, 3, 4, 3, 2, 1))
    bassline(b, c, beats=(0, 1.5, 2, 3.5), dur=0.45, level=0.9)
    groove(b, kick=(0, 2), snare=(1, 3), shaker=True, level=0.9, bassdrum=True)
for k in range(12):                                 # links between fields drawing on
    B['harp'].add(sec(EV['arcs4']) + k * 0.16, A.harp(m(['A5', 'C#6', 'E6', 'F#6'][k % 4]), 1.2), gain=0.08, pan=float(rng.uniform(-0.7, 0.7)))
B['fx'].add(sec(EV['tagline']), A.perc('cymbal-crash1_mp_rr2'), gain=0.15)
B['orch'].add(tb(49), A.timpani(m('B1') - 2, vel=4, roll=True, dur=2.0), gain=0.35)
swell(sec(EV['card']), 'Short', 0.7)

# ---- end card (bar 50): one open A major chord, left to ring ------------------------------------------------------------
tc = sec(EV['card'])
impact(tc, 0.8, timp='B1', crash=False, gong=True, sub_note='A1')
for key, sect, notes in (('vc', 'cellos', ['A2', 'E3']), ('va', 'violas', ['A3', 'C#4']), ('vn', 'violins', ['E4', 'A4', 'C#5', 'E5'])):
    for n in notes:
        B['long'].add(tc - 0.05, A.strings(sect, m(n), 4.2, layer=2, attack=0.15, release=2.2), gain=0.24)
for k, n in enumerate(['A1', 'A2', 'E3', 'A3', 'C#4', 'E4', 'A4', 'C#5', 'E5']):
    B['piano'].add(tc + k * 0.03, A.piano(m(n), 78, 5.5, release=2.0), gain=0.42, pan=-0.5 + k / 8)
for k, n in enumerate(['A4', 'C#5', 'E5', 'A5', 'C#6', 'E6']):
    B['harp'].add(tc + 0.15 + k * 0.09, A.harp(m(n), 4.0), gain=0.14)

# ==== mix ===================================================================================================================
def chain(*fx):
    return Pedalboard(list(fx))

# the strings breathe a little with the kick
kick_env = np.abs(B['drums'].x).mean(1)
duck = 1 - 0.22 * np.clip(np.convolve(kick_env, np.ones(2400) / 2400, mode='same') / (np.percentile(kick_env, 99.5) + 1e-9), 0, 1)
B['short'].x *= duck[:, None] ** 0.6
B['long'].x *= duck[:, None] ** 0.3

proc = {
    'piano': chain(HighpassFilter(55), LowShelfFilter(cutoff_frequency_hz=250, gain_db=-2),
                   Compressor(threshold_db=-24, ratio=2.0, attack_ms=20, release_ms=250)),
    'long': chain(HighpassFilter(60), PeakFilter(cutoff_frequency_hz=300, gain_db=-2.5, q=0.8), HighShelfFilter(cutoff_frequency_hz=4000, gain_db=1.5),
                  Compressor(threshold_db=-22, ratio=1.8, attack_ms=40, release_ms=300)),
    'short': chain(HighpassFilter(70), PeakFilter(cutoff_frequency_hz=2500, gain_db=1.5, q=1.0), Compressor(threshold_db=-24, ratio=2.5, attack_ms=8, release_ms=120)),
    'harp': chain(HighpassFilter(120), HighShelfFilter(cutoff_frequency_hz=9000, gain_db=-2)),
    'orch': chain(HighpassFilter(25), Compressor(threshold_db=-18, ratio=2.0, attack_ms=10, release_ms=200)),
    'drums': chain(HighpassFilter(30), Compressor(threshold_db=-20, ratio=3.0, attack_ms=5, release_ms=120)),
    'bass': chain(HighpassFilter(32), LowpassFilter(140), Compressor(threshold_db=-20, ratio=2.5, attack_ms=15, release_ms=200)),
    'fx': chain(HighpassFilter(60)),
}
send = {'piano': 0.22, 'long': 0.32, 'short': 0.2, 'harp': 0.42, 'orch': 0.26, 'drums': 0.06, 'bass': 0.0, 'fx': 0.3}
level = {'piano': 1.6, 'long': 3.4, 'short': 2.0, 'harp': 1.8, 'orch': 1.0, 'drums': 0.72, 'bass': 0.3, 'fx': 0.7}
dry = np.zeros_like(B['piano'].x)
rev_in = np.zeros_like(dry)
stems = {}
for k, bus in B.items():
    y = A.process(bus.x, proc[k]) * level[k]
    stems[k] = y
    dry += y
    rev_in += y * send[k]
mix = dry + A.reverb(rev_in, 1.0, rt_low=2.6, rt_high=1.0)

# section dynamics (bars → gain): a gentle arc — quieter than v13, never flat
curve = [(0, 0.62), (3, 0.7), (4.9, 0.86), (5, 0.95), (5.5, 0.8), (11.5, 0.8), (16, 0.82), (17, 0.95), (19, 0.62), (23.9, 0.86), (24, 1.0),
         (28, 0.92), (29, 0.88), (37, 0.9), (38, 0.95), (42, 0.86), (45, 0.92), (46, 1.0), (55, 1.0)]
tbars = np.arange(len(mix)) / SR / 2.0
g = np.interp(tbars, [c[0] for c in curve], [c[1] for c in curve])
mix *= g[:, None]
mix = A.process(mix, chain(HighShelfFilter(cutoff_frequency_hz=7000, gain_db=1.5), Compressor(threshold_db=-16, ratio=1.8, attack_ms=30, release_ms=250)))
fade = np.clip((sec(END_F) + 2.5 - np.arange(len(mix)) / SR) / 3.0, 0, 1)
mix *= fade[:, None]
mix = mix / np.abs(mix).max() * 0.9
sf.write('public/audio/score.wav', mix, SR, subtype='PCM_24')
import os
os.makedirs('public/audio/stems', exist_ok=True)
for k, y in stems.items():
    sf.write(f'public/audio/stems/{k}.wav', (y / (np.abs(mix).max() + 1e-9) * 0.9 * g[:, None]).astype(np.float32), SR, subtype='FLOAT')
print(f'duration {len(mix) / SR:.1f}s  rms {20 * np.log10(np.sqrt((mix ** 2).mean())):.1f} dBFS')
