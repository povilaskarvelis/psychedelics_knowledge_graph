# Product film V17

1920 × 1080, 30 fps, 2,946 frames / 98.2 seconds.

## Changes

- The rolling paper count begins at one digit and introduces each new digit only as needed. Thousands separator appears at four digits. No reserved leading zeros; the counter grows symmetrically around its center and finishes at 21,735.
- Bottom-to-top viewport movement retains the original compound order. Its duration is now 164 frames / 5.47 seconds, down from 296 frames / 9.87 seconds. A symmetric cubic easing accelerates through the middle and decelerates into the five-compound overview.
- Opening shortened by 132 frames, with its selection cursor and following scene brought forward by the same amount.
- Heading changed to See how the studies were done, sized to remain on one line.
- Sample sizes now lasts 150 frames / 5 seconds instead of 210 frames / 7 seconds.
- Closing sequence is now tools → updated as new papers arrive → product identity.
- Soundtrack regenerated against the revised sequence and duration.

## Scene starts

- 0:00 Opening
- 0:19.6 Study context and methods
- 0:40.6 Sample sizes (within study context)
- 0:45.2 Research concentration
- 0:52.8 Changing research composition
- 1:02.4 Researchers
- 1:13 Connect the graph to your tools
- 1:21.6 Updated as new papers arrive
- 1:32.2 Product identity

## Verification

test-v17.cjs checks original order, bottom-first viewport, monotonic motion, acceleration/deceleration, exact final positions, 1/2/3/4/5-digit progression, final count, scene order, and total frames.

Rendered and visually checked the counter at each digit length, successive scroll positions, and the expanded methods heading. Earlier compositions and exports are preserved.

Final export passed full FFmpeg decode: H.264/AAC, 1920 × 1080 at 30 fps, 98.261 seconds including encoder padding, 26,057,176 bytes.
