# Mechanistic Claims Schema

`claims.schema.json` is the active mechanistic claim schema for Gemini
extraction-v1 graph inspection. It is intentionally broader than the older
affinity-only schema: target claims do not need a numeric Ki/Kd/IC50-like value
to enter the graph.

The old strict binding/affinity schema is preserved at
`legacy_mechanistic_affinity_claims.schema.json` for compatibility checks and
legacy curated graph exports.

## Required Fields

- `claim_type`
- `compound`
- `target`
- `authors`
- `study_year`
- `paper_type`
- `evidence_level`
- `support`
- `confidence`
- `needs_human_review`
- `source`
- `source_type`
- `paper_assessment_route`
- `access_level`
- `evidence_location`
- `evidence_locator`
- `study_design`
- `study_doi` OR `openalex_id`

## Mechanistic Detail Fields

These are optional because extraction-v1 can describe several kinds of
mechanistic evidence:

- `mechanism_type`
- `assay_type`
- `assay_family`
- `action_type`
- `affinity_type`
- `affinity_value`
- `affinity_unit`
- `result_direction`
- `species`
- `model_or_system`
- `system`

## Inspection Fields

The default graph projection keeps extraction quality flags visible rather than
using them as hard filters:

- `support`
- `confidence`
- `needs_human_review`
- `supporting_quote`
- `notes`

## Example

```json
{
  "claim_type": "compound_target",
  "compound": "Ketamine",
  "target": "N-methyl-D-aspartate receptor (NMDAR)",
  "mechanism_type": "receptor antagonism",
  "assay_type": "pharmacological challenge",
  "action_type": "antagonist",
  "affinity_type": "",
  "affinity_value": "",
  "affinity_unit": "",
  "species": "human",
  "system": "clinical",
  "study_doi": "10.1234/example",
  "study_title": "Example study",
  "authors": "A. Author; B. Author; C. Author",
  "study_year": 2026,
  "paper_type": "primary_results",
  "evidence_level": "medium",
  "support": "supported",
  "confidence": 0.92,
  "needs_human_review": false,
  "source": "doi",
  "source_type": "primary_study",
  "paper_assessment_route": "primary_evidence",
  "access_level": "full_text_seen",
  "evidence_location": "text",
  "evidence_locator": "Results",
  "study_design": "randomized_controlled_trial",
  "supporting_quote": "Directly quoted support from the source text."
}
```
