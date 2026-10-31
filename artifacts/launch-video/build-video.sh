#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RAW="${ROOT_DIR}/capture/preview-raw.webm"
ASSETS="${ROOT_DIR}/assets"
BUILD="${ROOT_DIR}/build"
mkdir -p "${BUILD}"

ffmpeg -y \
  -i "${RAW}" \
  -loop 1 -framerate 25 -i "${ASSETS}/caption-1.png" \
  -loop 1 -framerate 25 -i "${ASSETS}/caption-2.png" \
  -loop 1 -framerate 25 -i "${ASSETS}/caption-3.png" \
  -loop 1 -framerate 25 -i "${ASSETS}/caption-4.png" \
  -filter_complex "
    color=c=#030806:s=1080x1080:r=25:d=32.4[bg];
    [0:v]scale=960:600:flags=lanczos,fps=25,setpts=PTS-STARTPTS[screen];
    [bg]drawbox=x=54:y=254:w=972:h=612:color=#2d554a@0.52:t=6[stage];
    [stage][screen]overlay=x=60:y=260:shortest=1[base];
    [1:v]scale=1080:1080,format=rgba,fade=t=in:st=0:d=0.35:alpha=1,fade=t=out:st=4.8:d=0.4:alpha=1[c1];
    [2:v]scale=1080:1080,format=rgba,fade=t=in:st=4.6:d=0.4:alpha=1,fade=t=out:st=7.7:d=0.4:alpha=1[c2];
    [3:v]scale=1080:1080,format=rgba,fade=t=in:st=7.5:d=0.4:alpha=1,fade=t=out:st=20.5:d=0.4:alpha=1[c3];
    [4:v]scale=1080:1080,format=rgba,fade=t=in:st=20.3:d=0.4:alpha=1,fade=t=out:st=31.9:d=0.45:alpha=1[c4];
    [base][c1]overlay=0:0:shortest=1[v1];
    [v1][c2]overlay=0:0:shortest=1[v2];
    [v2][c3]overlay=0:0:shortest=1[v3];
    [v3][c4]overlay=0:0:shortest=1,format=yuv420p[main]
  " \
  -map "[main]" -t 32.4 -an -c:v libx264 -preset medium -crf 18 -movflags +faststart \
  "${BUILD}/main.mp4"

ffmpeg -y -loop 1 -framerate 25 -i "${ASSETS}/title.png" -t 4 \
  -vf "scale=1120:1120:flags=lanczos,zoompan=z='min(zoom+0.00035,1.025)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=100:s=1080x1080:fps=25,format=yuv420p" \
  -an -c:v libx264 -preset medium -crf 18 -movflags +faststart "${BUILD}/title.mp4"

ffmpeg -y -loop 1 -framerate 25 -i "${ASSETS}/end.png" -t 5 \
  -vf "scale=1120:1120:flags=lanczos,zoompan=z='min(zoom+0.00022,1.018)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=125:s=1080x1080:fps=25,format=yuv420p" \
  -an -c:v libx264 -preset medium -crf 18 -movflags +faststart "${BUILD}/end.mp4"

ffmpeg -y \
  -i "${BUILD}/title.mp4" -i "${BUILD}/main.mp4" -i "${BUILD}/end.mp4" \
  -filter_complex "
    [0:v]settb=AVTB,fps=25[v0];
    [1:v]settb=AVTB,fps=25[v1];
    [2:v]settb=AVTB,fps=25[v2];
    [v0][v1]xfade=transition=fade:duration=0.6:offset=3.4[x1];
    [x1][v2]xfade=transition=fade:duration=0.6:offset=35.2,format=yuv420p[out]
  " \
  -map "[out]" -an -c:v libx264 -preset medium -crf 18 -movflags +faststart \
  "${ROOT_DIR}/psychedelics-knowledge-graph-v2-launch-silent.mp4"

ffmpeg -y \
  -f lavfi -i "anoisesrc=color=pink:amplitude=0.045:d=40.2" \
  -f lavfi -i "sine=frequency=98:duration=40.2" \
  -f lavfi -i "sine=frequency=146.83:duration=40.2" \
  -f lavfi -i "sine=frequency=659.25:duration=0.7" \
  -f lavfi -i "sine=frequency=783.99:duration=0.7" \
  -filter_complex "
    [0:a]lowpass=f=1100,highpass=f=70,volume=0.035[n];
    [1:a]volume=0.010[d1];
    [2:a]volume=0.006[d2];
    [3:a]volume=0.045,afade=t=out:st=0:d=0.7,adelay=3400|3400[c1];
    [4:a]volume=0.038,afade=t=out:st=0:d=0.7,adelay=11100|11100[c2];
    [n][d1][d2][c1][c2]amix=inputs=5:normalize=0,afade=t=in:st=0:d=1.4,afade=t=out:st=38.5:d=1.7,volume=28dB,alimiter=limit=0.9[a]
  " \
  -map "[a]" -t 40.2 -c:a aac -b:a 160k "${BUILD}/soundtrack.m4a"

ffmpeg -y \
  -i "${ROOT_DIR}/psychedelics-knowledge-graph-v2-launch-silent.mp4" \
  -i "${BUILD}/soundtrack.m4a" \
  -map 0:v:0 -map 1:a:0 -c:v copy -c:a copy -shortest -movflags +faststart \
  "${ROOT_DIR}/psychedelics-knowledge-graph-v2-launch.mp4"

cp "${ASSETS}/thumbnail.png" "${ROOT_DIR}/psychedelics-knowledge-graph-v2-thumbnail.png"

ffprobe -v error -show_entries format=duration,size:stream=width,height,r_frame_rate,codec_name \
  -of default=noprint_wrappers=1 "${ROOT_DIR}/psychedelics-knowledge-graph-v2-launch.mp4"
