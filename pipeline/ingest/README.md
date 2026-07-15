# Ingest and Metadata Enrichment

The operational pipeline starts from the canonical paper corpus at
`data/processed/corpus/candidate_papers.parquet`. Historical dataset-specific
search, DOI-gating, and paper-library builders have been retired.

This stage enriches existing corpus rows with bibliographic metadata,
publication types, open-access status, and candidate full-text links. It does
not classify papers or create graph evidence.

## Metadata Enrichment

Run the role-aware enrichment sequence:

```bash
python pipeline/ingest/run_standard_metadata_enrichment.py \
  --write-every 100 \
  --progress-every 100
```

Use `--doi-file <path>` for a scoped update. The runner writes metadata to
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
