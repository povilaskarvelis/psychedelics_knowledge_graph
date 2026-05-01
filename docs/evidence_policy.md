# Evidence and Provenance Policy

This policy governs how claims are labeled and trusted.

## Required provenance fields
Every claim must include:
- `paper_type`: normalized article/result category, including
  `primary_results`, `systematic_review`, `meta_analysis`, `review`,
  `protocol`, `conference_or_poster_abstract`, `case_report`, `commentary`,
  `correction`, `erratum`, `other`, or `uncertain`
- `source_type`: normalized source class, including `primary_study`,
  `secondary_evidence`, `review`, `meta_analysis`, `commentary`,
  `study_protocol`, `correction`, `conference_abstract`, `case_report`,
  `registry`, `other`, or `uncertain`
- `source_family`: broader family such as `original_empirical`,
  `evidence_synthesis`, `opinion_or_commentary`, `protocol`, `correction`,
  `conference_abstract`, or `uncertain`
- `access_level`: `full_text_seen`, `abstract_only`, or `secondary_summary`
- `evidence_location`: `table`, `figure`, `text`, `abstract`, `supplement`, `mixed`, or `unknown`
- `evidence_locator`: concrete location such as `Table 1`, `Figure 2`, `Results`, `Abstract`
- `study_design`: normalized design label

Every paper record should preserve useful bibliographic/extraction fields when
available:
- `study_journal`, `publication_type`, `publication_date`, `journal_issn`,
  `journal_eissn`, `publisher`, `trial_registry_ids`
- `mesh_terms`, `keywords`, `funders`, `grant_ids`, `related_dois`,
  `publication_relations`, `is_retracted`, `has_correction`, `language`,
  `semantic_scholar_id`
- `sample_size_total`, `sample_size_by_arm`, `population`
- `intervention_or_exposure`, `comparator`, `dose`, `route`,
  `session_count_or_duration`
- `primary_outcome`, `outcome_measure`, `timepoint`, `effect_size`, `p_value`,
  `confidence_interval`
- `adverse_events`, `funding`, `conflicts_of_interest`,
  `risk_of_bias_summary`

## Internal evidence tier heuristic

`evidence_level` is an internal sorting and audit heuristic. It is not a formal
GRADE or Cochrane certainty rating and should not be foregrounded as a visible
claim-card badge. The UI should prefer factual provenance labels such as
`rct`, `open label`, `preclinical`, `full text`, `abstract`, and claim
direction.

`evidence_strength` is an LLM/rule proposal field for later synthesis. It
should be treated as provisional unless it is backed by an explicit risk-of-bias
or certainty assessment workflow.

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
- `protocol`, `review`, `systematic_review`, `meta_analysis`,
  `conference_or_poster_abstract`, `commentary`, `correction`, and `erratum`
  papers are not countable primary-evidence claims
- `review`, `systematic_review`, and `meta_analysis` rows are retained as
  secondary literature and can be included through the secondary-source graph
  view/checkmark. They should not be treated as failed primary evidence.
- Protocols, conference abstracts, commentary, corrections, and errata are
  retained as non-primary context when encountered, but are excluded from the
  default primary and secondary-source graph views unless a curator explicitly
  promotes a special-purpose view.
- Case reports are original empirical evidence, but they should normally be
  low-strength and should not be pooled with trials without an explicit view
  choice
- Rows auto-demoted from the main curated set are kept in exploratory files
  under `data/curated/` rather than deleted

## Access-level semantics
- `full_text_seen`: curator verified claim from full paper content
- `abstract_only`: curator verified claim from abstract only
- `secondary_summary`: claim taken from a review, summary table, or secondary source

## Screening and assessment terminology
- **Discovery/search**: database/API retrieval and DOI queue generation.
- **Deduplication**: DOI/title-level merging before screening.
- **Abstract screening**: title/abstract relevance screening before PDF
  acquisition.
- **Full-text eligibility assessment**: full-text decision about whether the
  paper is in scope and what source family it belongs to.
- **Data extraction**: structured extraction of study design, sample, measures,
  outcomes, effect sizes, adverse events, funding/COI, and risk-of-bias notes.
- **Adjudication**: final conflict resolution when deterministic rules, LLM
  proposals, and/or curator decisions disagree.

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
