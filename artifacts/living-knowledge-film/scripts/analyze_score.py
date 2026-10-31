"""Look at the score without listening: short-term loudness against the film's scenes, each bus's level, a
log-frequency spectrogram and a scan for clicks. Writes public/audio/analysis.png and prints a short report.

    python3 scripts/analyze_score.py [public/audio/score.wav]
"""
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from scipy import signal

path = sys.argv[1] if len(sys.argv) > 1 else 'public/audio/score.wav'
x, sr = sf.read(path, always_2d=True)
x = x.T
mono = x.mean(0)
SCENES = [('1665', 0), ('pile', 90), ('2026', 300), ('prose', 376), ('links', 466), ('review', 556), ('dated', 656), ('search', 750),
          ('scratch', 880), ('thesis', 1020), ('act II', 1140), ('blade', 1208), ('DROP', 1440), ('living', 1560), ('act III', 1740),
          ('explore', 1890), ('analyze', 2250), ('agents', 2550), ('lift', 2700), ('act IV', 2760), ('card', 3000)]


def kweight(s):
    s = signal.lfilter([1.53512485958697, -2.69169618940638, 1.19839281085285], [1, -1.69065929318241, 0.73248077421585], s, axis=-1)
    return signal.lfilter([1.0, -2.0, 1.0], [1, -1.99004745483398, 0.99007225036621], s, axis=-1)


def loudness(sig, win, hop=0.1):
    z = kweight(sig) ** 2
    w, h = int(win * sr), int(hop * sr)
    c = np.cumsum(np.concatenate([np.zeros((z.shape[0], 1)), z], axis=1), axis=1)
    st = np.arange(0, z.shape[1] - w, h)
    ms = (c[:, st + w] - c[:, st]) / w
    return (st + w / 2) / sr, -0.691 + 10 * np.log10(ms.sum(0) + 1e-12)


t, M = loudness(x, 0.4)
ts, S = loudness(x, 3.0)
fig, ax = plt.subplots(3, 1, figsize=(18, 13), gridspec_kw={'height_ratios': [1.1, 1, 1.5]})
ax[0].plot(t, M, lw=0.5, color='#aaa', label='momentary')
ax[0].plot(ts, S, lw=1.8, color='#2d5bd7', label='short-term (3 s)')
for name, f in SCENES:
    ax[0].axvline(f / 30, color='#222', lw=0.5)
    ax[0].text(f / 30 + 0.2, -6, name, fontsize=8, rotation=90, va='top')
ax[0].set_ylim(-50, -4); ax[0].set_xlim(0, t[-1]); ax[0].set_ylabel('LUFS'); ax[0].legend(loc='lower right'); ax[0].grid(alpha=0.2)

stems = os.path.join(os.path.dirname(path), 'stems')
if os.path.isdir(stems):
    for f in sorted(os.listdir(stems)):
        s, _ = sf.read(os.path.join(stems, f), always_2d=True)
        s = s.mean(1)
        w = int(0.4 * sr)
        r = np.sqrt(np.convolve(s ** 2, np.ones(w) / w, 'same'))[::w // 4]
        ax[1].plot(np.arange(len(r)) * (w // 4) / sr, 20 * np.log10(r + 1e-6), lw=1, label=f[:-4])
    ax[1].legend(ncol=8, fontsize=9, loc='lower center'); ax[1].set_ylim(-70, -5); ax[1].set_xlim(0, t[-1]); ax[1].set_ylabel('bus RMS dB'); ax[1].grid(alpha=0.2)
    for name, f in SCENES:
        ax[1].axvline(f / 30, color='#222', lw=0.5)

f_, tt, Z = signal.spectrogram(mono, sr, nperseg=4096, noverlap=3072)
ax[2].pcolormesh(tt, f_, 10 * np.log10(Z + 1e-14), shading='auto', cmap='magma', vmin=-130, vmax=-40)
ax[2].set_yscale('symlog', linthresh=200); ax[2].set_ylim(30, 16000); ax[2].set_ylabel('Hz'); ax[2].set_xlabel('s')
for name, f in SCENES:
    ax[2].axvline(f / 30, color='w', lw=0.4, alpha=0.6)
plt.tight_layout()
out = os.path.join(os.path.dirname(path), 'analysis.png')
plt.savefig(out, dpi=80)

# clicks: sample-to-sample jumps far above the local level
d = np.abs(np.diff(mono))
loc = np.sqrt(np.convolve(mono ** 2, np.ones(2400) / 2400, 'same'))[1:] + 1e-4
z = d / loc
idx = np.where(z > 3.0)[0]
groups = []
for i in idx:
    if not groups or i - groups[-1][-1] > sr * 0.05:
        groups.append([i])
    else:
        groups[-1].append(i)
print(f'{path}: {x.shape[1] / sr:.1f} s, peak {20 * np.log10(np.abs(x).max()):.1f} dBFS, DC {mono.mean():+.5f}')
print('suspected clicks (s):', ', '.join(f'{g[0] / sr:.2f}' for g in groups[:30]) or 'none')
band = lambda lo, hi: 10 * np.log10((Z[(f_ >= lo) & (f_ < hi)].sum()) + 1e-20)
tot = band(20, 20000)
print('spectral balance (dB vs total): sub<60 %.1f, low 60–250 %.1f, mid 250–2k %.1f, presence 2–6k %.1f, air 6–16k %.1f' % (
    band(20, 60) - tot, band(60, 250) - tot, band(250, 2000) - tot, band(2000, 6000) - tot, band(6000, 16000) - tot))
print('wrote', out)
