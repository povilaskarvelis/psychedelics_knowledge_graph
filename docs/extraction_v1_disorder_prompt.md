# Extraction V1 Disorder Addendum

Use this addendum only when the input record has `dataset = "disorder"`.
Extract only `compound_disorder` evidence. Do not extract compound-target
pharmacology claims for this dataset.

## Clinical Task

Extract a `compound_disorder` claim only when the supplied input directly
supports an original compound-to-disorder, compound-to-indication, or
compound-to-clinical-outcome relationship.

For disorder claims:

- `claim_type` must be `compound_disorder`.
- `target` must be `not_applicable`.
- `disorder` names the clinical endpoint being extracted. Use
  `not_applicable` only for endpoints that are not disorders, symptoms, safety
  signals, or interpretable clinical problems.
- Prefer outcome domain, outcome measure, qualitative result direction, sample
  size, population, intervention/exposure, comparator, dose/session details,
  timepoint, and adverse events when explicitly reported.
- Use `clinical_context_condition` for the broader population or clinical
  context when it differs from the extracted endpoint.

## Clinical Endpoint Roles

Classify the endpoint with the most specific supported role:

- `therapeutic_indication`: diagnosed condition or explicit indication studied
  or treated, such as major depressive disorder, PTSD, alcohol use disorder,
  social anxiety disorder, migraine, or neuropathic pain. Use
  `graph_entity_type = "condition_indication"` and
  `graph_include_candidate = true`.
- `symptom_or_problem`: measured clinical symptom/problem that is not clearly a
  diagnosis or indication, such as depressive symptoms, anxiety symptoms,
  suicidal ideation, craving, sleep disturbance, fear of death, or pain
  intensity. Use `graph_entity_type = "symptom_problem"` and
  `graph_include_candidate = true` only when the symptom/problem is a main
  clinical endpoint.
- `safety_or_adverse_event`: tolerability, adverse events, physiological safety,
  vital signs, mania switch, flashbacks/HPPD, nausea, dissociation as an adverse
  effect, serious adverse events, or respiratory/cardiovascular safety. Use
  `graph_entity_type = "safety_adverse_event"` and
  `graph_include_candidate = false`.
- `outcome_measure`: instrument or scale used to measure an endpoint, such as
  MADRS, PHQ-9, GAD-7, LSAS, CAPS-5, or C-SSRS. Put scales in
  `outcome_measure`; do not create a separate claim just because a scale
  appears.

Do not promote vague labels such as depression, anxiety, pain, social anxiety,
mental health, wellbeing, therapeutic potential, or patient experience into a
condition unless the supplied text explicitly frames them as a diagnosis,
enrolled condition, or treated indication. When they are measured symptoms,
classify them as `symptom_or_problem`.

## Result Direction

`result_direction` means the therapeutic or functional interpretation, not the
raw numeric direction of the measured variable:

- `positive`: beneficial therapeutic or functional effect.
- `null`: no meaningful therapeutic or functional effect.
- `negative`: worsening, harm, or poorer functioning.
- `mixed`: both beneficial and unfavorable findings.
- `unclear`: evidence does not support a clear interpretation.

## Clinical Graph Candidate

Set `graph_include_candidate = true` only for clean condition/indication or
symptom/problem endpoints. Use the best supported concise label in
`graph_entity_label`.

Do not put raw endpoints such as heart rate, blood pressure, adverse events,
biomarkers, patient satisfaction, opioid consumption, imaging readouts, or
population/context labels in the `disorder` slot. Put them in
`raw_entity_label`, `outcome_measure`, `outcome_domain`, or `adverse_events`;
set `entity_role` accordingly; and set `graph_include_candidate = false`.

If the paper only discusses receptor pharmacology without an in-scope condition
or therapeutic outcome, use `context_only`, `exclude`, or `human_review` rather
than forcing a disorder claim.
