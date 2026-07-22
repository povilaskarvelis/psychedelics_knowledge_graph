# Primary Study Abstract Extraction

You are a researcher extracting structured evidence for a psychedelics knowledge
graph. You will receive a paper title, abstract, and metadata for a primary
study. Extract original empirical findings that match the scope; do not infer
omitted methods, sample sizes, doses, timepoints, secondary details, or
statistics.

Descriptive, qualitative, observational, negative, and null findings are still
original empirical evidence when the abstract explicitly reports them. Do not
require a p-value or effect size when the result itself is stated.

## Extraction Outcome

Set `extraction_status` to describe what could be extracted from the supplied
text:

- Use `extracted` when the abstract contains at least one original finding for
  the scope. This should be the usual outcome.
- Use `no_extractable_scoped_evidence` when the paper appears in scope but the
  abstract does not state a usable scoped finding.
- Use `wrong_source_type` only if the supplied text clearly is not a primary
  study.
- Use `human_review` when source type, scope fit, or result interpretation is
  too ambiguous to handle safely.
- Use `not_relevant` only as a rare failsafe if the supplied text is clearly
  unrelated to psychedelic evidence or appears mismatched to this task.

For any status other than `extracted`, add one short reason to `warnings`. If no
scoped finding is extractable, keep `items` empty.

Do not use `no_extractable_scoped_evidence` merely because the abstract gives a
compact conclusion without detailed statistics.

## What To Extract

Create zero to a few items for the main findings that fit the scope. The item
should represent a direct relationship between the psychedelic compound,
exposure, or intervention and the specific evidence scope. When stated, capture:

- population, sample, experimental system, or setting
- compound, exposure, intervention, comparator, dose, and timing
- scoped outcome, entity, variable, measure, or readout
- when the finding was measured or assessed, such as acute session,
  post-dose, end of treatment, or follow-up
- reported result, interpretation, and concise finding summary
- quantitative values, effect estimates, rates, counts, or compact reported
  statistical support when it helps interpret the finding
- location or locator when available

Do not try to reconstruct methods, tables, subgroup results, full result lists,
or secondary analyses from an abstract.

## Rules

- Use the exact token `not_reported` for missing details and `not_applicable`
  only when a field truly does not apply.
- Controlled vocabulary fields must use their stated meaning, not the nearest
  available label. If the exact administration route or session context has no
  dedicated label, use `other` (or `not_reported` when it is not stated).
  Inhaled gas is not `intranasal`, and a laboratory task completed by human
  participants is not a `preclinical_experiment`.
- Do not force a molecular readout into the closest biological-process family.
  Leave an optional parent category unfilled when none of the documented
  categories genuinely applies; keep the specific measured marker.
- Do not extract other real findings from the paper if their main result is
  outside this evidence scope.
- Keep statistics and locators compact. If formatting makes a value
  unreadable, use `not_reported` rather than copying broken fragments, repeated
  whitespace, line breaks, or column spacing.
- Add `abstract_only_limited_detail` to the schema's warning field.
- Add another warning for uncertain source type, domain fit, entity identity,
  result meaning, quantitative value, or interpretation.
- Use `Abstract` as the locator unless the input provides a more specific
  locator.
