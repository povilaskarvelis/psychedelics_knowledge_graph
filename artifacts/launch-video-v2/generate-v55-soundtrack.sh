#!/bin/zsh
set -euo pipefail

# V55: warm, spatial, and slightly uncanny rather than upbeat or dark.
# The score moves from organic ambience to modular precision and back again.
chill_root="/Library/Audio/Apple Loops/Apple/07 Chillwave"
hip_root="/Library/Audio/Apple Loops/Apple/01 Hip Hop"
output="public/story/product-v55-soundtrack.wav"
temporary="${TMPDIR:-/tmp}/product-v55-score-premaster.wav"

afloat_pad="$hip_root/Afloat Pad.caf"
afloat_bass="$hip_root/Afloat Sub Bass.caf"
afloat_beat="$hip_root/Afloat Beat.caf"
euphoria_pad="$hip_root/Euphoria Pad.caf"
wave_pad="$chill_root/Harmonic Waves Synth Pad.caf"
ghost_guitar="$chill_root/Ghost Harmonics Guitar.caf"
genetic_one="$chill_root/Genetic Code Layers 01.caf"
genetic_two="$chill_root/Genetic Code Layers 02.caf"
continuum_one="$chill_root/Continuum Beat 01.caf"
continuum_two="$chill_root/Continuum Beat 02.caf"
continuum_three="$chill_root/Continuum Beat 03.caf"
reverse_hat_one="$chill_root/Reverse Hat Beat 01.caf"
reverse_hat_two="$chill_root/Reverse Hat Beat 02.caf"
next_wave_one="$chill_root/Next Wave Beat 01.caf"
next_wave_two="$chill_root/Next Wave Beat 02.caf"

for source in \
  "$afloat_pad" "$afloat_bass" "$afloat_beat" "$euphoria_pad" "$wave_pad" \
  "$ghost_guitar" "$genetic_one" "$genetic_two" \
  "$continuum_one" "$continuum_two" "$continuum_three" \
  "$reverse_hat_one" "$reverse_hat_two" "$next_wave_one" "$next_wave_two"; do
  [[ -f "$source" ]] || { print -u2 "Missing Apple Loop: $source"; exit 1; }
done

ffmpeg -y -loglevel error \
  -i "$afloat_pad" \
  -i "$afloat_bass" \
  -i "$afloat_beat" \
  -i "$euphoria_pad" \
  -i "$wave_pad" \
  -i "$ghost_guitar" \
  -i "$genetic_one" \
  -i "$genetic_two" \
  -i "$continuum_one" \
  -i "$continuum_two" \
  -i "$continuum_three" \
  -i "$reverse_hat_one" \
  -i "$reverse_hat_two" \
  -i "$next_wave_one" \
  -i "$next_wave_two" \
  -filter_complex "
    [0:a]asplit=4[afloat_open_src][afloat_open_high_src][afloat_return_src][afloat_outro_src];
    [afloat_open_src]atrim=0:19.45,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=48,lowpass=f=5000,aphaser=in_gain=0.67:out_gain=0.72:delay=2.1:decay=0.24:speed=0.21:type=s,
      stereowiden=delay=12:feedback=0.08:crossfeed=0.18:drymix=0.92,volume=0.20,
      afade=t=in:st=0:d=1.5,afade=t=out:st=17.2:d=2.25[afloat_open];
    [afloat_open_high_src]atrim=14.47:19.45,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=1700,lowpass=f=8600,volume=0.07,afade=t=in:st=0:d=0.55,afade=t=out:st=4.2:d=0.78,
      adelay=14470|14470[afloat_open_high];
    [afloat_return_src]atrim=0:19.45,asetpts=PTS-STARTPTS,areverse,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=52,lowpass=f=5100,aphaser=in_gain=0.68:out_gain=0.72:delay=2.5:decay=0.21:speed=0.18:type=s,
      stereowiden=delay=16:feedback=0.10:crossfeed=0.16:drymix=0.90,volume=0.13,
      afade=t=in:st=0:d=2.2,afade=t=out:st=17.2:d=2.25,adelay=61000|61000[afloat_return];
    [afloat_outro_src]atrim=8.5:18.0,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=48,lowpass=f=5900,aphaser=in_gain=0.70:out_gain=0.72:delay=1.8:decay=0.18:speed=0.16:type=s,
      stereowiden=delay=18:feedback=0.07:crossfeed=0.16:drymix=0.93,volume=0.16,
      afade=t=in:st=0:d=1.7,afade=t=out:st=6.3:d=3.2,adelay=88600|88600[afloat_outro];

    [1:a]atrim=0:7.65,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=34,lowpass=f=1150,volume=0.12,afade=t=in:st=0:d=0.35,afade=t=out:st=6.7:d=0.95,
      adelay=14470|14470[afloat_bass_reveal];

    [2:a]asplit=2[afloat_beat_reveal_src][impact_src];
    [afloat_beat_reveal_src]atrim=0:7.65,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=70,lowpass=f=6800,volume=0.095,afade=t=in:st=0:d=0.18,afade=t=out:st=6.8:d=0.85,
      adelay=14470|14470[afloat_beat_reveal];

    [3:a]asplit=3[euphoria_a_src][euphoria_b_src][euphoria_c_src];
    [euphoria_a_src]atrim=0:14.55,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=52,lowpass=f=6500,aphaser=in_gain=0.72:out_gain=0.70:delay=2.0:decay=0.20:speed=0.24:type=s,
      stereowiden=delay=14:feedback=0.08:crossfeed=0.16:drymix=0.93,volume=0.15,
      afade=t=in:st=0:d=1.5,afade=t=out:st=12.4:d=2.15,adelay=17800|17800[euphoria_a];
    [euphoria_b_src]atrim=0:14.55,asetpts=PTS-STARTPTS,areverse,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=52,lowpass=f=5600,aphaser=in_gain=0.68:out_gain=0.72:delay=2.4:decay=0.19:speed=0.19:type=s,
      volume=0.115,afade=t=in:st=0:d=2.0,afade=t=out:st=12.3:d=2.25,adelay=39500|39500[euphoria_b];
    [euphoria_c_src]atrim=2.8:12.4,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=58,lowpass=f=6200,aphaser=in_gain=0.70:out_gain=0.70:delay=1.9:decay=0.17:speed=0.14:type=s,
      stereowiden=delay=15:feedback=0.06:crossfeed=0.15:drymix=0.94,volume=0.105,
      afade=t=in:st=0:d=1.6,afade=t=out:st=7.0:d=2.6,adelay=81600|81600[euphoria_c];

    [4:a]asplit=3[wave_a_src][wave_b_src][wave_c_src];
    [wave_a_src]atrim=0:10.55,asetpts=PTS-STARTPTS,asetrate=40000,aresample=48000,
      aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=58,lowpass=f=6600,
      stereowiden=delay=17:feedback=0.06:crossfeed=0.16:drymix=0.94,volume=0.14,
      afade=t=in:st=0:d=1.6,afade=t=out:st=9.7:d=1.9,adelay=29900|29900[wave_a];
    [wave_b_src]atrim=0:10.55,asetpts=PTS-STARTPTS,areverse,asetrate=40000,aresample=48000,
      aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=58,lowpass=f=6100,
      aphaser=in_gain=0.70:out_gain=0.72:delay=2.3:decay=0.18:speed=0.20:type=s,volume=0.12,
      afade=t=in:st=0:d=1.7,afade=t=out:st=9.6:d=2.0,adelay=51800|51800[wave_b];
    [wave_c_src]atrim=0:10.55,asetpts=PTS-STARTPTS,asetrate=40000,aresample=48000,
      aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=58,lowpass=f=7200,
      aphaser=in_gain=0.69:out_gain=0.72:delay=2.8:decay=0.20:speed=0.27:type=s,
      stereowiden=delay=20:feedback=0.09:crossfeed=0.13:drymix=0.91,volume=0.13,
      afade=t=in:st=0:d=1.6,afade=t=out:st=9.5:d=2.1,adelay=77800|77800[wave_c];

    [5:a]asplit=2[ghost_rise_src][ghost_explore_src];
    [ghost_rise_src]atrim=0:4.45,asetpts=PTS-STARTPTS,areverse,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=130,lowpass=f=7200,aecho=0.74:0.25:290|510:0.16|0.08,
      stereowiden=delay=22:feedback=0.10:crossfeed=0.14:drymix=0.91,volume=0.10,
      afade=t=in:st=0:d=0.65,afade=t=out:st=4.0:d=0.45,adelay=10020|10020[ghost_rise];
    [ghost_explore_src]atrim=0:9.45,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=150,lowpass=f=7000,aecho=0.78:0.24:330|620:0.14|0.07,
      aphaser=in_gain=0.73:out_gain=0.69:delay=2.2:decay=0.17:speed=0.22:type=s,volume=0.048,
      afade=t=in:st=0:d=1.0,afade=t=out:st=8.2:d=1.25,adelay=22070|22070[ghost_explore];

    [6:a]asplit=3[genetic_breadth_src][genetic_analysis_src][genetic_live_a_src];
    [genetic_breadth_src]atrim=0:4.75,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=150,lowpass=f=6900,stereowiden=delay=20:feedback=0.11:crossfeed=0.13:drymix=0.90,
      volume=0.070,afade=t=in:st=0:d=0.7,afade=t=out:st=3.8:d=0.95,adelay=5750|5750[genetic_breadth];
    [genetic_analysis_src]atrim=0:4.75,asetpts=PTS-STARTPTS,areverse,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=160,lowpass=f=6700,aphaser=in_gain=0.72:out_gain=0.69:delay=2.0:decay=0.16:speed=0.25:type=s,
      volume=0.065,afade=t=in:st=0:d=0.65,afade=t=out:st=3.8:d=0.95,adelay=47670|47670[genetic_analysis];
    [genetic_live_a_src]atrim=0:4.75,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=150,lowpass=f=7000,stereowiden=delay=24:feedback=0.12:crossfeed=0.12:drymix=0.89,
      volume=0.078,afade=t=in:st=0:d=0.5,afade=t=out:st=3.9:d=0.85,adelay=81530|81530[genetic_live_a];

    [7:a]asplit=2[genetic_reveal_src][genetic_live_b_src];
    [genetic_reveal_src]atrim=0:4.75,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=145,lowpass=f=7400,aphaser=in_gain=0.70:out_gain=0.71:delay=2.4:decay=0.18:speed=0.28:type=s,
      stereowiden=delay=22:feedback=0.10:crossfeed=0.13:drymix=0.90,volume=0.09,
      afade=t=in:st=0:d=0.35,afade=t=out:st=3.9:d=0.85,adelay=14470|14470[genetic_reveal];
    [genetic_live_b_src]atrim=0:4.75,asetpts=PTS-STARTPTS,areverse,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=150,lowpass=f=7200,aphaser=in_gain=0.72:out_gain=0.70:delay=2.7:decay=0.17:speed=0.24:type=s,
      volume=0.078,afade=t=in:st=0:d=0.5,afade=t=out:st=3.9:d=0.85,adelay=86300|86300[genetic_live_b];

    [8:a]asplit=2[continuum_one_a_src][continuum_one_b_src];
    [continuum_one_a_src]atrim=0:5.55,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=82,lowpass=f=7200,volume=0.068,afade=t=in:st=0:d=0.30,afade=t=out:st=4.8:d=0.75,
      adelay=22070|22070[continuum_one_a];
    [continuum_one_b_src]atrim=0:5.55,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=82,lowpass=f=7000,volume=0.070,afade=t=in:st=0:d=0.25,afade=t=out:st=4.8:d=0.75,
      adelay=58330|58330[continuum_one_b];
    [9:a]asplit=2[continuum_two_a_src][continuum_two_b_src];
    [continuum_two_a_src]atrim=0:5.55,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=82,lowpass=f=7200,volume=0.072,afade=t=in:st=0:d=0.25,afade=t=out:st=4.8:d=0.75,
      adelay=30730|30730[continuum_two_a];
    [continuum_two_b_src]atrim=0:5.55,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=82,lowpass=f=6900,volume=0.066,afade=t=in:st=0:d=0.25,afade=t=out:st=4.8:d=0.75,
      adelay=63980|63980[continuum_two_b];
    [10:a]asplit=2[continuum_three_a_src][continuum_three_b_src];
    [continuum_three_a_src]atrim=0:5.55,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=82,lowpass=f=7100,volume=0.070,afade=t=in:st=0:d=0.25,afade=t=out:st=4.8:d=0.75,
      adelay=36300|36300[continuum_three_a];
    [continuum_three_b_src]atrim=0:5.55,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=82,lowpass=f=6800,volume=0.062,afade=t=in:st=0:d=0.25,afade=t=out:st=4.8:d=0.75,
      adelay=69600|69600[continuum_three_b];

    [11:a]atrim=0:5.25,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=96,lowpass=f=6900,volume=0.067,afade=t=in:st=0:d=0.35,afade=t=out:st=4.45:d=0.80,
      adelay=47670|47670[reverse_hat_a];
    [12:a]atrim=0:5.25,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=96,lowpass=f=6700,volume=0.064,afade=t=in:st=0:d=0.30,afade=t=out:st=4.45:d=0.80,
      adelay=52950|52950[reverse_hat_b];
    [13:a]atrim=0:4.30,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=88,lowpass=f=7300,volume=0.082,afade=t=in:st=0:d=0.28,afade=t=out:st=3.55:d=0.75,
      adelay=72930|72930[next_wave_a];
    [14:a]atrim=0:4.30,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=88,lowpass=f=7300,volume=0.080,afade=t=in:st=0:d=0.25,afade=t=out:st=3.55:d=0.75,
      adelay=77290|77290[next_wave_b];

    [impact_src]asplit=15[i0][i1][i2][i3][i4][i5][i6][i7][i8][i9][i10][i11][i12][i13][i14];
    [i0]atrim=0:0.62,asetpts=PTS-STARTPTS,highpass=f=42,lowpass=f=1050,volume=0.18,afade=t=out:st=0.20:d=0.42,adelay=14470|14470[hit0];
    [i1]atrim=0:0.48,asetpts=PTS-STARTPTS,highpass=f=50,lowpass=f=1200,volume=0.075,afade=t=out:st=0.17:d=0.31,adelay=22070|22070[hit1];
    [i2]atrim=0:0.42,asetpts=PTS-STARTPTS,highpass=f=56,lowpass=f=1300,volume=0.047,afade=t=out:st=0.15:d=0.27,adelay=30730|30730[hit2];
    [i3]atrim=0:0.42,asetpts=PTS-STARTPTS,highpass=f=56,lowpass=f=1300,volume=0.044,afade=t=out:st=0.15:d=0.27,adelay=35300|35300[hit3];
    [i4]atrim=0:0.42,asetpts=PTS-STARTPTS,highpass=f=56,lowpass=f=1300,volume=0.044,afade=t=out:st=0.15:d=0.27,adelay=39570|39570[hit4];
    [i5]atrim=0:0.42,asetpts=PTS-STARTPTS,highpass=f=56,lowpass=f=1300,volume=0.044,afade=t=out:st=0.15:d=0.27,adelay=43070|43070[hit5];
    [i6]atrim=0:0.55,asetpts=PTS-STARTPTS,highpass=f=46,lowpass=f=1100,volume=0.115,afade=t=out:st=0.19:d=0.36,adelay=47670|47670[hit6];
    [i7]atrim=0:0.50,asetpts=PTS-STARTPTS,highpass=f=48,lowpass=f=1150,volume=0.082,afade=t=out:st=0.18:d=0.32,adelay=55270|55270[hit7];
    [i8]atrim=0:0.50,asetpts=PTS-STARTPTS,highpass=f=48,lowpass=f=1150,volume=0.082,afade=t=out:st=0.18:d=0.32,adelay=62330|62330[hit8];
    [i9]atrim=0:0.56,asetpts=PTS-STARTPTS,highpass=f=44,lowpass=f=1080,volume=0.12,afade=t=out:st=0.19:d=0.37,adelay=72930|72930[hit9];
    [i10]atrim=0:0.56,asetpts=PTS-STARTPTS,highpass=f=44,lowpass=f=1080,volume=0.115,afade=t=out:st=0.19:d=0.37,adelay=81530|81530[hit10];
    [i11]atrim=0:0.38,asetpts=PTS-STARTPTS,highpass=f=62,lowpass=f=1500,volume=0.046,afade=t=out:st=0.13:d=0.25,adelay=82470|82470[hit11];
    [i12]atrim=0:0.38,asetpts=PTS-STARTPTS,highpass=f=62,lowpass=f=1500,volume=0.046,afade=t=out:st=0.13:d=0.25,adelay=85400|85400[hit12];
    [i13]atrim=0:0.38,asetpts=PTS-STARTPTS,highpass=f=62,lowpass=f=1500,volume=0.046,afade=t=out:st=0.13:d=0.25,adelay=88330|88330[hit13];
    [i14]atrim=0:0.68,asetpts=PTS-STARTPTS,highpass=f=42,lowpass=f=980,volume=0.12,afade=t=out:st=0.22:d=0.46,adelay=92130|92130[hit14];

    [afloat_open][afloat_open_high][afloat_return][afloat_outro]
    [afloat_bass_reveal][afloat_beat_reveal]
    [euphoria_a][euphoria_b][euphoria_c][wave_a][wave_b][wave_c]
    [ghost_rise][ghost_explore]
    [genetic_breadth][genetic_analysis][genetic_live_a][genetic_reveal][genetic_live_b]
    [continuum_one_a][continuum_one_b][continuum_two_a][continuum_two_b][continuum_three_a][continuum_three_b]
    [reverse_hat_a][reverse_hat_b][next_wave_a][next_wave_b]
    [hit0][hit1][hit2][hit3][hit4][hit5][hit6][hit7][hit8][hit9][hit10][hit11][hit12][hit13][hit14]
      amix=inputs=44:duration=longest:normalize=0,
      highpass=f=31,lowpass=f=8900,
      acompressor=threshold=0.27:ratio=1.42:attack=32:release=340:makeup=1.04,
      alimiter=limit=0.89:attack=7:release=95,
      afade=t=out:st=94.9:d=3.2,
      apad=whole_dur=98.133333,atrim=0:98.133333[audio]
  " \
  -map "[audio]" -c:a pcm_s24le -ar 48000 -ac 2 "$temporary"

ffmpeg -y -loglevel error -i "$temporary" \
  -af "loudnorm=I=-15.9:LRA=10:TP=-1.3,apad=whole_dur=98.133333,atrim=0:98.133333" \
  -c:a pcm_s24le -ar 48000 -ac 2 "$output"

rm -f "$temporary"

ffprobe -v error \
  -show_entries format=duration,size \
  -show_entries stream=codec_name,sample_rate,channels \
  -of json "$output"
