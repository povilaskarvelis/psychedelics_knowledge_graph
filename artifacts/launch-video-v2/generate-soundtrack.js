const fs = require('fs');
const path = require('path');

const sampleRate = 48000;
const landscape = process.argv.includes('--landscape');
const story = process.argv.includes('--story');
const motion = process.argv.includes('--motion');
const research = process.argv.includes('--research');
const product = process.argv.includes('--product');
const productV8 = process.argv.includes('--product-v8');
const productV9 = process.argv.includes('--product-v9');
const productV19 = process.argv.includes('--product-v19');
const productV18 = process.argv.includes('--product-v18');
const productV17 = process.argv.includes('--product-v17');
const productV15 = process.argv.includes('--product-v15');
const productV13 = process.argv.includes('--product-v13');
const productV11 = process.argv.includes('--product-v11');
const productV10 = process.argv.includes('--product-v10');
const duration = productV19 ? 2870/30 : productV18 ? 2870/30 : productV17 ? 98.2 : productV15 ? 104.6 : productV13 ? 104.6 : productV11 ? 112.2 : productV10 ? 112.2 : productV9 ? 105.4 : productV8 ? 97.4 : product ? 88 : research ? 57 : motion ? 70 : story ? 94 : landscape ? 35 : 34;
const frames = sampleRate * duration;
const left = new Float32Array(frames);
const right = new Float32Array(frames);
const bpm = 112;
const beat = 60 / bpm;
const transitions = productV19 ? [0.6,3.5,6.2,9.03,10.27,14.87,16.3,17.07,18.27,22.97,25.73,30.3,34.57,38.07,42.67,50.27,59.87,70.47,79.07,89.67] : productV18 ? [2.5,6.2,9.03,10.27,14.87,16.3,17.07,18.27,22.97,25.73,30.3,34.57,38.07,42.67,50.27,59.87,70.47,79.07,89.67] : productV17 ? [2.5,5.3,8.2,9.4,14.9,19.6,20.8,25.5,28.3,32.8,37.1,40.6,45.2,52.8,62.4,73,81.6,92.2] : productV15 ? [2.5,5.3,8.2,9.4,19.3,24,25.2,29.9,32.7,37.2,41.5,45,51.6,59.2,68.8,79.4,90,98.6] : productV13 ? [2.5,6.1,9.5,17.2,19.5,24,25.2,31.3,32.7,37.2,41.5,45,51.6,59.2,68.8,79.4,90,98.6] : productV11 ? [2.5,6.1,9.5,17.2,19.5,24,25.2,31.3,32.7,37.2,41.5,45,51.6,55.8,61.2,68.8,76.4,87,97.6,106.2] : productV10 ? [2.5,6.1,9.5,17.2,19.5,24,25.2,31.3,32.7,37.2,41.5,45,51.6,55.8,61.2,68.8,76.4,87,97.6,106.2] : productV9 ? [2.5,6.1,9.5,17.2,19.5,24,25.2,31.3,32.7,37.2,41.5,45.6,50.9,57.4,65.5,75.5,80.2,90.8,99.4] : productV8 ? [2.5,5.9,11.7,13.8,20,21.2,27.3,28.7,33.2,37.5,41.6,46.9,53.4,61.5,68.5,73.2,82.8,91.4] : product ? [2.9,5.1,7.2,14.6,21.8,23.4,28.3,32.8,37.2,49.2,59.2,64.3,73.9,82] : research ? [2.73,5.57,11.83,18.03,23,26.9,35,44,51] : motion ? [2.1,4.5,9.1,15,21,30,36,42,48,55,63] : story ? [11,18,24,35.6667,44.3333,52.3333,59.3333,67,78,87] : landscape ? [4, 7, 13.8667, 20.6667, 28.3333] : [5.33, 9.33, 14.33, 17.83, 22.83, 28.67];

let seed = 78341;
const random = () => {
  seed = (seed * 1664525 + 1013904223) >>> 0;
  return seed / 4294967296 * 2 - 1;
};

const smoothstep = (a, b, x) => {
  const p = Math.max(0, Math.min(1, (x - a) / (b - a)));
  return p * p * (3 - 2 * p);
};

for (let i = 0; i < frames; i++) {
  const t = i / sampleRate;
  const fadeIn = smoothstep(0, 1.2, t);
  const fadeOut = 1 - smoothstep(duration - 2.2, duration, t);
  const master = fadeIn * fadeOut;
  const sectionLift = 0.72 + 0.28 * smoothstep(8.8, 15.2, t);

  // A restrained low electronic bed: present enough to carry motion, quiet enough for social autoplay.
  const bass = Math.sin(2 * Math.PI * 55 * t + 0.14 * Math.sin(t * 0.6)) * 0.052;
  const fifth = Math.sin(2 * Math.PI * 82.407 * t + 0.8) * 0.022;
  const air = Math.sin(2 * Math.PI * 220 * t + 0.4 * Math.sin(t * 0.33)) * 0.007;

  const beatPhase = (t % beat) / beat;
  const halfPhase = (t % (beat / 2)) / (beat / 2);
  const kickEnv = Math.exp(-beatPhase * 13);
  const localBeatTime = t % beat;
  const kickPhase = 48 * localBeatTime + 72 * beat / 18 * (1 - Math.exp(-beatPhase * 18));
  const kick = Math.sin(2 * Math.PI * kickPhase) * kickEnv * 0.058 * smoothstep(1.2, 3.2, t);
  const hat = random() * Math.exp(-halfPhase * 52) * 0.010 * smoothstep(4.8, 8, t);

  let whooshL = 0;
  let whooshR = 0;
  let impact = 0;
  for (let k = 0; k < transitions.length; k++) {
    const dt = t - transitions[k];
    if (dt > -0.72 && dt < 0.04) {
      const p = (dt + 0.72) / 0.76;
      const env = Math.sin(Math.PI * p) * (0.25 + 0.75 * p);
      const noise = random() * env * 0.042;
      whooshL += noise * (k % 2 ? 1 : 0.58);
      whooshR += noise * (k % 2 ? 0.58 : 1);
    }
    if (dt >= 0 && dt < 0.42) {
      const env = Math.exp(-dt * 12);
      impact += Math.sin(2 * Math.PI * (42 * dt + 32 / 18 * (1 - Math.exp(-dt * 18)))) * env * 0.12;
    }
  }

  // Sparse glass tones after the knowledge structure appears.
  let glass = 0;
  const glassTimes = landscape ? [5.1,5.3,5.5,9.6,10,10.4,16.37,17.3,18.27,23.3,24.2,25.17,29.33,30.33] : [10.2, 11.05, 11.9, 12.75, 15.0, 15.8, 16.6, 23.7, 24.5, 25.3, 26.1, 30.0, 30.7];
  for (let g = 0; g < glassTimes.length; g++) {
    const dt = t - glassTimes[g];
    if (dt >= 0 && dt < 1.1) {
      const freq = [523.25, 659.25, 783.99, 987.77][g % 4];
      glass += Math.sin(2 * Math.PI * freq * dt) * Math.exp(-dt * 4.7) * 0.017;
    }
  }

  const common = (bass + fifth + air + kick + impact + glass + hat) * master * sectionLift;
  left[i] = common + whooshL * master;
  right[i] = common + whooshR * master;
}

let peak = 0;
for (let i = 0; i < frames; i++) peak = Math.max(peak, Math.abs(left[i]), Math.abs(right[i]));
const gain = peak ? 0.86 / peak : 1;
const dataBytes = frames * 2 * 2;
const buffer = Buffer.alloc(44 + dataBytes);
buffer.write('RIFF', 0);
buffer.writeUInt32LE(36 + dataBytes, 4);
buffer.write('WAVE', 8);
buffer.write('fmt ', 12);
buffer.writeUInt32LE(16, 16);
buffer.writeUInt16LE(1, 20);
buffer.writeUInt16LE(2, 22);
buffer.writeUInt32LE(sampleRate, 24);
buffer.writeUInt32LE(sampleRate * 4, 28);
buffer.writeUInt16LE(4, 32);
buffer.writeUInt16LE(16, 34);
buffer.write('data', 36);
buffer.writeUInt32LE(dataBytes, 40);
for (let i = 0; i < frames; i++) {
  buffer.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(left[i] * gain * 32767))), 44 + i * 4);
  buffer.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(right[i] * gain * 32767))), 46 + i * 4);
}

const target = path.join(__dirname, productV19 ? 'public/story/product-v19-soundtrack.wav' : productV18 ? 'public/story/product-v18-soundtrack.wav' : productV17 ? 'public/story/product-v17-soundtrack.wav' : productV15 ? 'public/story/product-v15-soundtrack.wav' : productV13 ? 'public/story/product-v13-soundtrack.wav' : productV11 ? 'public/story/product-v11-soundtrack.wav' : productV10 ? 'public/story/product-v10-soundtrack.wav' : productV9 ? 'public/story/product-v9-soundtrack.wav' : productV8 ? 'public/story/product-v8-soundtrack.wav' : product ? 'public/story/product-soundtrack.wav' : research ? 'public/story/research-soundtrack.wav' : motion ? 'public/story/motion-soundtrack.wav' : story ? 'public/story/soundtrack.wav' : landscape ? 'public/landscape/soundtrack.wav' : 'public/assets/soundtrack.wav');
fs.writeFileSync(target, buffer);
console.log(target);
