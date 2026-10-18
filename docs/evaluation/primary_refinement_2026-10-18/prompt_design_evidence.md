# Instruction refinement v3: design evidence and boundaries

Status: candidate submitted for root review; no model calls or activation by this reviewer. The candidate is `docs/extraction_profiles/candidates/primary_instruction_refinement_v3.md`. It keeps all ten current domain schemas and uses only `{{DOMAIN_SCOPE}}`. The prior frozen v2 prompt, domain instructions and schemas were not edited.

The revision targets an observation-binding problem: a model can summarize the right result while attaching another experiment's denominator, time, design, analyte or controlled category. Adding more fields did not reliably solve this. This candidate instead establishes the scientific comparison before filling the existing fields, and treats every populated field as a scientific assertion that must agree with the source.

## Evidence reviewed

I read the structured-prompt-design skill, both current primary-study depth prompts, the previous `primary_observation_v2.md` candidate and its helper, all ten primary domain schemas (including required fields, descriptions and exact enums), all ten domain scope documents, and the material scientific/scope entries across the existing, fresh and controlled comparison cohorts. The machine-readable evidence manifest next to this note records the ledger and schema hashes and the selected entries. New-field errors from the abandoned expanded schema are not counted as failures of the unchanged schemas.

This design pass builds on the completed source audits rather than treating a prior model extraction as truth. I rechecked the original supplied passages for the requested regression examples: P18 species, F36 phases, F15 analyte roles, P71 Figure 5 and P89 Figure 5/6 contrasts. Earlier source qualifications, including damaged table layouts and uncertainty about exact original archived inputs, remain in force. This is a prompt rationale, not a new independently blinded evaluation.

## Priorities

These are design priorities based on scientific consequence and recurrence, not estimated error rates. Several erroneous items in one paper can share one failure, so repeated rows are not independent evidence.

| Priority | Recurring failure | Concrete evidence | Instruction control |
|---|---|---|---|
| 1 | A result inherits numbers, time or comparison from another analysis | P71 behavioral Figure 5 imports molecular/genotype sample sizes; P89 acute versus 2-hour pretreatment counts are crossed; P32 pooled sex totals become per-modality n; P57 follow-up is attached to the wrong participant | Define each observation first. Label n by unit/group; locate row, outcome column or panel; transfer study-wide values only with explicit source support. |
| 2 | Correct narrative coexists with false controlled metadata | P18 rhesus observations become `mouse_model`; P15 human IV becomes `preclinical_injection`; F36 open-label ketamine becomes `rct` because later treatment is randomized; P22 phase 2 becomes a randomized trial without support | Each category must be true for this observation. Choose a broader truthful allowed token, retain exact species/design prose, and repair contradictory fields rather than merely warn. |
| 3 | Exposure, analyte, comparator, measurement and inferred mechanism trade roles | F15 hormone increase becomes changed MDMA exposure; H34 and P61 encode self-metabolism; H29 anchors a perturbation instead of the treatment whose effect is described | State whose exposure and whose measurement the relationship concerns. Keep parent→metabolite direction and assay/probe roles explicit in existing fields and summary. |
| 4 | Extra detail creates unsupported precision or overstated nulls | P29 estimates come from the wrong outcome column or absent/truncated cells; P31 damaged row labels coexist with confident n-to-arm assignment; F45 descriptive headache counts become a null comparison | Require local quantitative binding; preserve qualitative findings when numbers are uncertain; distinguish unreported, descriptive and tested-null results. Warnings must remove unsupported precision throughout the item. |
| 5 | Coverage gains are offset by losing central restrictions or adding out-of-domain/background rows | P18 dose-equated contrast, P29 null/positive contrast distinctions and P89 timing comparisons require coverage; P74 methods-only ROI becomes a result; P25 routine common therapy becomes independently studied context; P93 cited metabolism becomes primary evidence | Inventory distinct main experiments and central null/opposing restrictions; retain useful detail but exclude background, isolated methods and duplicate observations. |

The same binding principle also covers transferred population/phase (F44, P50), endpoint timing (F10, P96), sensitivity-analysis conclusions from a different drug (P59), and adult behavioral nulls extended to an unreported adult neural result (P83). It does not require mentioning any paper ID in the model prompt.

## Source examples checked again

- **P71, F005:** “saline (Sal; n = 24), ketamine (Ket; n = 9), or ketamine plus a miRNA 448-3p antagonist ( n = 12)”. This is the behavioral comparison; nearby molecular assays supply different n values.
- **P89, Figure 6:** “Eight cells, four spines per cell were used.” The local caption associates these counts with the acute/short-treatment analysis. The later pretreatment analysis cannot inherit them merely because it appears in the same figure.
- **F36, C003/C007:** “MDD patients openly received a single i.v. infusion”; BDNF was collected “before riluzole/placebo was administered.” The later randomized maintenance phase does not randomize the preceding ketamine before/after observation.
- **P18, C016:** “measurements of extracellular levels of serotonin in the striatum could be reliably obtained from rhesus monkeys”. The schema has `animal_model`; a mouse-specific token is unnecessary and false.
- **F15, Abstract:** “MDMA induced a robust increase of blood oxytocin concentrations”. A separate comparison concerns correlations with “blood MDMA levels.” These are different analytes and relationships; preserving the measured drug exposure–response comparison does not require creating an oxytocin PK-exposure item.

Exact source text remains authoritative, including qualifications and source errors. These excerpts identify the issue; they do not replace the full source review.

## Schema compatibility decisions

- **No new shared role fields.** Necessary roles and comparisons use existing population/model, comparator, method, exposure, relationship, summary and statistic fields. Domains without a dedicated comparator can retain it in their existing prose.
- **No generated enum guide.** The supplied schemas already provide the complete enum sets. A second generated copy would add prompt length and risk drift. The candidate explains only recurring semantic boundaries and valid broad fallbacks.
- **“Closest allowed value” is not permission to assert a false fact.** The current population/design descriptions contain that wording. The prompt resolves it as a broader truthful allowed category. It does not change an enum. `animal_model`, `other`, `other_or_mixed`, `other_or_unclear`, `uncertain`, `mixed_or_unclear`, `not_reported`, and `not_applicable` are field-specific, not interchangeable global defaults.
- **Optional fields remain conditional.** Omitting an unsupported optional category is permitted only when the supplied schema allows omission. Required free-text fields can use the established missing-value token. No nonexistent fallback is requested in a constrained field.
- **Direction retains current domain meaning.** Clinical/safety direction is benefit or harm, while measured directions and associations remain in the source-facing result text. A descriptive count does not warrant `no_detected_effect` without a reported relevant null.
- **Exact schema version remains unchanged.** The candidate explicitly preserves the supplied version, including the current PK version; it must not emit the abandoned observation-schema version.

## Limits and evaluation expectations

The revision is an untested hypothesis. It should be evaluated on exact same-source/current-schema calls, with current Luna as control, prior cohorts reported separately from the source-first fresh64 set. Keep factual errors, unsupported specificity, controlled metadata, scope, central coverage and downstream mapping separate. Evaluate both lost and gained central null/contrast coverage, and assess output/cost growth rather than rewarding more rows.

The prompt cannot reconstruct missing table headers, unreadable symbols or omitted results. P73 unit corruption illustrates a source-origin problem: plausible units must not be silently repaired, and a source-faithful value can still be scientifically wrong relative to the original PDF. Some schemas remain coarse, and prose still carries roles that normalization must interpret. Downstream errors such as analogue identity collapse, cultural attitudes mapped to perceptual effects, or a radioligand assay mapped to a drug interaction require normalization evaluation; clearer extraction does not itself prove those graph errors are fixed.

The candidate is longer than v2 (1,830 versus 1,036 words before domain insertion). This is a material tradeoff: more explicit binding and fallback guidance may improve consistency but can increase input cost or distract the model. The final test must establish whether those costs buy an improvement. No claim of improvement should be made before the frozen comparisons and source judgments are complete.
