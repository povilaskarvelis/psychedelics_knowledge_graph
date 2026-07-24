# Abstract-Only Meta-Analysis Evidence Extraction

## Task

Extract the quantitative synthesis evidence explicitly reported in the
supplied paper's title and abstract. Describe the paper's stated objective,
main abstract-reported results, and stated qualifications.

The title, abstract, and metadata are the complete evidence available for this
task. Base every value and interpretation on that material.

## Relevant subject matter

The extraction is intended for research about classic psychedelics, MDMA,
ketamine, related psychoactive compounds, psychedelic-assisted interventions,
and their clinical, safety, biological, behavioral, subjective,
pharmacological, contextual, or population-level effects.

Use `extraction_status` as follows:

- `extracted`: the abstract reports at least one relevant quantitative
  synthesis result;
- `no_extractable_synthesis_result`: the paper is a quantitative evidence
  synthesis, but the abstract contains no usable synthesis result;
- `wrong_source_type`: the paper is not a meta-analysis or another form of
  quantitative evidence synthesis;
- `human_review`: the source type or reported evidence is too ambiguous for a
  reliable extraction;
- `not_relevant`: the paper does not report evidence within the subject matter
  defined above.

For any other status, return no synthesis results and state why in `warnings`.

## Paper overview and questions

Use `meta_analysis_overview` for the synthesis type, objective, research
question, central subjects, populations or systems, and included-evidence
information stated in the title or abstract.

Use `main_questions` for the questions or comparisons expressed by the stated
objective and principal abstract results. Mark a question `main` when it
expresses the objective, primary outcome, or principal comparison. Mark it
`supporting` when it materially qualifies or completes a main question.

## Synthesis results

Create a separate `synthesis_results` item for each distinct pooled estimate,
network estimate, dose-response result, subgroup result, meta-regression
result, or quantitative conclusion explicitly reported in the abstract.

Use `importance_in_paper` as follows:

- `main`: directly answers a main question or reports a principal result;
- `supporting`: materially qualifies or completes a main result;
- `additional`: reports a secondary result needed to avoid misrepresenting the
  abstract.

Write `relationship_statement` as a complete statement of what was synthesized
and what the abstract reports. Preserve the population or system, intervention
or exposure, comparator, outcome or entity, time window, and direction when
they are stated and affect the meaning. Keep results separate when combining
them would hide a meaningful difference in any of these features.

Each result must identify:

- `primary_subject_area`: the subject area that best represents its principal
  finding;
- `subject_areas`: every applicable subject area, including the primary one;
- `population_or_system`: the population, species, or system represented;
- `intervention_or_exposure`: the compound, intervention, regimen, or exposure
  represented by the result;
- `comparator`: the comparator or reference condition represented;
- `outcome_or_entity`: the outcome, endpoint, biological entity, construct, or
  measure represented by the result;
- `timepoint_or_window`: the assessment or exposure window represented.

For a `brain_system` result, keep the measured phenomenon—such as functional
connectivity, BOLD response, blood flow, or signal complexity—in
`outcome_or_entity`. Put every brain region, named brain network, or neural
circuit explicitly represented by that same result in `brain_system_entities`,
using one entry per entity. Do not infer an anatomical entity not stated in
the abstract.

For a `molecular_target` result, keep the measured quantity—such as binding
selectivity, affinity, occupancy, or a network measure—in `outcome_or_entity`.
Put every receptor, transporter, enzyme, channel, or target family explicitly
represented by that same result in `molecular_target_entities`, using one entry
per entity. Do not infer a molecular target not stated in the abstract.

Use `null` for one of these fields only when the abstract does not identify it.
Link results to the relevant questions with `addresses_question_ids`.

One result item represents one outcome and its corresponding quantitative
estimate. When different outcomes have different estimates, create separate
result items so an estimate cannot be assigned to the wrong outcome. Separate
subgroups when they have different estimates.

## Quantitative information

Copy reported values exactly, including signs, units, scales, transformations,
interval levels, and inequalities. Extract an effect estimate, uncertainty
interval, p value, evidence count, heterogeneity statistic, model, subgroup or
moderator, or other analysis detail only when the abstract reports it.

Omit an optional field or object when the abstract does not report it. Do not
calculate, convert, infer, or reconstruct an unreported statistic. Put an
uncertain reported value in `extraction_uncertainties` instead of assigning it
to a result whose population, comparison, outcome, or analysis is unclear.

Choose `finding_direction` from the result and interpretation reported in the
abstract. `no_detected_effect` means that the analysis did not detect an
effect; `does_not_support` means that the synthesis weighs against the proposed
relationship; `insufficient_evidence` means that the evidence cannot answer
the question; and `mixed` means that the findings differ in a way that matters
to the conclusion.

Use `supports` only when the quantitative result supports the relationship
under the analysis criterion reported in the abstract. When a p value exceeds
the reported significance threshold or an uncertainty interval includes the
null value, use `no_detected_effect` unless the abstract reports another
explicit criterion that supports a different interpretation. Keep a suggested
trend or potential benefit in `authors_interpretation` rather than
strengthening `finding_direction`.

## Network meta-analysis

For a reported network result, preserve the treatments, reference treatment,
evidence type, ranking, inconsistency assessment, and transitivity assessment
only to the extent stated in the abstract. Do not infer an unreported network
comparison or ranking.
Use a network result role only when the abstract reports a network meta-analysis.

A result marked `network_comparison` or `network_ranking` must include
`network_meta_analysis`. A network comparison must identify the treatments in
`treatment_a` and `treatment_b`.

## Risk of bias, certainty, and publication bias

Use an assessment array only for assessments explicitly reported in the
abstract. Preserve the named method or framework, scope, judgment or rating,
stated reasons, and any reported adjusted estimate. Do not create a certainty
rating or risk judgment that the abstract does not report. Use an empty array
when an assessment type is not reported.

## Evidence and interpretation

Give every result, assessment, and paper conclusion an abstract locator and a
short contiguous verbatim excerpt copied from the abstract. Do not join
separated text with ellipses. Use a specific locator such as `Abstract
methods`, `Abstract results`, or `Abstract conclusion`.

Use `statistical_interpretation` for what the estimate and uncertainty show;
use `authors_interpretation` for the authors' interpretation and caution.

Use result `limitations`, `overall_limitations`, and `paper_conclusions` only
for abstract content. Use `warnings` only for genuine extraction problems.

## Output

Return one JSON object matching the supplied schema, without other text.
