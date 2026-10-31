# Product film v11

1920 × 1080, 30 fps, 3366 frames / 112.2 seconds.

## Requested corrections

- Sample sizes is now the fourth right-hand detail panel within “How the studies were done.” The Psilocybin → Major depressive disorder edge, heading and selection total remain fixed. No separate full-screen heatmap, duplicated context header, or numerical color legend.
- Publication types reuse the exact first three colors of the established StudyFacets palette. All study-detail panels import that same palette.
- Research-area trend lines use the same category colors as the graph, looked up by category name.
- Research-area coverage is three horizontal composition bars. Publication-type names are neutral. Removed the mix label and percentage axis. The ten-area legend and segment colors match the main graph.
- Researchers are a three-column network: four overall authors → seven selected compounds → ten research areas. No ranking bars, counts or MDMA/PTSD filter. Each author's actual compound/area connections is emphasized in turn without moving the layout.
- Compound labels are bounded nodes with incoming and outgoing connections anchored to the boundaries, so text does not obscure connections.
- Opening, continuous-updating, API/MCP and outro scenes are unchanged.

## Researcher data

capture-v11-authors.cjs captures the first four entries in the current local Analyze → Authors overview, then uses the site's own focus and relationship summary functions to retrieve each author's compound portfolios and compound-specific area counts.

Authors: Carlos A. Zarate, Robin Carhart-Harris, Matthias E. Liechti, Kenji Hashimoto.

Selection is by the site's indexed first/last-author study activity, not an independently measured citation-impact or influence ranking. There is no numerical rank shown in the film.

The film shows a selected set of seven compounds, not an exhaustive author portfolio. Research-area edges are scoped to the currently highlighted author; they are not fabricated by joining unrelated global compound and author data. Link widths are scaled for readability from source counts.

Sample-size and composition data retain v10 provenance and normalization. The sample-size heatmap contains only observations with a sample size and publication year; the selection total also includes studies lacking these fields.

## Files

- Source: src/product-v11/
- Captured author data: src/v11-authors.json
- Export: dist/psychedelics-knowledge-graph-product-v11.mp4
- Studio: http://localhost:3000/ProductV11

## Validation

- Inspected rendered sample-size context, publication palette, horizontal coverage, trend colors and three author-highlight states.
- Inspected encoded sample-size and researcher frames.
- Full FFmpeg decode passed without errors; H.264/AAC, 1920 × 1080, 30 fps, 112.256 seconds, 26,056,421 bytes.
- Author relationship counts checked for positive values and area counts not exceeding the compound-specific paper counts.
- Soundtrack hash matches v10. Preserved scenes are imported directly from their prior source.
- git diff --check passed.
