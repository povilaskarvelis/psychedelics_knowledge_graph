# Launch film v5

70 seconds, 1920×1080, 30 fps, H.264 + AAC. Local Remotion rendering; no paid generation service or stock assets. Earlier cuts are preserved.

## Editorial changes

- Faster centered opening: psychedelic research, then 21,735 research papers.
- A 144-paper wall contracts into compound-linked paper nodes. The network continues across scenes rather than being replaced by feature cards.
- Connections span six compounds and ten research areas. Two highlighted source nodes expand into real paper records, without a separate psilocybin example.
- Incoming paper cards shrink into nodes, pulse on arrival and draw connections. This is a schematic of updates, not a claim that ingestion happens instantly or without curation.
- The network changes layout before the Analyze sequence: publication history, research-area distribution and a study/review comparison.
- The AI section connects the visual graph to readable structured paper fields. This is an editorial representation of structured data, not an exact API response schema or a filmed tool call.
- Existing favicon and closing identity retained. No update-date slide or coverage-count cards.

## Provenance

`story-data.json` contains the 144 sampled real papers, compound/topic connection styles, and yearly series from the site. Paper-to-compound connections use the compound matched in each paper title. The film's graph is an illustrative subset, not a complete quantitative rendering of all 21,735 papers.

`motion-data.json` was extracted from the local site's unfiltered Analyze overview using `capture-motion.cjs`. Area counts and primary/synthesis counts are copied directly from the rendered controls and chart accessibility labels. Areas are nonexclusive. The study/review scatter plot preserves the product's logarithmic axes. Publication history shows complete years 2000–2025.

## Reproduce

```sh
node capture-motion.cjs
node generate-soundtrack.js --motion
node qa-motion.cjs
npx remotion render src/index.jsx Motion dist/psychedelics-knowledge-graph-motion-v5.mp4 --codec=h264 --crf=17 --pixel-format=yuv420p
```

Visual QA includes representative frames and final encoded frames, including source-link origins, safe bounds and readable chart labels. The export is checked with ffprobe and a full ffmpeg decode.
