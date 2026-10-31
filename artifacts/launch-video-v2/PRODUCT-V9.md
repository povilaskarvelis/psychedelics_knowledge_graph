# Product film v9

105.4 seconds · 1920 × 1080 · 30 fps · H.264 / AAC

Composition: `ProductV9`, in `src/product-v9`. Previous compositions and exports are retained.

## Editorial changes

- Paper icons accumulate alongside the increasing counter, with deterministic irregular positions and continuous drift.
- A shared smooth motion carries the paper cloud into compound nodes. Discrete row/batch delays and paper-layer clipping are removed.
- A longer vertical traversal covers 23 compound labels before settling on Ketamine, Psilocybin, and MDMA.
- The title background disappears before the overview appears, fixing the Conditions node/label clipping.
- “Publication types” replaces “Different kinds of research.” Publication types use blue/orange/purple, and research-area trends use orange/blue/pink.
- Research trends are headed “See how research is changing.”
- A hybrid researcher sequence starts with the site's MDMA / post-traumatic stress disorder author list, then opens Rick Doblin's broader research-area connections from his selected row.
- The update scene is now “Updated as new papers arrive”: a paper feed triggers a synchronized refresh of the graph and visualizations in one workspace.
- API/MCP connections start at the graph container boundary. No domain nodes are wired to that output port. The internal graph is centered below its title.

## Researcher data

`capture-v9-authors.cjs` captured `src/v9-authors.json` from the local site preview. The author counts are the Explore panel's distinct-study counts for first/last author roles in the selected MDMA/PTSD evidence. They are labeled **First / last authors** and **Studies**, not influence scores or total career publications.

The displayed rows are Rick Doblin (11), Jennifer Mitchell (4), Elliot Marseille (4), and Michael C. Mithoefer (3), retaining the site's ordering. Rick Doblin's research-area connections were separately captured from Analyze. The graph represents his broader area coverage, not additional MDMA/PTSD counts.

## Other data and schematic motion

All v8 provenance qualifications still apply; see `PRODUCT-V8.md`. The primary/review/meta-analysis totals match the active manifest's normalized-finding study counts. The stacked timeline uses complete years 2017–2025 from the captured Analyze series. Momentum's 2022–2026 window is ongoing.

The small update-scene bars use captured 2018–2025 totals, and its small matrix uses captured compound/area counts. Their refresh highlighting is schematic: no invented new values, efficacy results, citations, or influence measures are presented. Paper icons are not a one-to-one depiction of corpus size or per-compound counts. The update animation is not a claim of instantaneous ingestion.

## Build

```sh
node generate-soundtrack.js --product-v9
npx remotion studio src/index.jsx --no-open
npx remotion render src/index.jsx ProductV9 dist/psychedelics-knowledge-graph-product-v9.mp4 --codec=h264 --crf=17 --pixel-format=yuv420p --concurrency=4 --log=error
```

Official Remotion skills guided the scene organization, frame-driven motion, preview and export workflow. Audio is locally synthesized; no paid services or publishing actions were used.
