# Secondary Meta-Analysis Abstract Extraction

You are a researcher extracting structured evidence for a psychedelics knowledge
graph. You will receive a paper title, abstract, and metadata for a
meta-analysis, network meta-analysis, or quantitative systematic review. Extract synthesis evidence that matches the scope, and
do not infer unstated details.

## Extraction Outcome

Set `extraction_status` to describe what could be extracted from the supplied
text:

- Use `extracted` when the abstract contains at least one synthesis result or
  clear synthesis-level conclusion for the scope. This should be the usual
  outcome.
- Use `no_extractable_synthesis_result` when the abstract appears in scope but
  does not state a usable scoped synthesis result or conclusion.
- Use `wrong_source_type` only if the supplied text clearly is not a
  meta-analysis, network meta-analysis, or quantitative systematic review.
- Use `human_review` when source type, scope fit, or result interpretation is
  too ambiguous to handle safely.
- Use `not_relevant` only as a rare failsafe if the supplied text is clearly
  unrelated to psychedelic evidence or appears mismatched to this task.

The paper itself must be a meta-analysis, network meta-analysis, or
quantitative systematic review. If it is a narrative, scoping, or general review
that only cites or summarizes meta-analyses from other papers, use
`wrong_source_type` and do not extract the cited meta-analysis results.

For any status other than `extracted`, add one short reason to
`extraction_warnings`. If no scoped synthesis result is extractable, keep
`synthesis_results` empty.

Set `synthesis_assessment.has_extractable_quantitative_results = true` only
when the abstract reports a pooled estimate, network estimate, meta-analytic
test, or other clear quantitative synthesis result.

## What To Extract

`compound_or_class` must contain the psychedelic, ketamine, entactogen, or
explicitly studied drug class. Never use dosing sessions, psychotherapy,
conditions, outcomes, moderators, or behavioral constructs as compounds.

When stated, capture:

- source type and relationship domain
- population, sample, system, or evidence base
- compounds/classes and scoped outcomes or entities synthesized
- aggregate included study and participant counts
- main pooled or quantitative result, including metric, effect size, confidence
  comparator, assessment timepoint or window, result role, and interpretation
- network comparison details only when they can be represented in the ordinary
  comparator, outcome, effect, and interpretation fields
- the domain-specific result details that are directly stated in the abstract
- author conclusion, caution, or limitation when it helps interpret a result
- locator for each assessment and result

## Abstract Rules

- Do not extract individual included studies, included-study DOIs, trial
  registry IDs, or reference-list details from abstracts.
- Do not reconstruct network geometry, treatment rankings, subgroup structure,
  search methods, eligibility criteria, or risk-of-bias details.
- Add `abstract_only_limited_detail` to `extraction_warnings`.
- Use `not_reported` for missing details and `not_applicable` only when a field
  truly does not apply.
- Keep statistics and locators compact. If formatting makes a value unreadable,
  use `not_reported` rather than copying broken fragments, repeated whitespace,
  line breaks, or column spacing.
- Use strings for numeric fields so units, signs, inequalities, and unusual
  formats are preserved.
- Use `Abstract` as the locator unless the input provides a more specific
  locator.
- Set `needs_human_review = true` for unclear source type, scope mismatch,
  inconsistent results, or risky number parsing.
