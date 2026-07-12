# Paper-centered review relationships v2: 50-paper result

Date: 2026-07-11

## What changed

The review branch was redesigned around one paper relationship bundle per
review. Pre-extraction domain routing is not used. Full-text reviews receive a
whole-paper discovery pass and a paper-level reconciliation pass. Abstract-only
reviews receive one conservative abstract-visible pass. Domains are assigned
after relationships have been identified.

The canonical representation preserves compound classes, combinations,
interactions, contexts, research-landscape relationships, uncertainty, and all
raw anchors. The projection uses relationship nodes whenever an atomic edge
would lose meaning.

## Run completeness

- 50/50 review tasks completed successfully.
- 29 full-text reviews and 21 abstract-only reviews.
- 79 model calls, compared with 186 paper-domain calls in the routed baseline.
- 205 paper relationships produced.
- 162 relationships admitted to the isolated main-graph projection after
  deterministic prominence enforcement.
- 658/658 relationship anchors preserved.
- 50/50 papers have at least one main relationship.
- The active KG was not modified.

The admitted projection contains 69 atomic, 20 class, 17 combination, 22
interaction, 18 context, and 16 paper-topic relationships. Seven model rows
that inconsistently combined `secondary_context` with `main_graph` were
deterministically retained in the paper detail but excluded from the main
projection.

## Manual before-and-after assessment

The same 50 papers and the previously written 101 gold relationships were read
against the new bundles. Ratings use the same `good`, `partial`, and `poor`
scale as the baseline.

| Assessment | Baseline routed graph | Paper-centered v2 |
|---|---:|---:|
| Good | 13 | 35 |
| Partial | 17 | 15 |
| Poor | 20 | 0 |

By source depth:

| Source | Baseline good | V2 good | V2 partial | V2 poor |
|---|---:|---:|---:|---:|
| Full text, n=29 | 7 | 19 | 10 | 0 |
| Abstract only, n=21 | 6 | 16 | 5 | 0 |

Across separate manual dimensions:

- paper relationship capture: 39 good, 11 partial, 0 poor;
- paper-level centrality precision: 43 good, 7 partial, 0 poor;
- normalization/anchor fidelity: 30 good, 20 partial, 0 poor.

## Important improvements

- Ketamine plus lamotrigine remains a combination; lamotrigine is no longer
  stripped from the proposition.
- Class-level papers such as HPPD, long-term psychedelic effects, broad
  psychedelic pharmacology, and serotonergic psychedelics in autism now retain
  their class relationships.
- Bibliometric, funding, disparity, and research-agenda papers receive
  paper-topic or research-landscape relationships rather than fabricated
  efficacy edges.
- Broad chemsex and spirituality reviews retain their real paper identity;
  ketamine or psilocybin remain supporting components rather than replacing the
  paper's scope.
- Mixed, negative, and insufficient conclusions remain explicit relationship
  tones instead of disappearing.
- No paper becomes empty during projection.

## Remaining partial cases

The 15 partial bundles cluster into four problems:

1. Some very broad reviews still promote a few local details too highly,
   particularly the TRD bibliometric and management reviews.
2. Some relationship statements name focal compounds that are represented by a
   broader class anchor rather than an explicit named-compound anchor. These
   are flagged, preserved, and never silently dropped.
3. A few reconciliation outputs express an inconclusive answer mainly as an
   evidence-gap relationship instead of also retaining the explicit mixed or
   insufficient synthesis relationship. The ketamine-lamotrigine human efficacy
   question is the clearest example.
4. Abstract-only papers can still omit details absent from the abstract. These
   are marked for full-text acquisition rather than treated as paper-complete.

The next development pass should target these 15 partial papers, especially
question-to-synthesis completeness and focal-anchor completeness. After that,
the revised branch should be tested on a new disjoint 50-review validation set
before replacing the current review path in the active KG.

## Development repair pass

A source-grounded repair pass was run on the 10 partial full-text bundles. The
repair input contained the original bundle, discovery inventory, automatic QA
flags, and paper centrality evidence. It did not contain manual gold
relationships or manual assessment notes.

All 10 repair calls completed successfully. Each proposed repair was then read
directly against the paper-level gold. Seven were accepted and three were
rejected because they did not improve centrality or added noise. The accepted
repairs improved anchor completeness, explicit question answers, the
MDMA-plus-EX/RP treatment package, and the translational research-agenda
bundle.

After selective repair:

| Assessment | Routed baseline | Initial v2 | V2 development bundle |
|---|---:|---:|---:|
| Good | 13 | 35 | 37 |
| Partial | 17 | 15 | 13 |
| Poor | 20 | 0 | 0 |

The development bundle has 21 good and 8 partial full-text papers, while the
abstract-only stratum remains 16 good and 5 partial. Relationship capture is
now 41 good / 9 partial; centrality precision remains 43 good / 7 partial; and
normalization/anchor fidelity improves to 35 good / 15 partial.

At that stage, the 13 remaining partials divided into eight full-text centrality
problems and five abstract-only information limits. Additional model passes over
the same abstracts could not add unavailable evidence. The later cohort-wide
iterations below supersede the selective-repair result as the pipeline
development path.

## Cohort-wide pipeline iterations

The selective repair result above is not an automatic pipeline score. It used a
manually selected input DOI list and a manually accepted output DOI list. It is
retained only as development history.

The same 50 papers were subsequently rerun from scratch after shared changes to
the schema, prompts, and QA. No DOI-specific instructions, manual output
selection, or gold relationships were supplied to any extraction call.

| Automatic pipeline | Good | Partial | Poor | Full-text good | Abstract-only good |
|---|---:|---:|---:|---:|---:|
| Initial paper-centered v2 | 35 | 15 | 0 | 19/29 | 16/21 |
| Scope roles plus answer facets | 35 | 15 | 0 | — | — |
| Enforced central relationship plan | 35 | 15 | 0 | — | — |
| Facet-linked plan plus automatic QA correction | 37 | 13 | 0 | 22/29 | 15/21 |

The final iteration produced 152 relationships, of which 131 were manually
screened as central candidates and 122 entered the isolated main projection.
All 505 anchors were preserved. It used 123 model calls: the 79-call base path
plus 44 automatic contract-correction attempts. Twenty-one corrections were
accepted because they strictly reduced deterministic QA failures; 23 were
rejected automatically.

Manual dimensions for the final iteration were:

- relationship capture: 41 good / 9 partial;
- paper-level centrality precision: 46 good / 4 partial;
- relationship and anchor fidelity: 44 good / 6 partial.

This is a real cohort-wide improvement, but the branch is not yet ready for
production replacement. Thirty-eight papers still have at least one structural
QA flag. Most are upstream inconsistencies where discovery marks an answer
facet as defining or major-supporting but does not place it in the central
relationship plan. The bundle correction treats the paper frame as
authoritative and therefore cannot repair that upstream defect.

The next development change should separate the gates:

1. validate and, when necessary, retry the discovery frame before
   reconciliation;
2. use bundle correction only for relationship-level violations of an already
   valid frame;
3. preserve the pre-correction bundle so the correction stage can be ablated
   directly;
4. run a correction-disabled comparison before deciding whether the extra 44
   calls justify their cost and regression risk;
5. only then freeze the pipeline and evaluate it on a disjoint 50-review
   validation cohort.

The active KG remains unchanged.
