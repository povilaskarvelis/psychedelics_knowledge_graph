# Product film V20

1920 × 1080, 30 fps, 2,870 frames / 95.67 seconds. Earlier versions are preserved.

## Changes

- Removed Papers per year, y-axis labels, and gridlines from the opening.
- Kept annual bars, sparse year labels, two endpoint counts, and the rolling 21,000+ overall count.
- Added 2026 with a clearly marked full-year projection. The observed part is solid, while the forecast increment is hatched. Label: 2026 projected.
- Graph-formation heading: A connected map of the research.
- First-click and condition-exploration heading: See relationships across studies.
- These lead into the retained sequence of study methods, research concentration, changing research composition, researchers, tools, and continuous updating.
- Separated Conditions and individual condition-label fades to remove overlapping text during the split.

## 2026 projection

The capture contains 1,441 observed 2026 papers. The release metadata gives a build timestamp but not a verified literature-search cutoff, so the projection does not annualize the partial count against the release date.

Instead, it extrapolates the 2021–2025 compound annual growth rate for one year:

2025 papers × (2025 papers / 2021 papers)^(1/4), rounded to the nearest 100.

Inputs: 997 papers in 2021; 1,806 in 2025. The rounded result is approximately 2,100 for 2026. This is an illustrative trend extrapolation, not a validated forecast or observed count. The existing overall 21,000+ count is not increased to include projected papers.

Particle origins use observed annual counts only. The projected segment fades with the chart rather than supplying imaginary future papers to the graph.

## Validation

test-v20.cjs checks original compound order, camera direction and endpoint, digit progression, scene duration and order, 27 observed annual entries, cross-capture agreement, projection calculation, observed/projected visual split, removed axis labels, and matching exploration heading across the scene boundary.

Full-resolution stills inspected for the simplified histogram, projected segment, formation heading, and exploration heading.

Final export passed full FFmpeg decode: H.264/AAC, 1920 × 1080 at 30 fps, 95.723 seconds including encoder padding, 20,744,920 bytes. The corrected Conditions-label transition was also checked in the encoded MP4.
