# Product film V13

Composition: ProductV13. 1920 × 1080, 30 fps, 3,138 frames (104.6 seconds).

## Revision

- Removed the publication-type overview and its publication-type annual histogram.
- Kept the three publication-type research-area composition bars, using the muted colors captured from the actual Analyze interface.
- Restored the sample-size heatmap to the interface gold, #b89a5b. The selection, heatmap values, and edge context are unchanged.
- Replaced the momentum cards with a progressively revealed stacked research-area timeline for 2010–2025. The legend and colors match the preceding composition view.
- Preserved V12's opening, five-compound graph formation, and continuous selected-edge transition, plus the researcher graph, updating sequence, API/MCP scene, and outro.
- Retimed the synthesized soundtrack for the shorter edit.

## New timeline data

Run capture-v13.cjs against the local site on port 8012 to regenerate src/v13-area-timeline.json.
Data are taken from Analyze with no compound/topic selection, combining primary studies, reviews, and meta-analyses. For each year and each research area, papers are deduplicated with the site's uniqueStudyCount and classified with claimMatchesEntityViewOption.

Band thickness represents the area's share of all research-area assignments within that year, matching the denominator of the preceding concentration view. A paper can contribute to more than one area; these are not mutually exclusive shares of papers. The chart depicts changing research composition, not absolute publication volume or evidence quality.

2010–2025 uses complete calendar years and excludes partial 2026. Cubic boundaries share control coordinates across bands, interpolate between annual observations, and do not cross. Colors are the site's CATEGORY_COLORS, not the brighter graph-node palette.

## Timeline

- 0:00 — Papers and connected knowledge
- 0:24 — Conditions, study designs, comparators, follow-up, sample sizes
- 0:51.6 — Where research is concentrated
- 0:59.2 — Research-area composition over time
- 1:08.8 — Researchers and topic connections
- 1:19.4 — Updated as new papers arrive
- 1:30 — API and MCP
- 1:38.6 — Product identity

## Export

Run: npx remotion render src/index.jsx ProductV13 dist/psychedelics-knowledge-graph-product-v13.mp4 --codec=h264 --crf=17 --pixel-format=yuv420p --concurrency=4

Earlier compositions and exports remain unchanged.

Validation: sampled full-resolution renders of the sample-size, concentration, and timeline views; sampled encoded frames across the concentration-to-timeline transition; removed heading overlap with sequential title fades and checked the transition again; all ten colors checked against captured interface values; all annual counts validated; final export passed full FFmpeg decode. Export is H.264/AAC, 1920 × 1080 at 30 fps, 104.661 seconds including encoder padding, 30,990,742 bytes.
