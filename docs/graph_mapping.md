# Graph Mapping Plan

## Concept
Each curated claim becomes a graph contribution with structured properties for
mechanistic or disorder evidence. We then aggregate edges in the UI.

## Entities
- Compound
- Target or disorder
- Study
- Claim contribution

## Properties (per contribution)
- `compound`
- `target`
- `assay_type`
- `affinity_type`
- `affinity_value`
- `affinity_unit`
- `species`
- `system`
- `source_type`
- `source_family`
- `paper_type`
- `access_level`
- `evidence_location`
- `evidence_locator`
- `study_design`
- `evidence_level` (legacy/internal compatibility field, not a certainty rating)
- `study_year`
- `source`
- `doi` or `openalex_id`

## Suggested Templates
Use templates such as:
- `Psychedelics: Mechanistic Targets`
- `Psychedelics: Disorder Outcomes`

Template fields mirror the properties above. Each new paper adds one or more
contributions using the relevant template. If a paper reports multiple targets
or outcomes, create one contribution per claim.

## Provenance
- Use DOI/openalex_id in the `source` field and retain paper title, journal,
  year, and provider metadata where available.
- Primary and secondary graph views are controlled by source/provenance fields
  such as `source_type`, `paper_type`, `source_family`, and `access_level`, not
  by the legacy `evidence_level` high/medium/low values.

## Future Additions: Endpoint Graph Views

The clean default graph should keep primary indication and mechanistic target
edges separate from raw endpoints. However, extraction already preserves many
non-graph endpoints that could later become explicit additional graph
visualizations and exploration modes.

Candidate future graph views:

- Outcome measures: MADRS, PHQ-9, GAD-7, CAPS, SDS, WHO-5, and related scales
- Functional outcomes: wellbeing, functioning, mindfulness, quality of life
- Safety/adverse events: suicidality, mania switch, flashbacks, tolerability
- Biomarkers: BDNF, TNF-alpha, inflammatory markers
- Symptoms: anxiety symptoms, depressive symptoms, fear of death, sleep disturbance

These should not be promoted directly into the main indication graph. A future
implementation should treat them as selectable graph views or overlays that can
be seen and explored directly, likely derived from `raw_entity_label`,
`entity_role`, `outcome_type`, `outcome_measure`,
`outcome_measure_normalized`, `adverse_events`, and normalization audit rows.
