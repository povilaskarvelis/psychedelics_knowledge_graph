# Product V24

1920×1080, 30 fps, 2,794 frames (93.13 seconds), silent.

- Extended the opening curve to (1745, 250), 110 px right and 115 px above the previous tip. It clears the tallest bar's top at y=314.5.
- Bars finish at frame 118. Arrow continues to frame 140; arrowhead appears at frames 140–146. An ease-in/out draw keeps visible motion after the bars settle.
- Closing update heading changed to “Always stay up to date”.
- Existing counter position, data, hatched estimate, scene durations and other visuals unchanged.

Preview: http://localhost:3000/ProductV24

Export: dist/psychedelics-knowledge-graph-product-v24.mp4

Validation: node test-v24.cjs, opening/closing still checks, final stream metadata and full decode.
