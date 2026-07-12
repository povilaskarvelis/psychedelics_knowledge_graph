# Meta-analysis v2 extraction and normalization assessment

Date: 2026-07-12

## Overall assessment

The extraction worked well enough to use across the eligible meta-analysis
corpus. The results are both substantively useful and structurally suitable for
normalization. The normalization layer has now been revised for meta-analyses,
and the revised build is suitable for the active knowledge graph.

This decision does not mean that every extracted result should become a graph
edge. Results that cannot be mapped safely remain available in paper details,
and results that fail statistical or source-tracing checks remain outside the
normalization input.

## Extraction completed

- Eligible papers: 268
- Article-text inputs: 149
- Abstract-only inputs: 119
- Pilot papers: 100
- Remaining asynchronous batch: 168
- Valid asynchronous responses in the remaining batch: 168/168
- Extracted synthesis results across both runs: 933
- Results accepted by the fail-closed converter: 888
- Papers with an accepted result: 256
- Papers represented by at least one normalized finding: 238

The remaining-batch extraction is in
`data/processed/extraction/meta_analysis_v2_runs/meta_analysis_v2_remaining_168_20260712/`.
The combined converter output is in
`data/processed/extraction/meta_analysis_v2_runs/meta_analysis_v2_complete_268_20260712/`.

Five papers in the remaining batch did not yield accepted results. Four
abstracts did not report an extractable quantitative synthesis. One article
packet contained text for a different paper and was correctly rejected as not
relevant to the supplied metadata.

## Normalization changes

The initial build showed that the extracted results were more normalizable than
the graph was recognizing. It produced 874 findings, represented 215 papers,
and admitted 626 findings to the main graph. Common losses included generic
clinical endpoints, safety events, brain measures, intervention-context
analyses, and compound aliases.

The revised build produces:

- 1,037 normalized meta-analysis findings;
- 238 represented papers;
- 745 findings admitted to the main graph;
- 292 findings retained in paper details;
- no meta-analysis proposition-direction conflicts; and
- 328 remaining normalization audit rows, down from 423.

The largest changes are:

- Clinical results are anchored to the studied condition when the population
  clearly identifies one, while the exact endpoint remains attached to the
  result.
- Response, remission, relapse, discontinuation, acceptability, and symptom
  improvement are now recognized as stable clinical endpoints.
- Brain measurements such as connectivity, mismatch negativity, event-related
  potentials, BOLD, and cerebral blood flow have a dedicated normalized detail
  kind. They remain result context and are not a top-level graph category.
- Meta-regressions and subgroup analyses can retain dosing, comparator, and
  treatment-intensity context without turning the moderator into the treatment.
- More safety outcomes and cognitive measures normalize to controlled labels.
- Compound and condition aliases were corrected where the initial build was
  either too narrow or too broad.
- Proposition grouping now distinguishes outcome, comparator, subject, analysis
  role, subgroup or moderator, sensitivity method, network treatments, metric,
  and dose. This prevents unlike estimates from being treated as duplicates or
  contradictions.

## Completeness and usability

The exported meta-analysis detail payload contains 1,037 findings. Coverage of
the main structured fields is:

| Field | Findings populated |
|---|---:|
| Synthesis design | 1,037/1,037 (100.0%) |
| Result role | 1,037/1,037 (100.0%) |
| Source text depth | 1,037/1,037 (100.0%) |
| Population | 1,037/1,037 (100.0%) |
| Normalized comparator | 979/1,037 (94.4%) |
| Normalized follow-up window | 1,037/1,037 (100.0%) |
| Overall included-study count | 991/1,037 (95.6%) |
| Effect estimate | 802/1,037 (77.3%) |
| Confidence interval | 723/1,037 (69.7%) |
| P value | 499/1,037 (48.1%) |
| I-squared | 385/1,037 (37.1%) |
| Risk-of-bias summary | 528/1,037 (50.9%) |
| Certainty or evidence-strength summary | 162/1,037 (15.6%) |

Synthesis design, comparator, follow-up window, and included-study count are
useful high-level stacked-bar filters. Source depth is already handled
by the shared full-text control, while population and result role remain result
context. Effect estimates and confidence intervals
are sufficiently common and important to display in result details.
Heterogeneity, risk of bias, and certainty remain important, but their reporting
is too sparse for them to function as primary composition filters without
implying that absence means a favorable assessment.

## Right-hand detail panel

The meta-analysis view now has clickable stacked-bar plots for:

- synthesis designs;
- comparators;
- follow-up windows; and
- number of studies included.

These plots use fields that are present for almost all meta-analysis findings
and categories that are meaningful across different clinical and mechanistic
topics. Selecting a segment filters the displayed findings using the same
field represented by the plot.

Individual result cards also show the population, comparator, time window,
effect estimate, p value, included-study count, heterogeneity, subgroup or
moderator, risk-of-bias summary, and certainty when those values were reported.

## Remaining limitations

- Abstract-only papers necessarily contain fewer statistical and assessment
  details than article-text papers.
- A finding may be retained only in paper details when its concept is useful but
  does not support a sufficiently stable graph relationship.
- Non-verbatim source excerpts remain marked for review and are not treated as
  verified quotations.
- Normalization audit rows still provide a useful queue for extending controlled
  vocabularies, but maximizing graph coverage should not override semantic
  accuracy.

## Decision

Use the revised normalized build as the meta-analysis source for the knowledge
graph. Continue to preserve the accepted converter rows and normalization audit
as the stable reprocessing layer so later vocabulary improvements do not require
rerunning the model extraction.
