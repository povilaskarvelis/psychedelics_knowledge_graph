#!/bin/zsh
set -euo pipefail

# V54 is scored to the edit rather than laid under it as a continuous song.
# All musical sources come from one Apple Loops family so the palette stays
# coherent while the arrangement changes with the film.
loop_root="/Library/Audio/Apple Loops/Apple/01 Hip Hop"
output="public/story/product-v54-soundtrack.wav"
temporary="${TMPDIR:-/tmp}/product-v54-score-premaster.wav"

dark_pad="$loop_root/Legend Dark Synth Pad.caf"
drone="$loop_root/Legend Synth Drone.caf"
fx_pad="$loop_root/Legend FX Synth Pad.caf"
sub_bass="$loop_root/Legend Sub Bass.caf"
beat="$loop_root/Legend Beat.caf"
reveal_fx="$loop_root/Rise Up FX.caf"

for source in "$dark_pad" "$drone" "$fx_pad" "$sub_bass" "$beat" "$reveal_fx"; do
  [[ -f "$source" ]] || { print -u2 "Missing Apple Loop: $source"; exit 1; }
done

ffmpeg -y -loglevel error \
  -i "$dark_pad" \
  -i "$drone" \
  -i "$fx_pad" \
  -i "$sub_bass" \
  -i "$beat" \
  -i "$reveal_fx" \
  -i "$beat" \
  -filter_complex "
    [0:a]asplit=2[dark_a_src][dark_b_src];
    [dark_a_src]atrim=0:23.5,asetpts=PTS-STARTPTS,asetrate=40000,aresample=48000,
      aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=42,lowpass=f=3900,
      volume=0.23,afade=t=in:st=0:d=1.6,afade=t=out:st=22.0:d=3.8[dark_a];
    [dark_b_src]atrim=0:23.5,asetpts=PTS-STARTPTS,areverse,asetrate=40000,aresample=48000,
      aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=42,lowpass=f=3600,
      volume=0.20,afade=t=in:st=0:d=2.4,afade=t=out:st=21.8:d=4.0,adelay=61500|61500[dark_b];

    [1:a]asplit=2[drone_a_src][drone_b_src];
    [drone_a_src]atrim=0:23.5,asetpts=PTS-STARTPTS,asetrate=40000,aresample=48000,
      aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=48,lowpass=f=3300,
      volume=0.17,afade=t=in:st=0:d=2.8,afade=t=out:st=21.8:d=4.0,adelay=20500|20500[drone_a];
    [drone_b_src]atrim=0:15.5,asetpts=PTS-STARTPTS,areverse,asetrate=40000,aresample=48000,
      aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=48,lowpass=f=3100,
      volume=0.18,afade=t=in:st=0:d=2.4,afade=t=out:st=14.6:d=2.5,adelay=81700|81700[drone_b];

    [2:a]atrim=0:23.5,asetpts=PTS-STARTPTS,asetrate=40000,aresample=48000,
      aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=55,lowpass=f=4300,
      volume=0.19,afade=t=in:st=0:d=2.7,afade=t=out:st=21.8:d=4.0,adelay=41000|41000[fx_bed];

    [3:a]asplit=3[bass_reveal_src][bass_analysis_src][bass_tools_src];
    [bass_reveal_src]atrim=0:7.6,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=32,lowpass=f=900,volume=0.15,afade=t=in:st=0:d=0.18,afade=t=out:st=6.7:d=0.9,
      adelay=14470|14470[bass_reveal];
    [bass_analysis_src]atrim=0:23.3,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=32,lowpass=f=850,volume=0.12,afade=t=in:st=0:d=0.7,afade=t=out:st=21.8:d=1.5,
      adelay=47670|47670[bass_analysis];
    [bass_tools_src]atrim=10.5:18.8,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=32,lowpass=f=850,volume=0.13,afade=t=in:st=0:d=0.35,afade=t=out:st=7.3:d=1.0,
      adelay=72930|72930[bass_tools];

    [4:a]asplit=4[beat_reveal_src][beat_drill_src][beat_analysis_src][beat_tools_src];
    [beat_reveal_src]atrim=0:7.55,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=68,lowpass=f=6100,volume=0.12,afade=t=in:st=0:d=0.12,afade=t=out:st=6.8:d=0.75,
      adelay=14470|14470[beat_reveal];
    [beat_drill_src]atrim=7.6:23.35,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=76,lowpass=f=5400,volume=0.075,afade=t=in:st=0:d=0.5,afade=t=out:st=14.4:d=1.35,
      adelay=22070|22070[beat_drill];
    [beat_analysis_src]atrim=0:23.35,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=70,lowpass=f=5900,volume=0.10,afade=t=in:st=0:d=0.75,afade=t=out:st=21.9:d=1.45,
      adelay=47670|47670[beat_analysis];
    [beat_tools_src]atrim=12.0:20.25,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=72,lowpass=f=5600,volume=0.09,afade=t=in:st=0:d=0.35,afade=t=out:st=7.2:d=1.05,
      adelay=72930|72930[beat_tools];

    [5:a]asplit=2[reveal_rise_src][living_rise_src];
    [reveal_rise_src]atrim=7.35:11.80,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=90,lowpass=f=4200,volume=0.11,afade=t=in:st=0:d=0.45,afade=t=out:st=4.0:d=0.45,
      adelay=10020|10020[reveal_rise];
    [living_rise_src]atrim=7.65:11.80,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,
      highpass=f=110,lowpass=f=3600,volume=0.055,afade=t=in:st=0:d=0.55,afade=t=out:st=3.75:d=0.40,
      adelay=77380|77380[living_rise];

    [6:a]asplit=15[i0][i1][i2][i3][i4][i5][i6][i7][i8][i9][i10][i11][i12][i13][i14];
    [i0]atrim=0:0.62,asetpts=PTS-STARTPTS,highpass=f=38,lowpass=f=880,volume=0.23,afade=t=out:st=0.22:d=0.40,adelay=14470|14470[hit0];
    [i1]atrim=0:0.54,asetpts=PTS-STARTPTS,highpass=f=42,lowpass=f=950,volume=0.10,afade=t=out:st=0.20:d=0.34,adelay=22070|22070[hit1];
    [i2]atrim=0:0.48,asetpts=PTS-STARTPTS,highpass=f=48,lowpass=f=1000,volume=0.065,afade=t=out:st=0.18:d=0.30,adelay=30730|30730[hit2];
    [i3]atrim=0:0.48,asetpts=PTS-STARTPTS,highpass=f=48,lowpass=f=1000,volume=0.055,afade=t=out:st=0.18:d=0.30,adelay=35300|35300[hit3];
    [i4]atrim=0:0.48,asetpts=PTS-STARTPTS,highpass=f=48,lowpass=f=1000,volume=0.055,afade=t=out:st=0.18:d=0.30,adelay=39570|39570[hit4];
    [i5]atrim=0:0.48,asetpts=PTS-STARTPTS,highpass=f=48,lowpass=f=1000,volume=0.055,afade=t=out:st=0.18:d=0.30,adelay=43070|43070[hit5];
    [i6]atrim=0:0.58,asetpts=PTS-STARTPTS,highpass=f=40,lowpass=f=900,volume=0.15,afade=t=out:st=0.20:d=0.38,adelay=47670|47670[hit6];
    [i7]atrim=0:0.54,asetpts=PTS-STARTPTS,highpass=f=42,lowpass=f=920,volume=0.10,afade=t=out:st=0.20:d=0.34,adelay=55270|55270[hit7];
    [i8]atrim=0:0.54,asetpts=PTS-STARTPTS,highpass=f=42,lowpass=f=920,volume=0.10,afade=t=out:st=0.20:d=0.34,adelay=62330|62330[hit8];
    [i9]atrim=0:0.58,asetpts=PTS-STARTPTS,highpass=f=40,lowpass=f=900,volume=0.14,afade=t=out:st=0.20:d=0.38,adelay=72930|72930[hit9];
    [i10]atrim=0:0.58,asetpts=PTS-STARTPTS,highpass=f=40,lowpass=f=900,volume=0.15,afade=t=out:st=0.20:d=0.38,adelay=81530|81530[hit10];
    [i11]atrim=0:0.42,asetpts=PTS-STARTPTS,highpass=f=55,lowpass=f=1050,volume=0.052,afade=t=out:st=0.16:d=0.26,adelay=82470|82470[hit11];
    [i12]atrim=0:0.42,asetpts=PTS-STARTPTS,highpass=f=55,lowpass=f=1050,volume=0.052,afade=t=out:st=0.16:d=0.26,adelay=85400|85400[hit12];
    [i13]atrim=0:0.42,asetpts=PTS-STARTPTS,highpass=f=55,lowpass=f=1050,volume=0.052,afade=t=out:st=0.16:d=0.26,adelay=88330|88330[hit13];
    [i14]atrim=0:0.70,asetpts=PTS-STARTPTS,highpass=f=38,lowpass=f=780,volume=0.16,afade=t=out:st=0.24:d=0.46,adelay=92130|92130[hit14];

    [dark_a][drone_a][fx_bed][dark_b][drone_b]
    [bass_reveal][bass_analysis][bass_tools]
    [beat_reveal][beat_drill][beat_analysis][beat_tools]
    [reveal_rise][living_rise]
    [hit0][hit1][hit2][hit3][hit4][hit5][hit6][hit7][hit8][hit9][hit10][hit11][hit12][hit13][hit14]
      amix=inputs=29:duration=longest:normalize=0,
      highpass=f=30,lowpass=f=7800,
      acompressor=threshold=0.24:ratio=1.55:attack=28:release=300:makeup=1.05,
      alimiter=limit=0.88:attack=7:release=90,
      afade=t=out:st=94.7:d=3.4,
      apad=whole_dur=98.133333,atrim=0:98.133333[audio]
  " \
  -map "[audio]" -c:a pcm_s24le -ar 48000 -ac 2 "$temporary"

ffmpeg -y -loglevel error -i "$temporary" \
  -af "loudnorm=I=-16.2:LRA=10:TP=-1.3,apad=whole_dur=98.133333,atrim=0:98.133333" \
  -c:a pcm_s24le -ar 48000 -ac 2 "$output"

rm -f "$temporary"

ffprobe -v error \
  -show_entries format=duration,size \
  -show_entries stream=codec_name,sample_rate,channels \
  -of json "$output"
