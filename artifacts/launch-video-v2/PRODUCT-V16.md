# Product film V16

Corrects the interpretation of the opening scroll. The compound order is restored, not rearranged.

- Ketamine, Psilocybin, MDMA, LSD, and DMT remain the first five entries.
- Papers form the graph while the viewport is at the bottom of the full 23-compound list: Methylone, Dextromethorphan, Nitrous oxide, DOM, Noribogaine.
- The viewport scroll offset decreases monotonically from 2340 to zero during frames 282–578. Thus the camera travels toward the top of the list while rows move downward on screen.
- At zero offset the first five entries occupy their existing overview positions and the camera stops. No reversal, reordering, or extra repositioning occurs.
- Formation particles target the initially visible bottom entries' actual research-area edges.
- V15's revised headings, tighter count-to-formation timing, soundtrack, and all subsequent scenes are unchanged.

Composition ProductV16: 1920 × 1080, 30 fps, 3138 frames / 104.6 seconds.

Verification: test-v16.cjs evaluates the actual layout declarations and position expressions, checking original order, bottom-five initial viewport, monotonic direction at every frame, and exact first-five final positions. The opening motion render was inspected at successive points across formation and bottom-to-top traversal.

Export: dist/psychedelics-knowledge-graph-product-v16.mp4. Full FFmpeg decode passed; H.264/AAC, 1920 × 1080, 30 fps.
