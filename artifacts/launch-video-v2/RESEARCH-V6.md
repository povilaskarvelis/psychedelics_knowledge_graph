# Research launch film — v6

57 seconds · 1920×1080 · 30 fps · H.264/AAC

## Editorial constraints

- No subtitle lines, secondary explanations, source records, footnotes, circular layouts or “New Analyze” label.
- Explicit text sizes are 48 px or larger at 1080p; no text is placed inside scaled graph groups. Primary messages are 83–200 px.
- Paper motifs use geometric marks, not illegible miniature titles.
- The network travels through 22 real compound names from the site's longer compound list. A single transition focuses the network on three compounds and four research areas. It does not fold back and forth.
- Graph growth is shown with extending branches, not orbiting or flying paper cards.
- Built-in tools lead to research trends and sparse coverage. API/MCP access is shown as graph connections, not a data-record panel.
- The closing screen contains the actual favicon, product name and URL only.

## Data and visual semantics

`capture-v6.cjs` extracts 24 visible compound rows and 240 compound/area counts from the local site's Analyze compound matrix. `v6-data.json` is the captured snapshot. The travelling list omits the very long hydroxynorketamine label and the potentially ambiguous compound abbreviation DOI; it is not presented as exhaustive.

Compound-to-area connections correspond to nonzero cells. The coverage graphic is a selected 4×3 subset of those exact counts. Low counts illustrate sparse coverage in the resource, not proof that no other research exists or a clinical conclusion. Timeline counts come from the previously captured publication-history series in `story-data.json`; the chart ends at 2025, with year labels visible.

Source-branch growth and the compact API/tool graph are schematic motion graphics, not a literal subset of named findings. The three-part Graph/Trends/Coverage dock is an editorial navigation motif for the film, not an exact screenshot or a claim about the site's tab names.

## Build

```sh
node capture-v6.cjs
node generate-soundtrack.js --research
node qa-research.cjs
npx remotion render src/index.jsx Research dist/psychedelics-knowledge-graph-research-v6.mp4 --codec=h264 --crf=17 --pixel-format=yuv420p
```

Earlier versions and unrelated website changes are preserved.
