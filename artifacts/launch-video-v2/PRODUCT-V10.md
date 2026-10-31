# Product film v10

1920 × 1080, 30 fps, 3366 frames / 112.2 seconds.

## Changes

- Paper count and paper-world camera share the same easing: a six-times close-up pulls back to reveal a 560-paper field. Icons are illustrative, not a one-to-one paper count.
- Added a large sample-size-by-publication-year heatmap after study designs, comparators and follow-up.
- Publication types now share a muted green / ivory / dusty rose palette throughout the charts.
- Added three vertical publication-type columns, each stacked by its mix of all ten research areas, using the site's native area colors. Framing: “See where research is concentrated.” This shows distribution, not a claim that every low-volume area is a research gap.
- Simplified researcher rows, retained relative study activity and the selected author's actual area connections, and changed the heading to “See who’s driving the research.”
- Removed the “Research papers by topic” matrix sequence.
- Imports Living and Access directly from v9: their content and animations are unchanged.

## Data and interpretation

capture-v10.cjs reads the current local website DOM into src/v10-sample.json and src/v10-areas.json.

The sample chart is the current Psilocybin → Major depressive disorder selection. Its 27 non-empty cells contain 55 study/sample-year observations. It retains the site's bins and deduplication semantics; not all 75 studies in the selection have usable sample sizes and publication years.

Research-area counts are distinct papers within each area and publication type. A paper can appear in more than one area. Each column normalizes its area assignments to 100%, matching the first Analyze overview chart's denominator. These are research-area mixes, not mutually exclusive percentages of all papers. Data were captured from the default Analyze overview across all paper types and animated as vertical columns for the film.

Author activity remains the site's first/last-author study counts within MDMA / post-traumatic stress disorder. It is not a citation-based influence ranking. The network shows the selected author's broader research-area connections.

Annual publication history uses complete years 2017–2025. Topic momentum retains the existing 2017–2021 and 2022–2026 windows; 2026 is ongoing. Sparklines are independently normalized, not a common numerical y-axis.

## Timeline

- 0:00 — Identity, rising count, camera pullback, compound list, connections
- 0:24 — Conditions and study details
- 0:45 — Sample sizes by publication year
- 0:51.6 — Publication types and annual history
- 1:01.2 — Publication types across research areas
- 1:08.8 — Changing research activity
- 1:16.4 — Researchers and topic connections
- 1:27 — Updated as new papers arrive
- 1:37.6 — API / MCP
- 1:46.2 — Product identity

## Output

dist/psychedelics-knowledge-graph-product-v10.mp4

Preview: http://localhost:3000/ProductV10

## Validation

- Inspected rendered close/wide opening frames, graph/Conditions handoff, sample-size reveal and full heatmap, publication-type colors, research-area composition, and researcher connections.
- Inspected encoded frames for the final research-area columns and preserved updating scene.
- Full FFmpeg decode completed without errors.
- Export verified as H.264 / AAC, 1920 × 1080, 30 fps; encoded duration 112.256 seconds, 25,553,355 bytes.
- git diff --check passed.
