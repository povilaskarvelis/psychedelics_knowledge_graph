# Extraction V1 Rerun Tracker

This file is the human-facing tracker for extraction records that should be
retried or repaired after the main extraction batches complete. The generated
projection/normalization/KG outputs should not be edited by hand.

Machine-readable queue records live in:

- `data/curated/extraction_v1_rerun_queue.jsonl`

## Open Rerun Buckets

### Full-text/metadata mismatch quarantines

Status: open

Count: 3 unique DOI records

Source: `data/processed/extraction/projection_report.json`,
`quarantined_records`

These records are excluded from the active KG because their metadata/title
indicates review or synthesis literature, while the extraction packet contained
duplicated primary-study full text from another DOI/title. They need source-text
repair before another Gemini extraction.

Records:

- `10.1007/7854_2021_278` - disorder - The Potential of Psychedelics for End of
  Life and Palliative Care. The packet currently contains the OLTAS psilocybin
  group-therapy pilot text that belongs to `10.1016/j.eclinm.2020.100538`.
- `10.1038/s41380-025-03320-6` - disorder - Efficacy and safety of esketamine on
  major depression, postpartum depression and perioperative depression: a
  systematic review and meta-analysis.
- `10.1007/s00213-022-06098-5` - mechanistic - The role of serotonin
  neurotransmission in rapid antidepressant actions.

Next action:

1. Verify DOI metadata and source text.
2. Find or redownload the correct full text where available.
3. Rebuild extraction packets for only these records.
4. Rerun Gemini extraction for only these records.
5. Merge successful outputs into the active extraction set.
6. Rebuild projection, normalization, KG tables, and graph payloads.

### Malformed or batch-error retries

Status: open

Count: 463 pending records

Input queue:
`data/processed/extraction/extraction_v1_retry_queue.pending_20260526.jsonl`

Report:
`data/processed/extraction/extraction_v1_retry_queue.pending_20260526.report.json`

These records already have retry input packets. They should usually only need an
LLM retry, not PDF redownload, unless a later source check finds packet problems.
This queue was refreshed after `mechanistic_fulltext_rerun_all_20260526`: 46
older full-text mechanistic retry rows in that rerun scope were removed, and
the 27 latest failed rows from that rerun were added. The 42 removed rows that
now have successful latest outputs should not remain in retry state.

### Schema-invalid extraction retries

Status: open

Count: 8 records

Input queue:
`data/processed/extraction/extraction_v1_schema_invalid_retry.active_20260526.jsonl`

Report:
`data/processed/extraction/extraction_v1_schema_invalid_retry.active_20260526.report.json`

These are parsed Gemini outputs that failed the extraction schema, mostly
secondary/meta-analysis-like records with empty or incompatible required fields.
This queue was refreshed after `mechanistic_fulltext_rerun_all_20260526`
promotion and active QA rebuild. Rerun them with the current prompt/schema; if
they remain meta-analysis records without clear coverage mentions, park them
for the future evidence-synthesis extraction layer rather than forcing them
into primary claims.

### Quote-QA failures

Status: open

Count: 63 records

Input queue:
`data/processed/extraction/extraction_v1_quote_error_retry.active_20260526.jsonl`

Report:
`data/processed/extraction/extraction_v1_quote_error_retry.active_20260526.report.json`

These parsed extraction outputs failed supplied-context quote verification. They
are kept separate from malformed/schema-invalid retries because some may be
acceptable after manual review or deterministic quote-matching improvements.
This queue was refreshed after `mechanistic_fulltext_rerun_all_20260526`
promotion and active QA rebuild. Review a sample before deciding whether to
rerun full extraction or only repair supporting quotes.

### Meta-analysis synthesis stream

Status: planned

Normal v1 extraction batches should be built with `--exclude-meta-analyses`.
Those records are intentionally parked in the builder's sibling
`*.excluded.jsonl` output and should be revisited with a dedicated
evidence-synthesis schema rather than the current primary/secondary coverage
schema.

Reason:

Meta-analyses need fields that are not first-class in the current v1 graph claim
contract: pooled effect estimates, confidence intervals, p-values, included
study count, participant count, comparator, outcome scale, heterogeneity, and
review registration/quality details when available.

## Policy

Use deterministic projection or normalization safeguards for repeatable error
classes. Use curated manual overrides only for paper-specific factual
adjudications that cannot be generalized safely, and keep those overrides in a
versioned curated file with reason, evidence note, curator, and date.
