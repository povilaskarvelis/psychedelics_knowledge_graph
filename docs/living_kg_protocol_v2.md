# Living KG Protocol V2

This protocol separates source discovery from graph-edge trust. Existing DOIs
remain useful as a paper corpus, but each `DOI + compound + target/indication`
context must carry explicit provenance before it is treated as evidence.

## Paper Identity

Paper identity is DOI-level. When a new literature search finds a DOI that is
already present in the corpus, the paper should not be added or processed again
as a new paper. The rediscovery should be logged for provenance only.

Use the DOI add gate before metadata sync:

```bash
python pipeline/ingest/add_new_dois.py --dataset disorder --input data/raw/doi_queue.disorder.discovered.txt
```

The `run_extensive_search.py` wrapper runs this gate automatically after
discovery and passes `doi_queue.<dataset>.new.txt` into metadata sync. Run the
standalone command when importing or checking a DOI queue outside the wrapper.

Default outputs:

- `data/raw/doi_queue.<dataset>.new.txt`
- `data/processed/add_new_dois_report_<dataset>.json`
- `data/processed/rediscovered_dois_<dataset>.csv`
- `data/processed/missing_or_invalid_dois_<dataset>.csv`
- `data/processed/input_duplicate_dois_<dataset>.csv`

Only `doi_queue.<dataset>.new.txt` should continue to expensive metadata, PDF,
screening, or extraction steps when the goal is to process newly discovered
papers.

The discovery ledger is not part of the default existing-paper check, because
it is updated during the current discovery run. The gate checks the corpus,
paper libraries, stubs, curated claims, exploratory claims, and known-study set
unless an operator explicitly asks to include ledger history.

## Evidence Layers

1. `candidate_context`: a DOI-context pair found by search, queues, ledgers, or
   inherited artifacts. This is a lead, not a verified edge.
2. `screened_context`: title/abstract screening supports the compound and
   target or indication context, but structured evidence extraction may still
   be incomplete.
3. `verified_evidence`: a curated evidence row with provenance fields such as
   paper type, source type, access level, evidence locator, study design, and
   evidence-specific fields.

The public KG should prefer `verified_evidence`. Methods and gap views may show
candidate and screened contexts when clearly labeled.

## Corpus Migration Audit

Run the audit builder before new large searches:

```bash
python pipeline/validate/build_context_provenance_audit.py
```

Default outputs:

- `data/processed/candidate_paper_corpus.json`
- `data/processed/context_provenance_audit.json`
- `data/processed/context_provenance_summary.json`

The audit aggregates existing artifacts, including DOI queues, discovery
ledgers, discovery reports, paper libraries, abstract-screening reports, triage
reports, claim stubs, curated claims, exploratory claims, known-study entries,
and local PDFs.

Each context records `context_sources`, including values such as
`queue_discovered_context`, `seed_result_context`, `paper_library_context`,
`triage_matched_context`, `triage_synthesized_context`,
`llm_verified_context`, `claim_stub`, `curated_claim`,
`exploratory_claim`, and `known_study_context`.

## Revalidation Rules

Contexts should be treated as needing revalidation unless they are already
curated evidence and do not trigger audit flags. The first audit flag is
`possible_acronym_collision`, intended to catch short labels such as `DMT`,
`DOI`, `DOM`, `DOB`, `MDA`, and similarly ambiguous target labels.

The flag is conservative. It does not prove a row is wrong. It marks rows that
deserve a human or stricter automated check before they are used as trusted KG
edges.

## Promotion Plan

After rebuilding the provenance audit, build the promotion plan:

```bash
python pipeline/validate/build_context_promotion_plan.py
```

Default outputs:

- `data/processed/context_promotion_plan.json`
- `data/processed/context_promotion_worklist.csv`
- `data/processed/context_edge_rollup.json`
- `data/processed/context_promotion_summary.json`

The plan converts each `DOI + compound + target/indication` context into a
next action:

- `retain_in_curated_kg`: already curated evidence and no blocking audit flag
- `review_possible_acronym_or_entity_collision`: blocked until the short label
  or entity match is rechecked
- `curate_existing_claim_stub`: a claim stub exists but is not promoted
- `review_exploratory_claim_before_public_kg`: evidence exists only in the
  exploratory layer
- `extract_structured_claim_from_full_text`: screened context with local PDF
- `obtain_full_text_or_extract_abstract_only_claim`: screened context without a
  local PDF
- `screen_candidate_context`: discovered context that has not been screened

The edge rollup aggregates multiple papers into one compound-target or
compound-indication edge status. This is the bridge between broad search
coverage and the public KG: an edge can be visible as a gap or candidate before
it becomes a verified KG edge, but only `verified_evidence` should count as
public evidence by default.

The full plan, worklist CSV, and edge rollup are generated artifacts and may be
large. Keep the summary file for review, and regenerate the full artifacts from
the audit when needed.

## Stage Queues

Export actionable queues from the promotion plan:

```bash
python pipeline/validate/export_context_promotion_queues.py
```

Default outputs:

- `data/processed/context_queue_manifest.json`
- `data/processed/context_queues/*.csv`
- `data/raw/doi_queue.<dataset>.context_<stage>.txt`

The generated DOI queues preserve `doi, compound, entity, study_title,
study_year` in the same CSV-style format used by existing DOI queue scripts.
The richer stage CSVs preserve the original `context_id`, source artifacts, and
blocking flags.

Suggested queue order:

1. `noise_review`: resolve possible acronym/entity collisions first.
2. `curation_review`: finish existing stubs before creating duplicate work.
3. `full_text_extraction_ready`: extract structured evidence from local PDFs.
4. `screened_needs_pdf_or_abstract_extraction`: acquire PDFs or explicitly
   mark abstract-only evidence.
5. `abstract_screening_needed`: screen the broader candidate pool.

## Living Update Loop

1. Run discovery with a versioned search manifest.
2. Run the DOI add gate and send only new DOI rows downstream.
3. Rebuild the corpus/context audit.
4. Build the context promotion plan.
5. Export stage-specific promotion queues.
6. Screen candidate contexts and extract verified evidence.
7. Promote only validated rows into curated claims.
8. Export the KG and publish a release manifest with counts, hashes, and audit
   deltas.

This makes updates incremental: new searches fill gaps, while the existing DOI
corpus remains reusable and traceable.
