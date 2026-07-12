Focus on real-world-use and public-health evidence: epidemiology, prevalence,
use patterns, community or retreat settings, clinical-practice evidence,
emergency visits, poison-center data, harm reduction, policy, access,
population-level safety, or public-health impact findings.

Prioritize:

- population and setting
- evidence source or study design, such as survey, registry, observational,
  administrative, poison-center, qualitative, or scoping-review evidence
- controlled data-source type when it can be identified
- comparison group, exposure level, or reference group when reported
- a stable research topic or outcome on one consistent axis, such as population
  use and trends, use patterns, motivations, health outcomes, problematic use,
  acute harms, treatment effectiveness, access, implementation, economics, or
  policy outcomes
- prevalence, rate, count, association, or qualitative public-health conclusion
- public-health interpretation

Capture policy, regulatory, access/equity, implementation, exposure-pattern,
confounding, adjustment, or bias context only when it is central to the
public-health finding.

Use `public_health_topic_category` for the graph-facing real-world research
question or outcome and `public_health_measure` for the specific estimate,
behavior, signal, or measure. Prefer stable topic labels such as Population use
& trends, Use patterns & practices, Motivations & intentions, Predictors &
correlates, Perceived benefits & harms, Health & functioning outcomes,
Problematic use & dependence, Acute harms & healthcare use, Treatment
effectiveness & care outcomes, Harm reduction practices, Drug composition &
adulteration, Availability & market trends, Access & equity, Implementation &
acceptability, Economic & resource impacts, and Policy & legal outcomes.

Do not use Microdosing, Recreational use, Self-treatment, Ceremonial/retreat
use, Polysubstance use, Clinical care, Wastewater, Drug checking, or
Poison-center data as mutually exclusive graph topics. Put the first six in
`real_world_use_context` as semicolon-separated context tags; put the evidence
source in `data_source_type`. Multiple context tags may apply to one finding.

Fill `data_source_type` with the closest controlled value when stated: survey,
poison center/toxicology, wastewater, drug checking, administrative/registry,
qualitative/interview, or observational cohort. Use `study_design` for exact
paper wording and `study_design_category` for the coarse design bucket.

Do not extract a result merely because participants are described as drug users
in a mechanistic or clinical study.

Do not create standalone clinical, safety, mechanistic, subjective-experience,
brain-system, cognitive/behavioral, or pharmacokinetic items here unless the
reported finding is directly about population-level impact, use pattern,
epidemiology, policy, access, equity, service delivery, harm reduction, or
public-health risk/benefit.
