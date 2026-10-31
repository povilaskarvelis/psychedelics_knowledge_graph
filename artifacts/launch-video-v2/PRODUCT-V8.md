# Product film v8

97.4 seconds · 1920 × 1080 · 30 fps · H.264 / AAC

Composition: `ProductV8`. Source: `src/product-v8/ProductFilm.jsx`. The v7 composition and export are preserved.

## Changes from v7

- Project-name opening and an increasing odometer-style count that stops at 21,735.
- Dedicated, vertically moving compound list after the counter has finished. Papers arrive across fifteen compounds before the camera returns to Ketamine, Psilocybin, and MDMA.
- Shared overview geometry across the opening/drill-down boundary, with no scene crossfade. Selecting Conditions fades other research areas; the Conditions node expands into specific conditions and its existing connections fan out with it.
- No Explore/Analyze navigation tabs.
- “How the studies were done” replaces the comparison claim. Selected-study facets remain distribution summaries, not study-by-study comparisons.
- Added primary-study/review/meta-analysis totals and a stacked annual timeline. The three research-area sparklines now show Safety, Molecular effects, and Real-world use. Author-topic connections and the compound/topic heat map remain.
- Removed the overlapping research-papers footer and revised the author heading to “Researchers and research areas.”
- “Living knowledge synthesis” labels the continuing arrival of new papers.
- A graph output port is visibly wired to the graph's research-area nodes. Animated packets follow the curves from this port to API/MCP.

## Provenance and interpretation

The 21,735 / 16,731 / 4,672 / 332 counts match `normalized_finding_study_count` in the active release manifest under `data/processed/graph_payload_runs/living_update_20260917_author_identity_reviewed/graph_payload_manifest.json`. They describe the normalized-finding literature, not the narrower graph-filtered study count.

The stacked timeline uses the actual Analyze UI series captured in `src/story-data.json`; only complete calendar years 2017–2025 are shown. Source-type segment values sum exactly to each year's total.

Study-context facets, relationships, author-topic counts, momentum series, and matrix data are from the same saved product captures used in v7 (`src/v7-data.json`, `src/v6-data.json`). Counts can overlap across facets or research areas. The 2022–2026 momentum window is ongoing; the video makes no annualized-growth or efficacy claim. Each sparkline retains the product's independent vertical normalization.

Paper icons and programmatic data packets are schematic. Their number is not a per-compound paper count, and their timing does not promise immediate automated ingestion. No screenshots are used as footage.

## Build

```sh
node generate-soundtrack.js --product-v8
npx remotion studio src/index.jsx --no-open
npx remotion render src/index.jsx ProductV8 dist/psychedelics-knowledge-graph-product-v8.mp4 --codec=h264 --crf=17 --pixel-format=yuv420p --concurrency=4 --log=error
```

Uses the existing Remotion 4.0.526 / React 19.3.0 project, official Remotion skills, and locally synthesized audio. No paid media generation or publishing action.
