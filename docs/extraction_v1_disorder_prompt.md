# Extraction V1 Disorder Addendum

Use this addendum only when the input record has `dataset = "disorder"`.
Extract only `compound_disorder` evidence. Do not extract compound-target
pharmacology claims for this dataset.

## Disorder Task

Extract a `compound_disorder` claim only when the supplied input directly
supports an original compound-to-disorder, compound-to-indication, or
compound-to-therapeutic-outcome relationship.

For disorder claims:

- `claim_type` must be `compound_disorder`.
- `target` must be `not_applicable`.
- `disorder` should name the treated or studied therapeutic condition when the
  evidence supports one.
- Prefer outcome domain, outcome measure, qualitative result direction, sample
  size, population, intervention/exposure, comparator, dose/session details,
  timepoint, and adverse events when explicitly reported.
- Use `clinical_context_condition` for the broader population or clinical
  context when it is not itself the treated/studied condition.

## Result Direction

`result_direction` means the therapeutic or functional interpretation, not the
raw numeric direction of the measured variable:

- `positive`: beneficial therapeutic or functional effect.
- `null`: no meaningful therapeutic or functional effect.
- `negative`: worsening, harm, or poorer functioning.
- `mixed`: both beneficial and unfavorable findings.
- `unclear`: evidence does not support a clear interpretation.

## Disorder Graph Candidate

Set `graph_include_candidate = true` only for a
compound-to-therapeutic-indication edge. Use `graph_entity_type =
"indication"` and the best supported condition/indication label.

Do not put raw endpoints such as heart rate, blood pressure, adverse events,
biomarkers, patient satisfaction, opioid consumption, imaging readouts, or
population/context labels in the `disorder` slot. Put them in
`raw_entity_label`, `outcome_measure`, `outcome_domain`, or `adverse_events`;
set `entity_role` accordingly; and set `graph_include_candidate = false`.

If the paper only discusses receptor pharmacology without an in-scope condition
or therapeutic outcome, use `context_only`, `exclude`, or `human_review` rather
than forcing a disorder claim.
