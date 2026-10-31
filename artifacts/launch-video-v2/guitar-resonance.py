"""Create a continuous spectral sustain from guitar, omitting its pick envelope."""
import subprocess
import sys
import numpy as np

source, target = sys.argv[1:]
rate, size, hop = 48000, 65536, 16384
raw = subprocess.check_output([
    'ffmpeg', '-v', 'error', '-i', source, '-t', '2.5',
    '-ar', str(rate), '-ac', '2', '-f', 'f32le', '-'
])
samples = np.frombuffer(raw, dtype='<f4').reshape(-1, 2)
window = np.hanning(size)
# Average the resonant spectrum, discarding the original amplitude/attack pattern.
spectra = []
for start in [int(rate * x) for x in [.25, .45, .65]]:
    frame = samples[start:start + size]
    frame = np.pad(frame, ((0, max(0, size-len(frame))), (0, 0)))
    spectra.append(np.abs(np.fft.rfft(frame * window[:, None], axis=0)))
magnitude = np.mean(spectra, axis=0)
frequency = np.fft.rfftfreq(size, 1/rate)
tone = (1-np.exp(-(frequency/140)**4)) * np.exp(-(frequency/2400)**2)
magnitude *= tone[:, None]

length = 12*rate
result = np.zeros((length+2*size, 2))
weight = np.zeros(length+2*size)
rng = np.random.default_rng(60)
for position in range(0, length+size, hop):
    phase = rng.uniform(-np.pi, np.pi, len(frequency))
    # Shared phases with a small stereo offset give width without antiphase bass.
    stereo_phase = np.column_stack((phase, phase + .28*np.sin(frequency/420)))
    frame = np.fft.irfft(magnitude * np.exp(1j*stereo_phase), n=size, axis=0)
    result[position:position+size] += frame * window[:, None]
    weight[position:position+size] += window**2
result /= np.maximum(weight[:, None], .1)
result = result[size//2:size//2+length]
result *= .11 / max(np.sqrt(np.mean(result**2)), 1e-8)
result *= min(1, .72/max(np.max(np.abs(result)), 1e-8))
subprocess.run([
    'ffmpeg', '-y', '-v', 'error', '-f', 'f32le', '-ar', str(rate),
    '-ac', '2', '-i', '-', '-c:a', 'pcm_f32le', target
], input=result.astype('<f4').tobytes(), check=True)
