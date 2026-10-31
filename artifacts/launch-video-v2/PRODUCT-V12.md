# Product film v12 — graph formation and continuous detail motion

1920 × 1080, 30 fps, 3366 frames / 112.2 seconds.

## Changes

- The 560 illustrative paper marks now travel to positions along real compound–area connections. Each paper contracts into a colored point; edge segments grow outwards, and endpoint nodes and labels emerge afterward.
- Removed the four repeated paper icons per compound and the pre-existing compound nodes during paper arrival.
- The graph forms before the longer compound list scrolls. The camera returns to five overview compounds: Ketamine, Psilocybin, MDMA, LSD and DMT.
- The final overview and the first frame of the conditions drill-down use matching geometry. The five compounds remain through the condition expansion, then other compounds fade when Psilocybin / Major depressive disorder is selected.
- Source-label alignment no longer changes halfway through its movement.
- The selected condition label reflows continuously: its second word moves below the first phrase before moving left. Labels move clear of their nodes before the edge translates into its detail-panel position.
- Reused all v11 analytics, palettes, author graph, living-update animation, API/MCP scene, outro and soundtrack.

## Data and visual semantics

Graph connections and widths are derived from the existing v6 broad-area data and v7 condition-edge data. The paper marks and their travel paths are illustrative; they are not a claim that each compound has the same number of papers, or that 560 icons represent 560 specific publications.

The original 21,735 corpus count, close-up-to-wide paper camera and long compound list remain. No live data or production site files were edited.

## Checks

- Visually inspected dispersed papers, formation, formed graph, compound-list traversal, five-compound overview, label reflow and final study-details panel.
- Compared frames 719 and 720 across the scene handoff: red and green channels identical, aggregate PSNR 116 dB (negligible blue-channel cursor difference).
- Condition-label prefix spacing measured from the actual Space Bold font; no mid-animation text-anchor or single-line/two-line conditional switch.
- Inspected the encoded formation and detail frames. Full FFmpeg decode passed without errors.
- Verified H.264 / AAC, 1920 × 1080, 30 fps, encoded duration 112.256 seconds, 32,224,738 bytes.
- Confirmed data-backed area connections for all five overview compounds and passed git diff --check.

## Output

dist/psychedelics-knowledge-graph-product-v12.mp4

Preview: http://localhost:3000/ProductV12
