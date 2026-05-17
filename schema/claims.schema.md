# Claims Schema

This schema defines the structured claims we curate and publish as graph payloads.

## Required fields
- `compound`
- `target`
- `assay_type`
- `affinity_type`
- `affinity_value`
- `affinity_unit`
- `authors`
- `study_year`
- `paper_type`
- `evidence_level`
- `source`
- `source_type`
- `access_level`
- `evidence_location`
- `evidence_locator`
- `study_design`
- `study_doi` OR `openalex_id`

Note: `evidence_level` is still required for compatibility with existing rows
and graph payloads, but it is an internal coarse label rather than a public
certainty rating or graph-inclusion rule.

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
  "paper_type": "primary_results",
  "evidence_level": "high",
  "source": "doi",
  "source_type": "primary_study",
  "access_level": "full_text_seen",
  "evidence_location": "table",
  "evidence_locator": "Table 2",
  "study_design": "in_vitro_binding_assay"
}
```
