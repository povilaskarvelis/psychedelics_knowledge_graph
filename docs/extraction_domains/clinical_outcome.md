Focus on clinical outcome evidence: human clinical indication, symptom,
diagnosis, functioning, quality of life, response, remission, relapse, or
efficacy findings.

Prioritize:

- enrolled condition or clinical population
- clean condition or indication label for the graph
- population or subgroup context as a separate field
- therapeutic outcome and outcome measure
- intervention/exposure, comparator, dose, session count, and follow-up
- endpoint category and how benefit is interpreted when this is needed to
  understand the result
- response, remission, subgroup, moderator, predictor, or meta-regression
  details only when the result is specifically about them
- result direction as therapeutic interpretation
- sample size and study design

Do not promote ordinary safety events, physiological measures, raw scales,
perioperative anesthesia outcomes, or nonspecific wellbeing/context labels into
clean indication graph endpoints unless the paper explicitly frames them as the
treated clinical problem.

Do not use disease-model or drug-challenge language as a treated condition. In
healthy-volunteer, animal-model, or experimental challenge studies,
schizophrenia-like, psychosis-like, depression-like, anxiety-like, dissociative,
perceptual, or other induced acute effects are not clinical indications. Leave
`condition_or_indication` as `not_applicable` or `not_reported` unless the paper
enrolled participants with that condition. These effects belong to subjective
experience, safety, cognitive/behavioral, or mechanistic scopes depending on how
the paper frames them.

For graph-facing condition labels, use `condition_or_indication` for the
treated or studied clinical problem and `population_or_subgroup` for demographic,
recruitment, eligibility, comorbidity, or subgroup details. Keep
`condition_or_population` as the paper-facing combined wording when useful.

For review and meta-analysis coverage, fill `condition_or_indication` with the
clean condition or treatment target being reviewed, even when the extracted
`entity` is phrased as a symptom, endpoint, or population. Put the measured
symptom, response, remission, functioning, quality-of-life, or relapse endpoint
in `clinical_endpoint` and `clinical_endpoint_category`. Put scales and
instruments such as VAS, BPRS, MADRS, STAI, HADS, TLFB, or Y-BOCS only in
`outcome_measure_or_instrument` or `outcome_measure`; do not use a scale name
as the clinical condition.

When a review substantially discusses several compound-condition pairs, create
separate coverage rows for those pairs. For example, if a review separately
covers psilocybin for alcohol dependence and psilocybin for tobacco dependence,
these should be separate clinical outcome coverage rows.

Examples:

- Use `condition_or_indication`: Major depressive disorder; use
  `population_or_subgroup`: older adults.
- Use `condition_or_indication`: Cocaine use disorder; use
  `population_or_subgroup`: cocaine-dependent adults receiving mindfulness-based
  behavioral modification.
- Use `condition_or_indication`: Suicidality when suicidality is the studied
  treatment target; use safety only when suicidality is treatment-emergent or
  worsened risk.
- Use `condition_or_indication`: Tobacco use disorder for tobacco dependence or
  smoking cessation treatment studies; put abstinence, craving, or withdrawal
  endpoints in `clinical_endpoint`.
- Use `condition_or_indication`: Distress associated with life-threatening
  disease for end-of-life, terminal illness, life-threatening disease, or
  advanced cancer anxiety/depression/distress studies; put anxiety, depression,
  or distress scales in the endpoint and outcome-measure fields.
- Do not use `condition_or_indication`: Schizophrenia for a healthy-volunteer
  ketamine challenge that reports schizophrenia-like or psychotomimetic effects.
  Treat that as subjective-experience evidence, not a condition edge.

Use the optional controlled context fields when stated: `administration_route`,
`dosing_schedule`, `session_context`, `population_model_category`, and
`study_design_category`. These fields are coarse filters; keep exact paper
wording in `dose_or_regimen`, `study_design`, and `population_or_subgroup`.

Do not extract personality traits, cognitive or behavioral tasks, neural
readouts, biomarkers, pharmacokinetic parameters, or mechanistic predictors as
clinical outcome items unless the reported finding is directly about a clinical
condition, symptom, response, remission, functioning, quality of life, relapse,
or other treated clinical problem.

For predictor, moderator, or subgroup findings, keep the clinical outcome as
the item anchor. If the main anchor is a biomarker, brain region, cognitive
construct, target, pathway, exposure parameter, or safety event, leave it to
that evidence scope instead.

For `result_direction`, use `positive` for improvement or benefit, `negative`
for worsening or comparator-favoring results, `no_detected_effect` for no meaningful clinical
effect, and `mixed` for materially divergent clinical findings.
