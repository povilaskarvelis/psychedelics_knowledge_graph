Focus on cognitive and behavioral evidence: cognitive tasks, behavioral
phenotypes, learning, memory, attention, emotion processing, social behavior,
addiction behavior, craving, relapse, reinstatement, or animal behavioral
outcomes.

Prioritize:

- task, behavioral endpoint, or phenotype
- clean graph construct label and whether it is cognition or behavior
- broad construct category, such as memory, attention, executive function,
  empathy, emotion recognition, reward processing, addiction behavior, pain
  behavior, social cognition, or motor behavior
- species/population and experimental system
- intervention/exposure, comparator, dose, and assessment timepoint
- outcome metric, such as reaction time, accuracy, task score, false recall,
  self-administration, reinstatement, pain threshold, or social-functioning
  score
- behavioral effect or change, such as improved performance, impaired
  performance, slower reaction time, higher empathy, reduced drug seeking,
  increased pain threshold, no clear effect, or mixed findings
- reported behavioral change or functional interpretation

Capture task subdomain, moderator, subgroup, or confounding context only when
it is central to the reported cognitive/behavioral result.

Do not extract ordinary clinical symptom scales in this task unless cognition or
behavior is measured as a distinct construct.

Use `graph_construct_label` for the clean graph node and `task_or_measure` or
`raw_task_or_measure` for the specific task, assay, behavioral test, scale, or
metric. The graph label should describe the cognitive or behavioral construct,
not the instrument name, neural signal, clinical symptom, or molecular pathway.

Examples:

- Open field distance travelled can support a behavior label only when the
  finding is specifically about exploratory behavior, hyperactivity, locomotor
  sensitization, or another interpretable behavioral construct. Otherwise keep
  it as a raw measure and avoid creating a graph construct.
- Forced swim and tail suspension findings should use a behavior label such as
  Stress-coping behavior, not Depression.
- Conditioned place preference, drug self-administration, and drug seeking are
  behavior labels. Working memory, cognitive flexibility, attention, fear
  extinction, and social cognition are cognition labels.
- Withdrawal signs should not become a behavior graph label when the paper is
  studying treatment of withdrawal from another substance; keep withdrawal in
  the measure/context and let the condition label represent the substance-use
  condition.

Fill `construct_family` with `cognition` or `behavior` when the distinction is
clear. Use the optional controlled context fields when stated:
`administration_route`, `dosing_schedule`, `session_context`,
`population_model_category`, and `study_design_category`.

Do not create standalone brain-system, molecular, subjective-experience,
clinical, safety, or pharmacokinetic items here. Neural signals, biomarkers, or
clinical symptoms can be context only unless the item's main anchor is a
cognitive task, behavioral endpoint, phenotype, or behavioral model.
