# Claims Schema

This schema defines the structured claims we curate and publish to ORKG.

## Required fields
- `compound`
- `target`
- `assay_type`
- `affinity_type`
- `affinity_value`
- `affinity_unit`
- `authors`
- `study_year`
- `evidence_level`
- `source`
- `source_type`
- `access_level`
- `evidence_location`
- `evidence_locator`
- `study_design`
- `study_doi` OR `openalex_id`

## Optional fields
- `species`
- `system`
- `study_title`
- `notes`

## Example
```json
{
  "compound": "LSD",
  "target": "5-HT2A",
  "assay_type": "radioligand binding",
  "affinity_type": "Ki",
  "affinity_value": 2.9,
  "affinity_unit": "nM",
  "species": "human",
  "system": "in_vitro",
  "study_doi": "10.1234/example",
  "study_title": "Example study",
  "authors": "A. Author; B. Author; C. Author",
  "study_year": 2010,
  "evidence_level": "high",
  "source": "doi",
  "source_type": "primary_study",
  "access_level": "full_text_seen",
  "evidence_location": "table",
  "evidence_locator": "Table 2",
  "study_design": "in_vitro_binding_assay"
}
```
