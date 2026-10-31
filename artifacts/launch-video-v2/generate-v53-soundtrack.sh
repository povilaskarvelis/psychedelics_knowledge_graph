#!/bin/zsh
set -euo pipefail

loop_root="/Library/Audio/Apple Loops/Apple/07 Chillwave"
output="public/story/product-v53-soundtrack.wav"
temporary="${TMPDIR:-/tmp}/product-v53-score-premaster.wav"

synth="$loop_root/Evolving Space Synth.caf"
bass="$loop_root/Evolving Space Bass.caf"
beat_one="$loop_root/Solid Structure Beat 01.caf"
beat_two="$loop_root/Solid Structure Beat 02.caf"
texture_one="$loop_root/Genetic Code Layers 01.caf"
texture_two="$loop_root/Genetic Code Layers 02.caf"
riser="$loop_root/Early Riser Layers 01.caf"
bell="$loop_root/Cosmic Bell Layers 01.caf"

for source in "$synth" "$bass" "$beat_one" "$beat_two" "$texture_one" "$texture_two" "$riser" "$bell"; do
  [[ -f "$source" ]] || { print -u2 "Missing Apple Loop: $source"; exit 1; }
done

ffmpeg -y -loglevel error \
  -stream_loop -1 -i "$synth" \
  -stream_loop -1 -i "$bass" \
  -stream_loop -1 -i "$beat_one" \
  -stream_loop -1 -i "$beat_two" \
  -stream_loop -1 -i "$texture_one" \
  -stream_loop -1 -i "$texture_two" \
  -i "$riser" \
  -i "$bell" \
  -filter_complex "
    [0:a]atrim=0:98.133333,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=55,lowpass=f=9200,
      volume='if(lt(t,4.8),0.15+0.03*t,if(lt(t,9.6),0.30,if(lt(t,14.4),0.22,if(lt(t,91.2),0.34,0.28))))':eval=frame,
      afade=t=in:st=0:d=1.2,afade=t=out:st=94.3:d=3.8[synth];
    [1:a]atrim=0:98.133333,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=38,lowpass=f=1500,
      volume='if(lt(t,14.4),0,if(lt(t,22),0.12,if(lt(t,72),0.18,if(lt(t,81.6),0.11,if(lt(t,91.2),0.18,0)))))':eval=frame[bass];
    [2:a]atrim=0:98.133333,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=90,lowpass=f=10500,
      volume='if(lt(t,14.4),0,if(lt(mod(t-14.4,9.6),4.8),if(lt(t,72),0.12,if(lt(t,81.6),0.065,if(lt(t,91.2),0.13,0))),0))':eval=frame[beat1];
    [3:a]atrim=0:98.133333,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=90,lowpass=f=10500,
      volume='if(lt(t,14.4),0,if(gte(mod(t-14.4,9.6),4.8),if(lt(t,72),0.105,if(lt(t,81.6),0.055,if(lt(t,91.2),0.115,0))),0))':eval=frame[beat2];
    [4:a]atrim=0:98.133333,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=180,lowpass=f=7800,
      volume='if(between(t,4.8,9.6),0.065,if(between(t,48,72),0.045,if(between(t,81.6,91.2),0.065,0)))':eval=frame[texture1];
    [5:a]atrim=0:98.133333,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=180,lowpass=f=7800,
      volume='if(between(t,19.2,38.4),0.04,if(between(t,57.6,72),0.05,if(between(t,86.4,91.2),0.055,0)))':eval=frame[texture2];
    [6:a]atrim=0:4.8,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=140,lowpass=f=9000,
      volume=0.17,afade=t=in:st=0:d=0.5,afade=t=out:st=4.25:d=0.55,adelay=9600|9600[riser];
    [7:a]asplit=2[bellA][bellB];
    [bellA]atrim=0:4.8,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=260,lowpass=f=11000,
      volume=0.105,afade=t=in:st=0:d=0.08,afade=t=out:st=3.7:d=1.1,adelay=14400|14400[reveal];
    [bellB]atrim=0:4.8,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=320,lowpass=f=8500,
      volume=0.075,afade=t=in:st=0:d=0.15,afade=t=out:st=2.9:d=1.9,adelay=91200|91200[outro];
    [synth][bass][beat1][beat2][texture1][texture2][riser][reveal][outro]
      amix=inputs=9:duration=longest:normalize=0,
      acompressor=threshold=0.16:ratio=2.3:attack=24:release=240:makeup=1.15,
      alimiter=limit=0.89:attack=6:release=70,
      atrim=0:98.133333[audio]
  " \
  -map "[audio]" -c:a pcm_s24le -ar 48000 -ac 2 "$temporary"

ffmpeg -y -loglevel error -i "$temporary" \
  -af "loudnorm=I=-15.5:LRA=8:TP=-1.2,apad=pad_dur=98.133333,atrim=0:98.133333" \
  -c:a pcm_s24le -ar 48000 -ac 2 "$output"

rm -f "$temporary"

ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_name,sample_rate,channels -of json "$output"
