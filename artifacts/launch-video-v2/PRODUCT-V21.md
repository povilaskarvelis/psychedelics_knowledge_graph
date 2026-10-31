# Product V21

Revision of V20; 1920×1080, 30 fps, 2,822 frames (94.07 seconds).

- Removed all audio from the composition; export should contain only a video stream.
- Opening year label is now simply “2026”. The observed portion remains solid, the estimated increment remains hatched, and the endpoint retains “~2,100”.
- Added a frame-driven curved upward arrow above the annual bars. It is a directional cue, not a fitted data series.
- Formation heading: “We’ve connected this research”.
- First-click and Conditions heading: “Explore how research interconnects”.
- Research-area timeline now extends through observed 2026 data: 1,441 papers, ten research areas. Its existing 2010–2025 data and palette are unchanged.
- Timeline reveal reduced from 142 to 94 frames (about 34% shorter); scene reduced by 48 frames to preserve the existing hold time.
- Other sequence timing, data, palettes and visuals are preserved from V20.

The 2026 estimate still extrapolates the 2021–2025 compound annual growth rate for one year and rounds to the nearest hundred. It is not an observed full-year total or a validated forecast. The overall 21,000+ count is unchanged and is not increased by the projection.

Preview: http://localhost:3000/ProductV21

Export: dist/psychedelics-knowledge-graph-product-v21.mp4

Checks: node test-v21.cjs; opening and exploration rendered for layout review; final media streams and decode checked separately.
