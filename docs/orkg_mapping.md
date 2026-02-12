# ORKG Mapping Plan

## Concept
Each study becomes an ORKG "contribution" with structured properties for
mechanistic evidence. We then aggregate edges for compound -> target in the UI.

## Entities
- Compound (ORKG resource)
- Target (ORKG resource)
- Study (ORKG contribution)

## Properties (per contribution)
- `compound`
- `target`
- `assay_type`
- `affinity_type`
- `affinity_value`
- `affinity_unit`
- `species`
- `system`
- `evidence_level`
- `study_year`
- `source`
- `doi` or `openalex_id`

## Suggested ORKG Template
Create a template called:
- `Psychedelics: Mechanistic Targets`

Template fields mirror the properties above. Each new paper adds one or more
contributions using the template. If a paper reports multiple targets, create
one contribution per target.

## Provenance
- Use DOI/openalex_id in the `source` field.
- Add the paper title and year to help reviewers validate quickly.
