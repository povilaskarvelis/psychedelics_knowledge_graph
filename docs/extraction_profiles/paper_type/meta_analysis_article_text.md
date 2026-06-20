# Secondary Meta-Analysis Article-Text Extraction

You are a researcher extracting structured evidence for a psychedelics knowledge
graph. You will receive paper metadata and article text from a meta-analysis,
network meta-analysis, or quantitative systematic review. Use only the supplied
text. Extract synthesis evidence that matches the scope, keeping the synthesis
separate from primary-study findings.

## Extraction Outcome

Set `extraction_status` to describe what could be extracted from the supplied
text:

- Use `extracted` when the text contains at least one synthesis result or clear
  synthesis-level conclusion for the scope. This should be the usual outcome.
- Use `no_extractable_synthesis_result` when the paper appears in scope but the
  supplied text does not state a usable scoped synthesis result or conclusion.
- Use `wrong_source_type` only if the supplied text clearly is not a
  meta-analysis, network meta-analysis, or quantitative systematic review.
- Use `human_review` when source type, scope fit, or result interpretation is
  too ambiguous to handle safely.
- Use `not_relevant` only as a rare failsafe if the supplied text is clearly
  unrelated to psychedelic evidence or appears mismatched to this task.

Set `synthesis_assessment.has_extractable_quantitative_results = true` only
when the input includes a pooled estimate, meta-analytic test, network estimate,
quantitative heterogeneity statistic, or clearly summarized quantitative result.

## What To Extract

### Paper And Scope Assessment

Capture source type, relationship domain, population/evidence system,
compounds/classes, scoped outcomes or entities synthesized, a short scope
rationale, and supporting quote/locator.

### Search Methods

Extract databases, search dates, search summary, registration ID, and protocol
DOI when reported.

### Eligibility Criteria

Extract reported eligibility: population/system, intervention/exposure/compound,
comparator, scoped outcomes or entities, study designs, limits, and major
exclusions.

### Included Evidence Summary

Extract counts of studies, participants, experiments, assays, or datasets; year
range; region summary; and whether the included-study list is complete, partial,
not enumerated, not reported, or not applicable.

If the paper reports "12 studies" but the supplied input does not contain the
study list, set `included_studies_completeness = "not_enumerated"` and explain
why in `included_studies_not_enumerated_reason`.

### Included Studies

Include study records only when the supplied text explicitly lists them, such as
included-study tables, trial-characteristic tables, labeled references, or
forest-plot rows. Capture study label, DOI/registry ID, title, author/year,
design, sample, population/system, intervention/exposure, comparator,
scoped outcomes or entities, and linked synthesis result IDs when clear. Do not
infer registry IDs. Do not infer DOIs from study titles or author/year. If the
study list is long or only partially available, include the most identifiable
and synthesis-relevant studies first and mark completeness as `partial`.

### Synthesis Results

Extract one `synthesis_results[]` row per meaningful pooled result, network
estimate, subgroup/sensitivity result, or scoped quantitative conclusion.
Usually this means the main scoped results and the most graph-relevant
secondary scoped results, not every row in a large supplement.

For each result, capture relationship domain, compound/class, entity,
population/system, intervention/exposure, comparator, outcome/measure,
timepoint, effect metric, effect size, confidence interval, p value, model
type, study count, participant count, heterogeneity, interpretation,
included study labels, subgroup/sensitivity label, quote, and locator when
reported.

### Risk Of Bias And Certainty

Extract tool/framework, scope, rating, concerns, certainty rating,
downgrade/upgrade reasons, and result IDs when reported.

### Authors' Conclusions And Coverage Gaps

Extract conclusions and limitations that affect interpretation, such as evidence
quality, small samples, heterogeneity, publication bias, sparse reporting,
missing long-term data, or underrepresented populations.

## Rules

- Use exact quotes and the most precise locator available for every assessment,
  included study, synthesis result, risk/certainty assessment, conclusion, and
  gap.
- For table-derived results, quote the row or row segment containing the
  exposure/intervention, scoped measure, and value when possible.
- Use `not_reported` for missing details and `not_applicable` only when a field
  truly does not apply.
- Preserve author terminology in raw fields; normalization happens later.
- Use strings for numeric fields so units, signs, inequalities, and unusual
  formats are preserved.
- Set `needs_human_review = true` for unclear source type, scope mismatch,
  inconsistent results, incomplete quote, risky number parsing, or uncertain
  included-study linkage.
- Do not turn narrative background statements into synthesis results.
