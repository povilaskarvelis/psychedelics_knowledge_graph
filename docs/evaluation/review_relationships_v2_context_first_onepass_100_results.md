# Context-first one-pass review extraction: two 50-paper comparisons

## Test

The context-first prompts were run on both existing 50-review cohorts:

- original 50: 29 full-text and 21 abstract-only reviews;
- second 50: 29 full-text and 21 abstract-only reviews.

Every paper used one model call. The full-text call received the complete
available review and returned the final relationship bundle directly. The
abstract-only call received the title and abstract and returned the same final
bundle format. No second selection call, correction call, evaluator model, or
graph update was used.

The exact prompts, schema, task list, model settings, and hashes are archived
inside each run directory.

I compared every new result manually with the existing source-derived
relationship summary and the previous best result for that paper.

## Overall result

| Measure | Previous two-pass versions | Context-first one-pass | Change |
|---|---:|---:|---:|
| Papers rated good | 75/100 | 77/100 | +2 |
| Papers rated partial | 25/100 | 23/100 | -2 |
| Papers rated poor | 0/100 | 0/100 | 0 |
| Model calls | 158 | 100 | -58 (-36.7%) |
| Total tokens | 1,702,221 | 1,283,955 | -418,266 (-24.6%) |
| Extracted relationships | 402 | 413 | +11 |
| Main-graph relationships | 370 | 404 | +34 |

Across the paired paper comparisons, 11 papers improved, 9 regressed, and 80
were unchanged.

## Results by cohort

| Cohort | Previous | One-pass | Improved | Regressed | Calls | Token change |
|---|---:|---:|---:|---:|---:|---:|
| Original 50 | 42 good / 8 partial | 41 good / 9 partial | 3 | 4 | 79 to 50 | 909,137 to 701,731 (-22.8%) |
| Second 50 | 33 good / 17 partial | 36 good / 14 partial | 8 | 5 | 79 to 50 | 793,084 to 582,224 (-26.6%) |

The original cohort did not improve, while the second cohort improved by three
papers. The combined gain is therefore modest and not uniform across samples.

## Full text and abstract only

| Cohort and source | Previous good | One-pass good |
|---|---:|---:|
| Original full text | 23/29 | 22/29 |
| Original abstract only | 19/21 | 19/21 |
| Second full text | 20/29 | 20/29 |
| Second abstract only | 13/21 | 16/21 |

The clearest quality improvement occurred in the second set of abstract-only
reviews. Full-text quality was essentially unchanged: one fewer good paper in
the original cohort and no change in the second cohort.

## Improvements

The context-first prompts recovered several previously missing or underweighted
relationships:

- the balanced conclusion of the expectancy and unblinding review;
- placebo-controlled trial scarcity in the ketamine-anhedonia review;
- brain-entropy and personality predictors in the psychedelic-personality
  review;
- the gap-setting purpose of the psychedelic medicalisation review;
- historical context in the psilocybin review;
- rapid antisuicidal benefit in the broad ketamine review;
- named treatment results in the military and veteran review;
- the proposed status and timing of ketamine plus trauma-informed
  psychotherapy;
- weak study quality and missing long-term safety evidence in the palliative
  ketamine review.

These gains came without a second model call.

## Regressions

The main regressions were different omissions or shifts in importance:

- uncertain longer-term MDMA harms were stated too confidently;
- local neurotransmitter and clinical examples were overpromoted in a broad
  self-awareness review;
- psilocybin treatment was overpromoted within a spirituality-centered review;
- cognitive impairment was omitted from a long-term ketamine-abuse review;
- oxygen and injected triptans were omitted from the main acute
  cluster-headache treatment comparison;
- mixed personality and creativity findings disappeared from the psychedelic
  afterglow review;
- a plausible plasticity explanation was stated too causally;
- the ERP review lost its analgesic and broader clinical interpretation;
- the mescaline review lost its indigenous-to-modern treatment proposal and
  legal-cultural context.

## Important limitation: main-graph inflation

The new version selected nearly every extracted relationship for the main
graph:

- original 50: 204 of 208 relationships;
- second 50: 200 of 205 relationships.

The previous versions selected 186 of 201 and 184 of 201, respectively.

The one-pass version therefore improved or preserved paper-level coverage while
becoming less selective about what enters the main graph. This is important for
the actual knowledge graph: a paper can receive a good overall rating while
still exposing too many supporting relationships as central.

## Interpretation

The second full-text call is not required to preserve overall paper quality.
Removing it reduced calls by 36.7% and tokens by 24.6%, while the combined
manual result changed from 75 to 77 good papers.

This report records the evaluation result at the time of the test. After review
of the paper-level outputs and the efficiency gain, this exact one-pass prompt
and schema were promoted to the production review path. The somewhat broader
main-graph output was accepted as an appropriate tradeoff.

## Files

- Production full-text prompt, unchanged from the tested candidate:
  `docs/extraction_profiles/review_relationships_v2/full_text_extraction.md`
- Production abstract-only prompt, unchanged from the tested candidate:
  `docs/extraction_profiles/review_relationships_v2/abstract_extraction.md`
- Original-cohort run:
  `data/processed/extraction/review_relationship_runs/review_relationships_v2_old50_context_first_onepass/`
- Second-cohort run:
  `data/processed/extraction/review_relationship_runs/review_relationships_v2_validation50_context_first_onepass/`
- Paper-by-paper assessment:
  `data/processed/evaluation/review_relationship_context_first_onepass_100_20260711/manual_paired_assessment.csv`
