# V62

Shortens the researcher scene from 330 to 292 frames and scales its animation clock by 330/292, preserving all four author highlights. AnalyticalViews is 732 frames; the film is 2906 frames (96.867 seconds). Default durations remain unchanged for prior compositions.

The researcher/tools crossfade starts at 71.667 seconds and is centered at 71.867 seconds. The guitar half-phrase ends on beat 88 after the reveal, at 71.858 seconds. The visual alignment error is 8.7 milliseconds, less than half a frame at 30 fps. The percussion-emphasis envelope moves from beat 90 to beat 88 without restarting the rhythm. The ending fade shifts earlier by 38 frames.

Audio: `node generate-v56-soundtrack.cjs --aligned-tools`.
Render: `npx remotion render src/index.jsx ProductV62 dist/psychedelics-knowledge-graph-product-v62.mp4 --codec=h264 --crf=17 --pixel-format=yuv420p --audio-codec=aac --audio-bitrate=256k --concurrency=5`.
