# Primary-research deterministic projection assessment

Date: 2026-07-11

## Scope

This evaluation covers saved primary-research extraction rows only. No new
extraction, adjudication, or evaluator model calls were used. The candidate was
rebuilt from the existing 57,555 routed evidence rows.

The goal was not to maximize visible graph coverage. It was to recover useful
information from saved extraction while keeping arbitrary extraction wording
out of the overview graph.

## Result

| Metric | Preserved baseline | Candidate | Change |
|---|---:|---:|---:|
| Normalized findings | 42,974 | 47,244 | +4,270 |
| Papers with findings | 8,478 | 9,241 | +763 |
| Held normalization rows | 20,031 | 15,775 | -4,256 |
| Primary overview findings | 36,486 | 39,824 | +3,338 |
| Primary overview edges | 3,567 | 4,106 | +539 |
| Primary overview nodes | 528 | 540 | +12 |
| Degree-one overview nodes | 29 | 27 | -2 |
| Degree-one node rate | 5.5% | 5.0% | -0.5 points |

The candidate therefore recovers 3,338 additional primary findings in the
overview and 763 papers that previously had no normalized finding, while adding
only 12 controlled overview nodes. At the exact saved source-item level, 4,895
previously held rows became findings; 15,127 remained held and 9 could not be
matched after deterministic expansion or filtering.

## Rejected intermediate design

An initial implementation preserved each non-atomic exposure string as its own
node. That was rejected after corpus-level measurement: it produced 9,194
internal entities, including 5,972 degree-one entities (65%). Exact mixtures,
doses, assay wording, and contextual phrases are provenance, not an overview
vocabulary.

The surviving implementation separates the two layers:

- `graph_subject_label` stores the exact extracted exposure for paper detail.
- `graph_overview_subject_label` stores a controlled, intentionally lossy graph
  concept.
- Open-ended molecular readouts, pathways, and intervention components project
  to controlled parent families.
- Unparented labels in those open-ended domains require support from at least
  two studies.
- Subjects that cannot be projected cleanly remain `paper_detail` and do not
  enter the overview.

The final primary payload contains 70 subject nodes and 470 right-side concept
nodes. Every visible node is supported by at least two distinct studies;
multiple findings from a single study count once. Single-study findings remain
in the detail/search payload.

## Conservative holds

The candidate retains 523 findings as paper detail rather than overview edges:

| Reason | Findings |
|---|---:|
| Uncontrolled combination or regimen | 438 |
| Uncontrolled compound class | 38 |
| Specific but unmapped compound-like class text | 26 |
| Structurally identical direction conflict | 12 |
| Primary claim supported only by background/introduction location | 9 |

These rows remain available in `findings.parquet`; they are not discarded.

## Original regression example

For DOI `10.3389/fpsyt.2020.542301`, all 10 normalized findings now use the
controlled overview subject `Chemsex`. The exact extracted definitions remain
on each finding, and there are no Ketamine-subject rows for this paper. PTSD is
therefore connected to the study exposure rather than to ketamine alone.

This is one regression case, not the organizing principle of the projection.
The acceptance decision above is based on the full primary corpus.

## What this evaluation does not establish

These counts measure deterministic representation recovery and graph
presentability. They do not establish paper-level recall of every central
finding, because no new manual paper-level gold assessment was performed here.
The appropriate next evaluation is a blinded sample of primary papers comparing
the overview plus detail bundle with the full text, stratified by domain.
