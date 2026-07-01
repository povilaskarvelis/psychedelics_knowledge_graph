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

For graph-facing condition labels, use `condition_or_indication` for the
treated or studied clinical problem and `population_or_subgroup` for demographic,
recruitment, eligibility, comorbidity, or subgroup details. Keep
`condition_or_population` as the paper-facing combined wording when useful.

Examples:

- Use `condition_or_indication`: Major depressive disorder; use
  `population_or_subgroup`: older adults.
- Use `condition_or_indication`: Cocaine use disorder; use
  `population_or_subgroup`: cocaine-dependent adults receiving mindfulness-based
  behavioral modification.
- Use `condition_or_indication`: Suicidality when suicidality is the studied
  treatment target; use safety only when suicidality is treatment-emergent or
  worsened risk.

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
