# Revised paper-first review extraction: second 50-paper test

## Test

The revised prompt and schema were run on the same second 50-review validation
set used for the preceding paper-first test:

- 29 full-text reviews;
- 21 abstract-only reviews;
- 79 model calls: two for each full-text paper and one for each abstract-only
  paper;
- no retry or correction calls;
- no change to the active graph.

I compared every new bundle manually with the source-derived paper summary and
with the preceding extraction for the same paper. No evaluator model was used.

## What changed

The prompts were rewritten rather than extended with additional instructions.
The new version:

- asks directly for the paper's scope and final relationships instead of
  asking the model to create and later match outline IDs;
- adds one evidence label to every relationship: supported synthesis,
  preliminary or mixed evidence, hypothesis or proposal, research gap, or
  descriptive relationship;
- tells the model to make its wording match that evidence label;
- tells bibliometric papers to describe patterns in the literature rather than
  treat topic names as scientific evidence;
- tells the model to retain named treatments when a small evidence set gives
  them different results or levels of certainty;
- retains the existing number of model calls.

The schema was simplified in parallel. The linked outline objects were removed,
and the paper description now contains only the paper's objective, design,
subjects, supporting examples, populations, and source completeness.

## Results

| Measure | Previous version | Revised version | Change |
|---|---:|---:|---:|
| Papers rated good overall | 33/50 | 26/50 | -7 |
| Papers rated partial overall | 17/50 | 24/50 | +7 |
| Papers rated poor overall | 0/50 | 0/50 | 0 |
| Relationship coverage rated good | 38/50 | 37/50 | -1 |
| Selection of important relationships rated good | 44/50 | 37/50 | -7 |
| Evidence wording rated good | 40/50 | 39/50 | -1 |
| Full-text papers rated good | 20/29 | 16/29 | -4 |
| Abstract-only papers rated good | 13/21 | 10/21 | -3 |
| Total tokens | 793,084 | 767,106 | -25,978 (-3.3%) |
| Extracted relationships | 201 | 231 | +30 |
| Relationships selected for the main graph | 184 | 193 | +9 |

In the paired paper comparison, 8 papers improved, 12 regressed, and 30 were
unchanged.

The simpler schema reduced tokens slightly, but the model returned more
relationships. The extra coverage did not translate into better paper-level
selection.

## What improved

The evidence labels fixed several real errors:

- the personality review now includes brain entropy, posterior-cingulate
  findings, and the proposed therapeutic interpretation;
- the computational ketamine explanation is now stated as a proposal rather
  than an established causal mechanism;
- the ketamine-plus-psychotherapy package and its 24-to-48-hour timing are now
  stated as a proposal;
- the palliative ketamine review now makes the weak study base and lack of
  long-term safety evidence central;
- the historical psilocybin abstract now retains its historical context while
  qualifying the early clinical evidence.

These are meaningful improvements achieved without another model call.

## What did not improve

### Importance and graph selection became less reliable

The model assigns both an importance label and a graph decision. Those two
answers contradicted each other for 18 relationships across 16 papers:

- 15 relationships labelled paper-defining or major supporting were excluded
  from the main graph;
- 3 relationships labelled secondary context were included in the main graph.

This removed important qualifications or conclusions in papers about
expectancy, cognitive effects of ketamine, intimacy, palliative care, health
behaviour change, and other topics. Asking the model for the same decision in
two fields adds inconsistency without adding information.

### The supported-evidence label is still too permissive

The model sometimes treats a positive statement in a review as a supported
synthesis even when the underlying evidence is weak. Examples include:

- herbal treatments for opioid withdrawal;
- MDMA clinical efficacy inside a bibliometric review;
- human psilocybin findings based on small uncontrolled chronic-pain reports;
- MDMA-assisted PTSD benefit in an abstract that emphasizes unblinding and the
  FDA decision.

The prompt distinguishes the labels, but it does not yet give a strict rule for
what takes precedence when positive author wording conflicts with weak study
design.

### More extracted relationships sometimes displaced the paper's point

The revised output added mechanistic details, individual treatment findings,
or route comparisons in several papers while dropping or demoting the main
qualification, recommended treatment timing, or research need. This affected
both full-text and abstract-only papers, so it is not only a source-availability
problem.

## Recommended next revision

The next change should still use the same model calls. It does not require a new
stage.

1. Remove the model-generated graph decision. Derive it from the final
   importance label: paper-defining and major-supporting relationships enter the
   main graph; secondary and peripheral relationships remain paper detail.

2. Make the importance test stricter. A major-supporting relationship should be
   one whose removal would materially change or misstate the paper's main
   conclusion. The main graph should be the smallest set that preserves the
   paper's objective, principal results, and necessary qualifications.

3. Give weak evidence priority over positive wording. Case reports, small
   uncontrolled or open-label studies, retrospective self-report, heterogeneous
   results, and explicitly inconclusive findings must be labelled preliminary
   or mixed unless the relationship is only a descriptive research pattern.

4. Require a final check inside the same response: every explicit qualification
   attached to a principal result must appear either in that relationship's
   wording or as a separate major-supporting relationship.

5. For bibliometric reviews, allow clinical efficacy in the main graph only if
   the paper separately synthesizes clinical evidence. Topic clusters and
   research themes remain descriptive literature relationships.

These changes address the observed failures directly and should reduce output
rather than add cost. A targeted rerun of the 20 to 25 papers that exposed these
problems would be the efficient next test before another full 50-paper run.

## Files

- Revised full-text discovery prompt:
  `docs/extraction_profiles/review_relationships_v2/full_text_discovery.md`
- Revised full-text final prompt:
  `docs/extraction_profiles/review_relationships_v2/full_text_reconciliation.md`
- Revised abstract-only prompt:
  `docs/extraction_profiles/review_relationships_v2/abstract_extraction.md`
- Revised schemas:
  `schema/review_relationships_v2.discovery.schema.json` and
  `schema/review_relationships_v2.bundle.schema.json`
- Run:
  `data/processed/extraction/review_relationship_runs/review_relationships_v2_validation50_direct_contract/`
- Manual paper-by-paper comparison:
  `data/processed/extraction/review_relationship_runs/review_relationships_v2_validation50_direct_contract/evaluation/manual_direct_contract_comparison.csv`
