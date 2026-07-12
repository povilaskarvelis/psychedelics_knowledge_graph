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

## Multi-compound follow-up (2026-07-12)

The primary run was rebuilt again from the same saved extraction array, without
model calls. Multi-valued overview projection now distinguishes three cases:

- exact lists, alternatives, and separate study arms project to each registered
  atomic compound;
- explicit co-administration/formulations project to canonical `A + B` nodes,
  and explicit sequences to `A + B (sequential)` nodes;
- recognized colloquial combination names are inferred deterministically and
  appended in parentheses, including pharmahuasca, candyflipping, and hippy
  flipping;
- broad classes and exposure contexts remain controlled broad nodes only when
  the source itself is nonspecific. Chemsex remains one exposure context.

The exact extraction remains in `graph_subject_label`; the controlled list is
stored in `graph_overview_subjects_json`. This avoids duplicating finding cards
while allowing the graph payload to emit multiple edges.

Corpus-level primary results:

| Projection result | Findings | Distinct papers |
|---|---:|---:|
| Specific compounds separated from multi-compound text | 912 | 378 |
| Specific compounds recovered from class text | 877 | 253 |
| Supported simultaneous combination | 104 | 29 |
| Supported sequential regimen | 25 | 12 |

`Multi-compound exposure` is no longer present in primary findings. The initial
primary overview contains 82 subject nodes and 471 right-side nodes across
4,333 edges; every node still requires two distinct studies. Six specific
combination/regimen nodes survive that presentation threshold: `DMT + Harmine
(pharmahuasca)`, `DMT + Harmaline (pharmahuasca)`, `5-MeO-DMT + Harmaline`,
`LSD + MDMA (candyflipping)`, `Dextromethorphan + MDMA`, and `Ibogaine +
5-MeO-DMT (sequential)`. One-paper combinations remain searchable in detail and
cannot appear after filtering because filtered graphs use the fixed full-view
relationship whitelist.

The same pass fixed nested-name leakage: `5-MeO-DMT` no longer creates an
additional `DMT` subject, and `S-ketamine` no longer creates an additional
`Ketamine` subject unless the broader compound is independently named.

The follow-up also audited the remaining broad psychedelic subjects. An
explicitly predominant compound and a drug-specific assisted-therapy label now
override a broad class projection. This affects 221 saved primary rows from 55
papers. If several compounds are described as predominant, each is projected;
the first is not selected arbitrarily. Examples include:

- `Ketamine-assisted psychotherapy (KAPT), psychedelic approach` → `Ketamine`;
- `Naturalistic psychedelic use (primarily psilocybin)` → `Psilocybin`;
- `Psychedelics and ketamine` → the unresolved mixed/unspecified fallback, not
  `Ketamine`, because the collective exposure is not ketamine-specific.

The ambiguous primary labels were collapsed into one normalized fallback,
`Psychedelics (mixed or unspecified compounds)`. Its 487 findings from 214
papers remain searchable with their exact exposure text, but all are marked
paper-detail-only so the fallback cannot form a visual graph hub or reappear
after filtering. `Serotonergic psychedelics` was renamed `Classic
psychedelics` in the primary presentation. Main finding search now searches all
findings in the active source, independent of the graph domain currently
selected; the graph itself remains domain-specific. The primary graph includes
8,321 of 9,417 extracted primary papers after this presentation hold.
The acceptance decision above is based on the full primary corpus.

## What this evaluation does not establish

These counts measure deterministic representation recovery and graph
presentability. They do not establish paper-level recall of every central
finding, because no new manual paper-level gold assessment was performed here.
The appropriate next evaluation is a blinded sample of primary papers comparing
the overview plus detail bundle with the full text, stratified by domain.
