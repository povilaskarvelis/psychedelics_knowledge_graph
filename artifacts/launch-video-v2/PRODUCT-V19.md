# Product film V19

1920 × 1080, 30 fps, 2870 frames / 95.67 seconds.

## Opening

- Starts directly with Psychedelic science is growing fast. Removed the opening product-name card.
- Animated annual publication bars show observed growth from 2000 to 2025. The total 21,000+ research papers remains beside the chart, with unpadded rolling digits.
- Removed the molecules/minds/society supporting line.
- Bars dissolve into paper shapes placed within their footprints; paper particles travel into the graph's actual compound/research-area paths.
- Solution heading: We're connecting this research. It states the project's action rather than instructing the viewer.
- Explore the connections still arrives with the first Conditions click.
- All later content, bottom-to-top scroll, quick click timing, and tools-before-updating ending are preserved.

## Data and meaning

Annual data comes from src/story-data.json, captured from the site's Analyze publication chart by prepare-story.cjs. It includes unique papers per year, combining primary studies, reviews, and meta-analyses. The plotted 2000–2025 window uses complete years and excludes partial 2026. It begins at 178 papers in 2000 and ends at 1,806 in 2025, on a zero-based linear axis.

Annual totals for 2010–2025 independently agree with the later capture in src/v13-area-timeline.json. The graph represents the captured corpus, not an exhaustive independent census of all psychedelic publications.

The 21,000+ total is a rounded-down display of the previously captured overall count of 21,735, across the corpus's full timespan. The 2000–2025 annual chart is a subset of that timespan, not a cumulative chart that must sum to 21,000+. No future values, growth forecasts, or smoothed exponential fit are invented.

Paper icons in the transition are symbolic particles, distributed among year-bar footprints in proportion to the observed annual counts. They are not a one-icon-per-paper claim or an assignment of individual papers to compounds.

## Verification

test-v19.cjs validates the count, annual observations, agreement between captured datasets, original compound order and bottom-to-top motion, scene ordering, and total duration. The full-resolution growth layout and successive frames across bars → papers → graph were visually inspected.

Earlier versions remain unchanged.

Final MP4 passed full FFmpeg decode: H.264/AAC, 1920 × 1080 at 30 fps, 95.723 seconds including encoder padding, 20,830,085 bytes.
