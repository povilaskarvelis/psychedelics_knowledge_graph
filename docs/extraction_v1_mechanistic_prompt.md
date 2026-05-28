# Extraction V1 Mechanistic Addendum

Use this addendum only when the input record has `dataset = "mechanistic"`.
Extract only mechanistic compound-entity evidence. Do not extract
compound-disorder or therapeutic-outcome claims for this dataset.

## Mechanistic Task

Extract a `compound_target` claim only when the supplied input directly supports
an original compound-to-mechanistic-entity relationship. `compound_target` is
the legacy v1 claim type for all mechanistic graph relationships.

For mechanistic claims:

- `claim_type` must be `compound_target`.
- `target` should be the best mechanistic entity supported by the input.
- `disorder` and `result_direction` must be `not_applicable`.
- Put agonist, antagonist, inhibitor, modulator, binding, uptake, release, or
  functional activity language in `action_type`, `assay_type`, `assay_family`,
  or `notes`.
- Use affinity labels exactly as `Ki`, `Kd`, `IC50`, `EC50`, `EC90`, `Other`,
  or `not_reported`.
- Include assay type, affinity/functional value and unit, species, and
  model/system when explicitly reported.

## Mechanistic Graph Candidate

Set `graph_include_candidate = true` only for a clean mechanistic graph edge.
Use one of these `graph_entity_type` values:

- `target`: direct receptors, transporters, enzymes, ion channels, protein
  complexes, or subunits.
- `system_family`: broad receptor families or neurotransmitter systems when no
  more specific target is supported.
- `pathway_process`: downstream signaling pathways or cellular processes.
- `molecular_readout`: measured molecular/biochemical readouts such as BDNF,
  c-Fos, cytokines, neurotransmitter release, or protein expression.

For `target` and `system_family`, usually use `entity_role =
"molecular_target"`. For `pathway_process`, use `entity_role =
"pathway_or_process"`. For `molecular_readout`, use `entity_role =
"biomarker"`.

Use `raw_entity_label` and `graph_include_candidate = false` for findings that
are mainly about genotype moderation, brain regions, imaging/physiology,
behavioral readouts, assay conditions, or broad effects without a clean
mechanistic endpoint.

If the paper only discusses clinical/disorder outcomes or biomarkers without a
compound-linked mechanistic finding, use `context_only`, `exclude`, or
`human_review` rather than forcing a mechanistic claim.
