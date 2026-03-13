# Evidence and Provenance Policy

This policy governs how claims are labeled and trusted.

## Required provenance fields
Every claim must include:
- `paper_type`: `primary_results`, `review`, `protocol`, `conference_or_poster_abstract`, or `other`
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

## Minimal claim direction
- Disorder claims also include `result_direction`: `positive`, `null`, `negative`, `mixed`, or `unclear`
- `protocol`, `review`, and `conference_or_poster_abstract` papers are not countable primary-evidence claims
- Rows auto-demoted from the main curated set are kept in exploratory files under `data/curated/` rather than deleted

## Access-level semantics
- `full_text_seen`: curator verified claim from full paper content
- `abstract_only`: curator verified claim from abstract only
- `secondary_summary`: claim taken from a review, summary table, or secondary source

## Upgrade path
1. Convert `secondary_summary` to `full_text_seen` with explicit locator.
2. Replace review-derived mechanistic values with primary-study values when available.
3. Add a second independent source for high-impact edges.

## Cleanup workflow
- Build a cleanup candidate report:
  `python pipeline/validate/build_cleanup_report.py`
- Apply only the obvious auto-demotions:
  `python pipeline/validate/apply_cleanup_demotions.py --apply`
- Refresh stale abstract locators for rows already marked `full_text_seen`:
  `python pipeline/validate/refresh_pdf_provenance.py --apply`
- Resolve the clearest `paper_type=other` high-impact disorder rows before the long-tail manual pass:
  `python pipeline/validate/resolve_high_impact_manual_review.py --apply`
