# Evidence and Provenance Policy

This policy governs how claims are labeled and trusted.

## Required provenance fields
Every claim must include:
- `source_type`: `primary_study`, `review`, `meta_analysis`, `registry`, or `other`
- `access_level`: `full_text_seen`, `abstract_only`, or `secondary_summary`
- `evidence_location`: `table`, `figure`, `text`, `abstract`, `supplement`, `mixed`, or `unknown`
- `evidence_locator`: concrete location such as `Table 1`, `Figure 2`, `Results`, `Abstract`
- `study_design`: normalized design label

## Evidence level rubric

### Mechanistic claims
- `high`: direct assay evidence from primary study with explicit assay values and target
- `medium`: assay values sourced via review/meta-analysis or partial reporting without direct extraction context
- `low`: indirect mechanistic inference or unsupported secondary mention

### Disorder claims
- `high`: randomized controlled trial (including confirmatory phase studies)
- `medium`: open-label trial, pilot interventional study, or non-randomized prospective trial
- `low`: observational, retrospective, case report, or preclinical-only evidence

## Access-level semantics
- `full_text_seen`: curator verified claim from full paper content
- `abstract_only`: curator verified claim from abstract only
- `secondary_summary`: claim taken from a review, summary table, or secondary source

## Upgrade path
1. Convert `secondary_summary` to `full_text_seen` with explicit locator.
2. Replace review-derived mechanistic values with primary-study values when available.
3. Add a second independent source for high-impact edges.
