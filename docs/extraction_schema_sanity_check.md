# Extraction Schema Sanity Check

Generated: 2026-06-24

This is a no-model sanity check of the current extraction schemas against local
article text inputs in `data/processed/extraction/fulltext_packets.jsonl` and
the route/text audit tables in `data/processed/extraction/`.

## Papers Checked

| DOI | Type | Routed domains inspected | Why useful |
| --- | --- | --- | --- |
| `10.1001/archgenpsychiatry.2010.90` | primary study | clinical outcome, safety, subjective experience | RCT with MADRS outcomes, response rates, adverse/manic symptoms, and dissociation |
| `10.1001/jama.2023.14530` | primary study | clinical outcome, intervention context, safety | modern psilocybin RCT with dose, psychotherapy/context, response/remission, and safety reporting |
| `10.1001/archgenpsychiatry.2011.156` | primary study | molecular target, brain system, real-world/public health | PET/receptor availability paper with brain regions, 5-HT2A BP_ND, exposure history, and confounding controls |
| `10.1001/jamanetworkopen.2024.45278` | primary study | molecular pathway/readout, pharmacokinetics/exposure, safety | MDMA fluid restriction/oxytocin/sodium paper linking analytes, physiology, and hyponatremia |
| `10.1001/jamanetworkopen.2024.5960` | meta-analysis | safety/tolerability | psilocybin adverse-event meta-analysis with risk ratios, adverse-event categories, and heterogeneity |
| `10.1001/jamanetworkopen.2025.24119` | meta-analysis | clinical outcome | depression control-group meta-analysis with within/between-group effects and trial-level tables |
| `10.1001/jamanetworkopen.2020.4693` | meta-analysis | subjective experience, safety, pharmacokinetics/exposure | ketamine symptom meta-analysis with SMDs, subgroup labels, risk of bias, and symptom domains |

See `docs/meta_analysis_domain_schema_audit.md` for the full meta-analysis
domain-by-domain audit.

## Main Findings

The primary schemas are directionally right. The sampled primary papers usually
report exactly the things the schemas ask for: population, design, compound or
exposure, comparator, dose, assessment timepoint, endpoint/readout, quantitative result,
p value when needed, and a short interpretation.

Two primary-schema mismatches were fixed during this pass:

- Primary prompts ask for a locator, but primary domain schemas previously only
  had `evidence_location`. All primary item schemas now include required
  `evidence_locator`.
- Primary prompts ask for study design and statistical support, but several
  primary domain schemas did not have common homes for these. All primary item
  schemas now include `study_design`, `sample_size`, `effect_or_statistic`,
  and compact reported-result fields. Primary route-native schemas no longer
  request quote fields, p values, or confidence intervals as standalone fields.

The meta-analysis schemas fit ordinary pairwise meta-analysis reporting
reasonably well. The sampled safety and clinical meta-analyses expose fields
that already have clear homes: effect metric, effect size, CI, p value, study
count, participant count, I2 heterogeneity, result role, interpretation, and
domain-specific result details.

The removal of individual included-study extraction looks correct. The sampled
meta-analyses often contain references and study tables, but included-study
DOIs are not necessary for the current graph. Aggregate counts and evidence
type summaries are the useful level for now.

## Remaining Design Questions

### Primary Study Schemas

Some field names are still a little too generic or slightly mismatched to
domain language:

- `molecular_target.action_type` works for binding/agonism/antagonism papers,
  but it is awkward for PET receptor-availability papers, where the finding is
  closer to "exposure associated with receptor availability." Consider renaming
  or adding a field such as `target_relationship_or_effect`.
- Brain-system and cognitive/behavioral schemas now have common statistical
  fields, but they still rely on broad `statistic_or_value` for many result
  forms. That may be acceptable for the first pass, but model outputs should be
  reviewed for whether this field becomes too messy.
- Primary schemas remain item-first rather than having a separate paper-level
  methods/design block. This keeps extraction lean, but we should check whether
  repeated design/sample fields across items become annoying downstream.

### Meta-Analysis Schemas

The meta-analysis schema keeps the shared result shape compact. Broad result
roles such as main result, subgroup result, dose-response result, and network
comparison are represented in `result_role`; detailed network geometry and
ranking diagnostics are not separate fields.

Network meta-analysis support is still intentionally compact. The schema now
has fields for the treatment comparison, direct/indirect/mixed/ranking evidence
type, rank or score such as SUCRA or P-score, and inconsistency/transitivity
concerns. A future model-output audit should check whether this is enough before
adding more detailed network geometry fields.

Abstract-only and article-text meta-analysis tasks now use the same
domain-specific schema. Text depth changes the prompt and output provenance,
not the schema. Abstract-only prompts ask the model to fill only what is visible
in the abstract and leave unavailable full-article fields empty.

The domain-by-domain meta-analysis audit found concrete molecular-target schema
gaps: target evidence type, tissue or brain-region context, comparator or
reference, target-level effect/change, ligand or probe, and selectivity or
off-target context. All synthesis domain-result fields now also have JSON Schema
descriptions.

The pathway/readout meta-analysis schema also needed more context for how the
readout is used. It now captures readout category, treatment/response/pathway
relationship, comparator or reference, timing, dose/exposure context, and data
source or feature set.

The brain-system meta-analysis schema needed more context for neuroimaging and
neurophysiology findings. It now captures analysis method, neural effect/change,
circuit relationship, spatial/network context, dose/exposure context, and the
clinical or behavioral context tied to the neural result.

The cognitive/behavioral meta-analysis schema needed more task-level context. It
now captures construct category, task condition or subdomain, outcome metric,
behavioral effect/change, moderator or subgroup, and confounding or adjustment
context.

The subjective-experience meta-analysis schema needed more scale and phenomenology
context. It now captures construct category, scale/subscale or qualitative/NLP
dimension, comparator or reference, assessment context, subjective effect/change,
valence or quality, and dose-response or moderator context.

The pharmacokinetics/exposure meta-analysis schema needed more context for exposure
modifiers and reference conditions. It now captures evidence category, dose
standardization or equivalence, comparator or reference, co-exposure or modifier,
metabolic or transport pathway, and exposure-response or PK-effect context.

The intervention-context meta-analysis schema needed more protocol and care-model
context. It now captures intervention model or orientation, component quantity
or intensity, adjunctive or co-intervention strategy, provider or facilitator
context, protocol standardization or fidelity, and implementation or
acceptability context.

### Review Coverage Schema

The review schema is still a scaffold. It is useful for coverage maps and
evidence gaps, not primary graph evidence. Before making review extraction
runnable, it should probably get the same `text_depth` handling used for primary
and synthesis extraction.

## Practical Next Step

Run a small no-commit pilot with real model outputs after the current schemas:

- 2 primary clinical/safety papers
- 2 primary molecular/brain-system papers
- 2 primary pharmacokinetics/pathway/safety papers
- 2 clinical/safety meta-analyses, including one abstract-only task if possible

Then review whether fields are consistently filled with paper-native language
instead of generic filler such as `not_reported`, overly broad summaries, or
misplaced clinical interpretations.
