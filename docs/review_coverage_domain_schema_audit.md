# Review Coverage Domain Schema Audit

Generated: 2026-06-25

This was a no-model audit of non-meta-analysis review routes. The current
review route uses:

- paper type and text depth to select `review_article_text.md` or
  `review_abstract_only.md`
- domain route to append the domain scope note
- domain-specific schemas under `schema/extraction_profiles/review/`

The original shared schema captured broad coverage rows: compound, entity,
population, reviewed evidence type, summary statement, direction or tone,
study/sample summary, limitations, locator, and quote. The current
domain-specific schemas keep those common fields and add domain-native
`domain_result` fields.

## Current Review Route Volume

`route_extraction_tasks.jsonl` currently contains 7,774 review-coverage route
rows. Article-text review examples are available in every active domain.

| Domain | Article-text review rows |
| --- | ---: |
| `clinical_outcome` | 1,038 |
| `molecular_pathway_readout` | 637 |
| `safety_tolerability` | 585 |
| `molecular_target` | 516 |
| `cognitive_behavioral` | 345 |
| `intervention_context` | 344 |
| `brain_system` | 331 |
| `subjective_experience` | 213 |
| `real_world_public_health` | 195 |
| `pharmacokinetics_exposure` | 115 |

## Main Finding

The original shared review schema was useful for light evidence-map coverage,
but it was too generic for review extraction that we would want to analyze by
domain. It could say that a review summarizes a topic, but it often lost the
domain-native shape of what was reviewed.

Reviews should probably stay less detailed than meta-analyses: they usually do
not justify extracting pooled effect sizes or detailed quantitative synthesis
fields. But they still need domain-specific review fields so the output is more
useful than a broad summary paragraph.

## Domain Checks

| Domain | Local examples inspected | What the shared schema misses |
| --- | --- | --- |
| `clinical_outcome` | `10.1002/14651858.cd011611.pub3`; `10.1002/cpt.3478`; `10.1002/cam4.70586` | Clinical indication, specific endpoint, endpoint category, outcome measure or instrument, dose/regimen, treatment role, comparator/control, time window, response/remission definitions, subgroup/moderator context, clinical effect/statistic, evidence certainty, and whether the review is discussing efficacy, acceptability, relapse, distress, pain, suicidality, or disease-specific symptoms. |
| `safety_tolerability` | `10.1002/14651858.cd011611.pub3`; `10.1002/brb3.71187`; `10.1002/nau.25148` | Safety event category, frequency/rate, event count or denominator, severity/seriousness, medical or psychiatric attention, duration/resolution, discontinuation or withdrawal, ascertainment/reporting method, acute vs chronic window, dose/session risk context, recreational vs supervised exposure, affected organ/system, comparator/reference, risk factors, and management or mitigation context. |
| `molecular_target` | `10.1002/cpt.3459`; `10.1002/da.22501`; `10.1007/7854_2024_510` | Target evidence category, receptor/target, assay or method, comparator/reference, ligand/probe/tracer, metric or value, functional consequence, selectivity/off-target context, species/system, and pharmacogenomic variant context. |
| `molecular_pathway_readout` | `10.1002/advs.202413786`; `10.1002/da.22224`; `10.1002/da.22227` | Pathway/readout category, biological process, biomarker type, data source, model/species, tissue/sample, brain region or cellular compartment, comparator/reference, timing, dose/exposure context, direction of change, quantitative value/unit, treatment/response relationship, clinical vs preclinical system, and whether the review is mechanistic, predictive, diagnostic, or qualification-focused. |
| `brain_system` | `10.1002/advs.202413786`; `10.1002/da.22227`; `10.1002/hup.2835`; `10.1002/syn.21675`; `10.1007/s00213-006-0467-3`; `10.1007/s00213-016-4396-5`; `10.1007/s00213-009-1484-9` | Brain region/network, modality or evidence type, analysis method, readout/measure, neural effect or alteration, connectivity or circuit relationship, spatial/network context, task/state, species/system, comparator/reference, timing, dose/exposure context, direction/change, statistic/value, and clinical/behavioral linkage. |
| `cognitive_behavioral` | `10.1002/brb3.71043`; `10.1002/dta.1333`; `10.1002/hup.2811`; `10.1007/7854_2016_466`; `10.1007/s00018-024-05519-2`; `10.1007/s00213-020-05756-w`; `10.1007/s00406-021-01267-7`; `10.1007/s00406-023-01570-5` | Construct category, task/behavior/model, task condition or subdomain, behavioral context, acute vs long-term context, human vs animal system, exposure pattern, dose/regimen, comparator/reference, timing, outcome metric, behavioral effect/change, moderator/subgroup, model validity, confounding or neurotoxicity context, and statistic/value details. |
| `subjective_experience` | `10.1002/hup.2742`; `10.1002/hup.2824`; `10.1002/pcn5.146`; `10.1007/7854_2017_474`; `10.1007/7854_2021_298`; `10.1007/7854_2025_609`; `10.1007/s00213-024-06599-5`; `10.1007/s00213-025-06787-x`; `10.1007/s00406-024-01925-6` | Subjective construct category, population/context, instrument or phenomenological frame, scale subscale/dimension, valence/quality, session/setting context, dose/regimen, comparator/reference, timing, subjective effect/change, therapeutic-process linkage, outcome relationship, dose-response or moderator context, and statistic/value details. |
| `pharmacokinetics_exposure` | `10.1002/cpt.2166`; `10.1002/cpt.3459`; `10.1007/s00018-024-05353-6`; `10.1007/s00213-022-06065-0`; `10.1007/s00228-020-03047-z`; `10.1007/s40262-024-01450-8`; `10.1007/s40262-024-01454-4`; `10.1016/j.bcp.2021.114892`; `10.1016/j.biopha.2023.115775` | Enzyme/transporter/pathway, analyte type, metabolite/analyte, PK or exposure parameter, value/unit, matrix or sample type, dose/route/formulation, dose standardization/equivalence, sampling window, population/system, comparator/reference, co-exposure/modifier, model/method, interaction or potentiation context, pharmacogenomic variant, bioavailability, and exposure-response implication. |
| `intervention_context` | `10.1002/brb3.71187`; `10.1002/brb3.71265`; `10.1002/brb3.71280`; `10.1002/cpp.2945`; `10.1007/7854_2021_298`; `10.1007/7854_2024_532`; `10.1007/7854_2025_612`; `10.1002/jts.23163`; `10.1002/prp2.70097` | Therapy model/orientation, intervention component, component type, component quantity/intensity, preparation/integration/session structure, dose/session context, treatment phase, population/setting, delivery format, comparator/control, provider role, care coordination or collaboration, protocol standardization/fidelity, implementation setting, implementation/acceptability context, cultural adaptation, access/equity context, adjunctive strategy, and relationship to outcomes or safety. |
| `real_world_public_health` | `10.1002/brb3.71265`; `10.1002/hup.2594`; `10.1002/jts.23163`; `10.1007/7854_2025_606`; `10.1007/7854_2025_610`; `10.1007/s44192-024-00077-2`; `10.1016/j.disamonth.2024.101851`; `10.1016/j.eclinm.2024.102711`; `10.1016/j.eclinm.2025.103517` | Population/setting, evidence source or study design, use pattern or service context, exposure pattern or intensity, public-health measure, estimate or qualitative result, estimate unit, comparison/reference group, association or trend, confounding/adjustment/bias context, time window, policy or regulatory context, access/equity barrier, cultural or global-health context, recreational vs therapeutic exposure, implementation implication, and public-health risk or benefit framing. |

## Recommendation

Review extraction should become domain-specific, but not as heavy as
meta-analysis extraction.

The best shape is probably:

- keep the common review-level fields: review assessment, coverage items,
  evidence gaps, locators, and quotes
- add a `domain_coverage` or `domain_result` object inside each coverage item
  selected by `domain_route`
- create one lightweight review schema per active domain under a new directory,
  for example `schema/extraction_profiles/review/<domain>.schema.json`
- keep article-text and abstract-only review prompts separate
- keep review outputs as `review_coverage`, not primary KG evidence

This would preserve the useful boundary: reviews can support evidence maps,
coverage views, and gap summaries, while primary studies and meta-analyses
remain the main structured evidence sources.

## Implementation Status

Implemented on 2026-06-25:

- added domain-specific review schemas under
  `schema/extraction_profiles/review/<domain>.schema.json`
- kept the common review-level structure and added `domain_result` inside each
  `coverage_items[]` row
- constrained each review schema to one `domain_route` and the appropriate
  entity types
- added `text_depth` and source-text provenance fields to review outputs
- updated the route profile loader so review schemas resolve by `domain_route`
- added assembled-prompt and schema validation tests for review article-text
  and abstract-only prompts
- expanded the clinical-outcome review schema after example review inspection to
  capture specific endpoint, outcome measure/instrument, dose/regimen,
  response/remission definitions, moderator/predictor context, clinical
  effect/statistic, and score-direction/benefit interpretation
- expanded the molecular-target review schema after example review inspection to
  capture assay/method, comparator/reference, target effect/change, reported
  metric/value, and ligand/probe/tracer details
- expanded the molecular pathway/readout review schema after example review
  inspection to capture model/species, tissue/sample, brain region or cellular
  compartment, comparator/reference, timepoint/window, dose/exposure context,
  direction/change, quantitative value, and unit details
- expanded the brain-system review schema after example review inspection to
  capture analysis method, readout/measure, connectivity or circuit
  relationship, spatial/network context, comparator/reference,
  timepoint/window, dose/exposure context, direction/change, and reported
  statistic/value details
- expanded the cognitive-behavioral review schema after example review
  inspection to capture task condition or subdomain, behavioral context,
  dose/regimen, comparator/reference, timepoint/window, outcome metric,
  behavioral effect/change, moderator/subgroup, and reported statistic/value
  details
- expanded the subjective-experience review schema after example review
  inspection to capture population/context, scale subscale or dimension,
  dose/regimen, comparator/reference, timepoint/window, subjective
  effect/change, explicit outcome relationship, dose-response or moderator
  context, and reported statistic/value details
- expanded the pharmacokinetics/exposure review schema after example review
  inspection to capture analyte type, PK or exposure parameter, value/unit,
  dose standardization or equivalence, route of administration,
  sampling-time/window, population/system, comparator/reference,
  co-exposure/modifier, and model/method details
- expanded the intervention-context review schema after example review
  inspection to capture component type, component quantity/intensity,
  dose/session context, timepoint/phase, population/setting, delivery format,
  comparator/control, care coordination or collaboration, protocol
  standardization/fidelity, implementation/acceptability context, and
  relationship to outcome or safety
- expanded the safety/tolerability review schema after example review
  inspection to capture frequency/rate, event counts, medical or psychiatric
  attention, duration/resolution, discontinuation or withdrawal,
  ascertainment/reporting method, risk-factor context, and comparator/reference
  details
- expanded the real-world/public-health review schema after example review
  inspection to capture evidence source or study design, exposure
  pattern/intensity, public-health measure, estimate value/unit,
  comparison/reference group, association/trend, confounding/adjustment, and
  time-window details
- kept review profiles scaffolded, so they are available for testing but are
  not part of default model extraction yet

## Suggested Implementation Order

1. Done: add domain-specific review schemas using the current shared review schema as
   the base.
2. Done: add domain-specific regression coverage for review schemas.
3. Done: update the route profile loader so `review_coverage_schema` resolves by
   `domain_route`, the same way meta-analysis schemas now do.
4. Done: run assembled-prompt checks for review article text and abstract-only inputs.
5. Next: pilot a few review outputs only after the schema/prompt assembly is clean.
