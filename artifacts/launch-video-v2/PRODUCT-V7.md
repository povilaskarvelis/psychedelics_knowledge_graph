# Product film v7

88 seconds · 1920 × 1080 · 30 fps · H.264

The composition is `Product` in `src/product/ProductFilm.jsx`. Prior films remain intact.

## Story

- 0–14.6s: psychedelic research, paper volume, compound breadth, papers converging into connected knowledge
- 14.6–37.2s: Explore, compound–condition connections, the Psilocybin / Major depressive disorder selection, study designs, comparators, follow-up
- 37.2–64.3s: Analyze, research-area momentum, researcher–topic connections, compound–topic coverage
- 64.3–73.9s: incoming papers join the graph
- 73.9–82s: programmatic access through API and MCP
- 82–88s: actual project favicon, name, and URL

## Data and treatment

`src/v7-data.json` contains data captured by `capture-v7.cjs` from the local product preview on 2026-09-18. `src/v6-data.json` contains the captured compound / research-area matrix. Reference screenshots in `public/v7` informed the styling but are **not included as footage** in this composition.

The film redraws the product's hollow nodes, curved gradient links, stacked study-context bars, momentum sparklines, and coverage cells as independently animated elements. The layout is adapted for video; it is not an exact UI recording.

Numbers shown for the selected Psilocybin / Major depressive disorder connection are 75 studies, with the captured facet counts. Only selected facet labels are displayed, while the complete captured distribution is represented by the stacked bars. Facet categories and research areas are not necessarily mutually exclusive. This is descriptive coverage, not an efficacy comparison.

Momentum uses the product's 2017–2021 and 2022–2026 windows. The latter is an ongoing window; no annualized growth-rate or projection claim is made. Sparklines follow the product's independently normalized series, not a shared vertical scale. Matrix values are research-paper counts; zero cells are shown as a dash, not as proof that research does not exist.

Paper icons in the opening and living-graph scene are schematic, not a one-to-one rendering of every paper or a claim of instantaneous automatic ingestion. Paper arrival is a visual explanation of adding research to the graph. API/MCP packet motion is similarly schematic.

## Build

Remotion and all associated packages: 4.0.526. React / React DOM: 19.3.0. Official Remotion agent skills were installed and used for scene organization, editable headlines, frame-driven animation, font loading, preview, and rendering.

```sh
node generate-soundtrack.js --product
npx remotion studio src/index.jsx --no-open
npx remotion render src/index.jsx Product dist/psychedelics-knowledge-graph-product-v7.mp4 --codec=h264 --crf=17 --pixel-format=yuv420p --concurrency=4
```

Audio is locally synthesized by the existing project soundtrack generator. No paid generation API or external stock media was used. No posts were published.
