# Extraction V1 Mechanistic Addendum

Use this addendum only when the input record has `dataset = "mechanistic"`.
Extract only `compound_target` evidence. Do not extract compound-disorder or
therapeutic-outcome claims for this dataset.

## Mechanistic Task

Extract a `compound_target` claim only when the supplied input directly supports
an original compound-to-molecular-target relationship.

For mechanistic claims:

- `claim_type` must be `compound_target`.
- `target` should be the best molecular target supported by the input.
- `disorder` and `result_direction` must be `not_applicable`.
- Put agonist, antagonist, inhibitor, modulator, binding, uptake, release, or
  functional activity language in `action_type`, `assay_type`, `assay_family`,
  or `notes`.
- Use affinity labels exactly as `Ki`, `Kd`, `IC50`, `EC50`, `EC90`, `Other`,
  or `not_reported`.
- Include assay type, affinity/functional value and unit, species, and
  model/system when explicitly reported.

## Mechanistic Graph Candidate

Set `graph_include_candidate = true` only for a direct
compound-to-molecular-target edge. Use `entity_role = "molecular_target"`,
`graph_entity_type = "target"`, and the best supported target label.

Use `raw_entity_label` and `graph_include_candidate = false` for findings that
are mainly about genotype moderation, pathways, brain regions, biomarkers,
imaging/physiology, behavioral readouts, or broad assay effects without a clear
molecular target edge.

If the paper only discusses clinical/disorder outcomes or non-target biomarkers,
use `context_only`, `exclude`, or `human_review` rather than forcing a target
claim.
