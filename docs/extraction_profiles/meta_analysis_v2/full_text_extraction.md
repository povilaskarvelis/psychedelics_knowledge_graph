# Full-Text Meta-Analysis Evidence Extraction

## Task

Extract the main quantitative synthesis evidence reported in the supplied
paper. Describe the paper's objective, the questions it addresses, its main
results, and the qualifications needed to interpret those results accurately. Base every value and interpretation on the supplied metadata and article text.

## Relevant subject matter

The research concerns classic psychedelics, MDMA, ketamine, related compounds,
psychedelic-assisted interventions, and their clinical, safety, biological,
behavioral, subjective, pharmacological, contextual, or population effects.

Use `extraction_status` as follows:

- `extracted`: at least one relevant quantitative synthesis result is reported;
- `no_extractable_synthesis_result`: this is a quantitative synthesis, but the
  text contains no usable synthesis result;
- `wrong_source_type`: the paper is not a meta-analysis or another form of
  quantitative evidence synthesis;
- `human_review`: the source type or evidence is too ambiguous;
- `not_relevant`: the paper does not report evidence within the subject matter
  defined above.

For any other status, return no synthesis results and state why in `warnings`.

## Paper overview and questions

Use `meta_analysis_overview` for the reported objective, synthesis type,
research question, central subjects, populations or systems, and included-
evidence details such as counts, designs, dates, and registration.

Use `main_questions` for the questions or comparisons defining the purpose and
principal analyses. Mark the objective, primary outcome, or principal
comparison `main`; use `supporting` for a material qualification.

## Synthesis results

Create a separate `synthesis_results` item for each pooled, network,
dose-response, multilevel, subgroup, sensitivity, or meta-regression result
needed to represent the principal findings and important qualifications.

Set `importance_in_paper` to:

- `main` for a principal answer;
- `supporting` for a material qualification;
- `additional` for useful secondary evidence not needed for the principal answer.

Do not reproduce every analysis from a large table or supplement. Preserve
important differences, null or mixed findings, and conclusion-changing
qualifications.

Write `relationship_statement` as a complete statement of what was synthesized
and found. Preserve the population or system, intervention or exposure,
comparator, outcome or entity, time window, and direction when they affect the
meaning. Keep meaningfully different results separate.

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

Use `null` for one of these fields only when the paper does not identify it.
Link results to the relevant questions with `addresses_question_ids`.

One result item represents one outcome and its corresponding quantitative
estimate. When different outcomes have different estimates, create separate
result items so an estimate cannot be assigned to the wrong outcome. Separate
subgroups when they have different estimates.

## Quantitative information

Copy reported values exactly, including signs, units, scales, transformations,
interval levels, and inequalities. Extract when reported:

- effect metric and point estimate;
- confidence or credible interval;
- p value and standard error;
- statistical model, analysis scale, unit of analysis, and adjustment;
- reported evidence counts;
- subgroup, moderator, meta-regression, sensitivity, multiplicity, or
  dependency-handling details;
- I-squared, tau-squared, Cochran's Q, the Q-test p value, prediction interval,
  and the authors' interpretation of heterogeneity.

Omit unreported optional fields. Do not calculate, convert, infer, or
reconstruct statistics. Put an uncertain reported value in
`extraction_uncertainties` instead of assigning it to an unclear result.

Choose `finding_direction` from the estimate, uncertainty, analysis context,
and authors' interpretation. `no_detected_effect` means no effect was detected;
`does_not_support` weighs against the relationship; `insufficient_evidence`
cannot answer it; and `mixed` contains conclusion-relevant differences.

Use `supports` only when the quantitative result supports the relationship
under the analysis criterion reported in the paper. When a p value exceeds the
reported significance threshold or an uncertainty interval includes the null
value, use `no_detected_effect` unless the paper reports another explicit
criterion that supports a different interpretation. Keep a suggested trend or
potential benefit in `authors_interpretation` rather than strengthening
`finding_direction`.

## Network meta-analysis

For a reported network result, preserve the treatments, reference treatment,
evidence type, substantive ranking with its metric, inconsistency, and
transitivity. Do not infer comparisons or reconstruct the network.
Use a network result role only when the paper reports a network meta-analysis.

A result marked `network_comparison` or `network_ranking` must include
`network_meta_analysis`. A network comparison must identify the treatments in
`treatment_a` and `treatment_b`.

## Risk of bias, certainty, and publication bias

Use the separate assessment arrays for reported assessments. Preserve the
method or framework, scope, judgment or rating, reasons, and adjusted estimate.
Link assessments to result IDs when the paper makes that connection.

Keep risk of bias, certainty, and publication bias separate. Do not create an
unreported rating or judgment. Use an empty array when none is reported.

## Evidence and interpretation

Give every result, assessment, and conclusion a precise source locator and a
short contiguous verbatim excerpt. Do not join separated text with ellipses.
Use a table or figure identifier when clearest.

Use `statistical_interpretation` for what the estimate and uncertainty show;
use `authors_interpretation` for the authors' interpretation and caution.

Use result `limitations` for one result and `overall_limitations` across the
paper. Include only limitations established by the text.

Use `paper_conclusions` for the paper's principal conclusions and link them to
the supporting result IDs when the connection is clear.

Use `warnings` only for genuine source ambiguity or extraction problems that
require attention.

## Output

Return one JSON object matching the supplied schema, without other text.
