# Meta-analysis v2 pilot assessment

Date: 2026-07-12

## Decision

The final paper-centered meta-analysis extraction is suitable for a larger
extraction batch, provided that the fail-closed QA and conversion rules remain
in place. It is not suitable for automatic, unreviewed graph promotion.

The extraction itself is substantially more normalizable than the current graph
acceptance rate suggests. The main remaining work is controlled vocabulary and
normalization development, plus review of a small set of statistically or
structurally unsafe results.

## Evaluated run

- Run: `meta_analysis_v2_pilot_100_rerun2`
- Cohort: the same 100 papers used in the original pilot
- Source mix: 50 article-text papers and 50 abstract-only papers
- Model: `gemini-3-flash-preview`
- Batch result: 100/100 requests parsed and validated
- Extraction result: all 50 article-text papers and 47 abstracts yielded at
  least one synthesis result; 3 abstracts correctly reported that no
  quantitative synthesis result was available in the supplied abstract
- Extracted synthesis results: 338

The final run is under
`data/processed/extraction/meta_analysis_v2_runs/meta_analysis_v2_pilot_100_rerun2/`.

## Completeness

The extraction captured 172 article-text results and 166 abstract-only results.
Article-text papers averaged 3.44 results; abstracts averaged 3.32.

| Field or component | Article text | Abstract only |
|---|---:|---:|
| Primary subject area | 172/172 (100%) | 166/166 (100%) |
| Population or system | 172/172 (100%) | 166/166 (100%) |
| Intervention or exposure | 172/172 (100%) | 165/166 (99.4%) |
| Comparator, when non-null | 162/172 (94.2%) | 122/166 (73.5%) |
| Outcome or entity | 172/172 (100%) | 166/166 (100%) |
| Timepoint or window, when non-null | 171/172 (99.4%) | 85/166 (51.2%) |
| Effect estimate | 158/172 (91.9%) | 112/166 (67.5%) |
| Evidence-size details | 109/172 (63.4%) | 36/166 (21.7%) |
| Heterogeneity details | 94/172 (54.7%) | 21/166 (12.7%) |

The lower abstract rates for estimates, evidence size, heterogeneity, and time
windows mostly reflect what abstracts report. When a result statement itself
signaled a comparator, population, or time window, the corresponding dedicated
field was populated in 97.6%, 100%, and 97.0% of cases, respectively.

There were 179 main research questions. At least one synthesis result linked to
170 of them (95.0%). Manual review showed that the missing 5% is mainly caused
by conclusions or broad questions not tied to one result ID, rather than absent
principal estimates.

Assessment extraction was strong when the supplied source contained a textual
signal:

| Assessment | Article text | Abstract only |
|---|---:|---:|
| Risk of bias | 42/42 papers (100%) | 8/9 (88.9%) |
| Certainty or GRADE | 10/10 (100%) | 4/4 (100%) |
| Publication bias | 32/34 (94.1%) | 4/4 (100%) |
| Heterogeneity details | 39/47 (83.0%) | 10/15 (66.7%) |

Heterogeneity is the least complete of these elements. Some source mentions
only state that heterogeneity was assessed or describe it generally, so these
signal-based figures are a conservative test rather than a direct recall score.

## Fidelity to the supplied paper

The principal estimates and interpretations were generally faithful. Examples
that worked especially well include:

- `10.1001/jamapsychiatry.2023.0562`: the main ECT-versus-ketamine estimate,
  sensitivity analysis, response, remission, and dissociative-symptom results
  were kept separate with the correct estimates and heterogeneity.
- `10.4088/jcp.19r12889`: the abstract's MADRS change, response, and remission
  results were represented as three separate estimates.
- `10.1038/s41380-024-02830-z`: the overall psychoplastogen, ketamine, classic
  psychedelic, and time-moderator BDNF results were separated and the null
  findings were preserved.
- `10.1002/jcph.1995`: the abstract's CAPS mean difference, clinically
  significant response, and loss-of-diagnosis estimates were separated.

Automatic numeric tracing found the extracted number in the supplied model
input for:

- 241/247 point estimates (97.6%);
- 220/228 interval lower bounds (96.5%);
- 221/228 interval upper bounds (96.9%);
- 149/153 p values (97.4%); and
- 7/7 standard errors (100%).

The unsupported numeric flags were concentrated in five papers. Two were
p-value formatting mismatches. The substantive cases were:

- `10.1016/j.psychres.2022.114857`, where the model converted reported
  `estimate +/- margin` values into unreported lower and upper bounds;
- `10.1177/0271678x221116477`; and
- `10.1556/2054.2022.00218`, where figure-derived estimates were not present in
  the text supplied to the model.

These results are now held from graph conversion rather than silently used.

The main statistical interpretation problems were limited and detectable:

- three results were marked as supporting even though the extracted interval
  included the null;
- one result used a range across timepoints as a point estimate; and
- one result was labelled as a network result without network structure.

The converter now holds all of these cases.

## Evidence excerpts

The final run produced 599 evidence locators. Of these, 475 (79.3%) contained a
supporting excerpt that matched a contiguous span in the supplied text. This is
an improvement over the original pilot's 71.8%, but it is still the weakest
provenance field.

Most mismatches were shortened text, inserted ellipses, punctuation changes, or
combined clauses rather than different claims. They remain flagged, and written
rows with a non-verbatim excerpt are marked `needs_human_review`. The excerpt
should not be displayed as a verified quote until it passes this check.

## Intrinsic normalizability

The main normalization question is whether a result exposes stable concepts,
not whether today's vocabulary already contains the matching node.

On that basis, the final output is strong:

- every result has an explicit primary subject area;
- nearly every result has a result-specific intervention or exposure;
- every result has an outcome or entity and a population/system value;
- comparator and timepoint are explicit nullable fields rather than being
  hidden in prose;
- effect, interval, p value, evidence size, heterogeneity, analysis role,
  network structure, risk of bias, certainty, and provenance remain separate;
- result-level subject, entity, population, comparator, and domain provenance
  are retained through conversion.

The fail-closed converter wrote 322/338 results (95.3%) into structured
normalization rows. Sixteen results were held. The hold reasons were:

- 8 results with an unsupported point estimate or interval bound;
- 4 results that bundled more than one estimate;
- 3 statistical-direction conflicts;
- 1 non-atomic range used as an estimate; and
- 1 network-labelled result without network structure.

One result had more than one hold reason. These holds reflect genuinely unsafe
or non-atomic results, not missing vocabulary.

Examples of the bundled-estimate problem include:

- `10.1177/02698811261430518`, where drug-use and alcohol-use subgroup
  estimates, and psychotherapy/no-psychotherapy estimates, appeared in one
  result statement; and
- `10.1001/jamapsychiatry.2024.2546`, where psilocybin and LSD headache rates
  were combined while only the psilocybin estimate occupied the structured
  estimate field.

These are now detected and held so one estimate cannot be inherited by multiple
normalized entities.

## Fit to the current graph vocabulary

This is a secondary diagnostic, not the normalization score.

Using the current evidence-table builder, 216 distinct extracted results from
77 papers produced at least one graph claim. The preview contained 292 claims;
the larger claim count reflects endpoint views and repeated projections of some
source results.

Most current-vocabulary losses were predictable:

- generic clinical endpoints such as response, remission, relapse, and
  acceptability;
- broad intervention classes such as psychoplastogens or NMDAR antagonists;
- interventions outside the present psychedelic-compound graph scope;
- brain measures that are retained as metadata rather than graph nodes; and
- safety events that do not yet map to a displayable safety category.

These losses do not indicate that the extraction is difficult to normalize.
The raw labels, estimate, comparator, population, timepoint, and provenance are
preserved, so a revised vocabulary or graph design can normalize them later.

## Changes made during the assessment

- Required explicit nullable population, intervention/exposure, comparator,
  outcome/entity, and time-window fields for every result.
- Required one primary subject area per result.
- Required separate result items for different outcomes or subgroup estimates.
- Tightened statistical-direction instructions for p values and intervals.
- Added network-structure requirements.
- Required contiguous verbatim excerpts and automatic quote verification.
- Removed human-facing schema descriptions from the API request while keeping
  them in the canonical saved schema; this resolved Gemini's full-text
  structured-output rejection.
- Added deterministic normalization of missing markers and locator categories.
- Added source-number, interval-direction, network, atomicity, and linkage QA.
- Added a dedicated meta-analysis converter that preserves synthesis-specific
  statistics and fails closed on unsafe results.
- Preserved heterogeneity, analysis context, network details, evidence counts,
  risk-of-bias summaries, and certainty summaries in normalized tables and
  exportable finding records.

## Recommendation

Proceed with the remaining meta-analysis extraction using the final prompt,
schema, runner, and QA rules. Keep critical QA failures out of graph conversion,
retain non-verbatim excerpts as review-needed provenance, and evaluate future
normalization changes against the structured result fields rather than the
current graph acceptance rate.

Do not promote the full extraction directly to the live graph until the held
results and the intended meta-analysis graph representation have been reviewed.
