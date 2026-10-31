#!/bin/bash
# sheet.sh out.jpg cols img1 img2 ...
out=$1; cols=$2; shift 2
n=$#; rows=$(( (n + cols - 1) / cols ))
inputs=(); for f in "$@"; do inputs+=(-i "$f"); done
filter=""; for ((i=0;i<n;i++)); do filter+="[$i]scale=960:-1[s$i];"; done
for ((i=0;i<n;i++)); do filter+="[s$i]"; done
layout=""; for ((i=0;i<n;i++)); do c=$((i % cols)); r=$((i / cols)); layout+="$((c*960))_$((r*540))|"; done
filter+="xstack=inputs=$n:layout=${layout%|}:fill=black"
ffmpeg -v error -y "${inputs[@]}" -filter_complex "$filter" -q:v 3 "$out"
