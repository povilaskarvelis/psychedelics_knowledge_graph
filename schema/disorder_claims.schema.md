# Disorder Claims Schema

This schema defines structured claims linking compounds to disorders with
clinical or preclinical outcome evidence.

## Required fields
- `compound`
- `disorder`
- `outcome_type`
- `result_direction`
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

## Optional fields
- `outcome_measure`
- `population`
- `system`
- `study_title`
- `notes`

## Example
```json
{
  "compound": "Psilocybin",
  "disorder": "Major depressive disorder",
  "outcome_type": "reduces symptoms",
  "result_direction": "positive",
  "outcome_measure": "MADRS",
  "population": "adults with treatment-resistant depression",
  "system": "clinical",
  "study_doi": "10.1234/example",
  "study_title": "Example trial",
  "authors": "A. Author; B. Author; C. Author",
  "study_year": 2021,
  "paper_type": "primary_results",
  "evidence_level": "high",
  "source": "doi",
  "source_type": "primary_study",
  "access_level": "full_text_seen",
  "evidence_location": "text",
  "evidence_locator": "Results",
  "study_design": "randomized_controlled_trial"
}
```
