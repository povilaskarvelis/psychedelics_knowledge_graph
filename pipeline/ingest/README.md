# Ingest and Metadata Enrichment

The ingestion stage starts from the canonical paper corpus at
`data/processed/corpus/candidate_papers.parquet`. The standard upstream living
search is implemented in `pipeline/discovery/`; historical dataset-specific
search, DOI-gating, and paper-library builders remain retired.

This stage enriches existing corpus rows with bibliographic metadata,
publication types, open-access status, and candidate full-text links. It does
not classify papers or create graph evidence.

For new literature, first complete and promote a discovery run. Promotion
writes a scoped `new_candidate_dois.txt` file that can be passed directly to the
metadata command below.

## Metadata Enrichment

### Large discovery updates: batch abstracts first

For a large promoted discovery run, recover missing abstracts with provider
batch endpoints before deterministic pre-screening or per-record fallback
lookups:

```bash
python pipeline/ingest/run_batch_abstract_enrichment.py \
  --run-id batch_abstract_enrichment_YYYYMMDD \
  --doi-file data/processed/discovery/runs/<discovery_run_id>/new_candidate_dois.txt
```

The command:

- freezes the DOI-scoped missing-abstract cohort in the run directory;
- retrieves PubMed and PMC records in batches, then queries Semantic Scholar in batches
  of at most 500 for records still lacking an abstract;
- supports a resumable Crossref DOI pass with `--providers crossref`; Crossref
  requests use the configured polite-pool rate and at most three coordinated
  workers, with checkpoints every `--crossref-batch-size` records;
- checkpoints each successful provider batch and automatically reuses the
  checkpoint when the same run command is resumed;
- never overwrites an existing abstract;
- backs up `paper_metadata_enrichment.parquet` before an atomic merge; and
- records provider attempts, identifier mismatches, recovery counts, and the
  final metadata-table checksum in run artifacts under
  `data/processed/corpus/metadata_enrichment_runs/<run_id>/`.

Use `--dry-run` to inspect the eligible scope without network requests, or
`--no-merge` for a retrieval-only pilot. Reusing a run ID with different
inputs or batch settings is refused; choose a new run ID instead. Records that
remain abstractless are handled by the following deterministic pre-screen as
`exclude_no_usable_abstract` rather than being sent to model screening.

To run a measured Crossref recovery stage after the default providers, use a
new run ID. The command freezes only records still missing abstracts at the
start of this stage:

```bash
python pipeline/ingest/run_batch_abstract_enrichment.py \
  --run-id batch_abstract_enrichment_crossref_YYYYMMDD \
  --providers crossref
```

### Abstract contamination repair

After a discovery promotion—or before rebuilding a model-screening queue—run
the resumable quality repair over the corpus:

```bash
python pipeline/ingest/repair_abstract_contamination.py \
  --run-id abstract_contamination_repair_YYYYMMDD
```

Use `--doi-file` to restrict the audit to an update cohort and `--audit-only`
to materialize the suspect set without provider calls. The repair applies a
provider-aware quality policy shared with discovery promotion, preserves the
affected pre-repair rows, queries PubMed/PMC/Semantic Scholar/Crossref with
checkpoints, rejects contaminated recovery values, and atomically synchronizes
the candidate and metadata tables. Clean recovered abstracts replace bad
values; unresolved full text or container text is blanked so it cannot reach
screening. The detailed scope, provider outcomes, rejected recovery fields,
actions, backups, and checksums remain under the run directory.

Publication-type and open-access/PDF enrichment should normally wait until
after screening for a very large discovery update. The promoted discovery
records already carry provider publication types, while access resolution is
most useful for retained records.

### Small updates and per-record fallbacks

Run the role-aware enrichment sequence:

```bash
python pipeline/ingest/run_standard_metadata_enrichment.py \
  --write-every 100 \
  --progress-every 100
```

Use `--doi-file <path>` for a small scoped update. The runner writes metadata to
`data/processed/corpus/paper_metadata_enrichment.parquet` and leaves the
canonical candidate corpus unchanged.

The provider roles are intentionally separate:

- core bibliographic metadata and abstracts: PubMed, PMC, OpenAlex, Crossref,
  and Semantic Scholar fallbacks;
- publication-type labels: PubMed;
- open-access and PDF-link discovery: Unpaywall, OpenAlex, and PMC.

Run the lower-level metadata command when only one part of the workflow is
needed:

```bash
python pipeline/ingest/enrich_paper_metadata.py \
  --papers-table data/processed/corpus/candidate_papers.parquet \
  --output-table data/processed/corpus/paper_metadata_enrichment.parquet \
  --only-missing-abstract \
  --retry-missing-metadata
```

To refresh only access metadata:

```bash
python pipeline/ingest/refresh_open_access_links.py \
  --only-retained-secondary \
  --only-missing-pdf-url \
  --provider-order unpaywall,openalex,pmc
```

PDF retrieval begins after extraction assignments are built and belongs to
`pipeline/fulltext/`.
