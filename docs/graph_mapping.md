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
