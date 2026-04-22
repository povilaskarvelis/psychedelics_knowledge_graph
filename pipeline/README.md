# Pipeline

Deterministic ETL for building a provenance-aware psychedelics evidence graph.
The current workflow is optimized for high-recall literature discovery, explicit
screening provenance, conservative claim extraction, and schema-validated graph
outputs.

## Stages
1. **Discover**: search multiple literature sources and write DOI queues.
2. **Sync metadata**: build the paper library from PubMed, PMC, Unpaywall,
   Crossref, and OpenAlex metadata.
3. **Triage**: classify relevance and write triage-relevant DOI-context queues.
4. **Acquire PDFs**: download legal OA PDFs only for triage-relevant papers.
5. **Seed stubs**: create one claim stub per DOI + compound + target/disorder
   context.
6. **Autofill claims**: fill fields from abstracts first, then PDFs.
7. **Promote**: move schema-clean rows into curated claim datasets.
8. **Validate and publish**: run validation and export graph payloads.

Detailed stage docs:
- Ingest/discovery/PDF acquisition: `pipeline/ingest/README.md`
- Triage/autofill/review queue: `pipeline/review/README.md`
- Promotion: `pipeline/extract/README.md`
- Validation: `pipeline/validate/`
- Publishing: `pipeline/publish/README.md`

## Local Config
Keep credentials in the ignored overlay file:

```bash
cp pipeline/config.local.example.yaml pipeline/config.local.yaml
chmod 600 pipeline/config.local.yaml
```

Set whichever services you have:
- `openalex.api_key`
- `pubmed.email`
- `pubmed.api_key`
- `crossref.email`
- `unpaywall.email`
- `semantic_scholar.api_key` (optional; the pipeline can run without it)

Scripts that use `pipeline/config.example.yaml` automatically overlay
`pipeline/config.local.yaml` when it exists.

## Recommended High-Recall Run

### 1. Discovery
Run broad discovery, then a higher-recall expansion pass. Keep one dataset per
terminal when monitoring long runs.

```bash
python pipeline/ingest/run_extensive_search.py \
  --dataset mechanistic \
  --provider hybrid \
  --expand-seeds-from-config \
  --auto-template-mode broad \
  --auto-max-pairs 1400 \
  --auto-max-seeds 1800 \
  --balanced-seed-profile coverage \
  --max-results-per-seed 80 \
  --max-results 8000 \
  --semantic-scholar-rps 0.5 \
  --openalex-rps 3.0 \
  --max-retries 3 \
  --discover-only
```

Use `--dataset disorder` for disorder discovery. Use `--provider comprehensive`
for a final recall-focused pass when PubMed/PMC/Crossref coverage should be
included during discovery.

### 2. Recall Audit
The benchmark manifest is `data/raw/benchmark_manifest.json`.

```bash
python pipeline/ingest/recall_audit.py --dataset mechanistic --min-discovered 95 --fail-under-threshold
python pipeline/ingest/recall_audit.py --dataset disorder --min-discovered 95 --fail-under-threshold
```

If recall misses the threshold, improve seeds/synonyms before syncing and
extracting claims.

### 3. Metadata Sync
Run metadata first, without downloads.

```bash
python pipeline/ingest/sync_paper_library.py \
  --dataset mechanistic \
  --skip-download \
  --checkpoint-every 100 \
  --progress-every 100
```

Default metadata provider order is:

```text
pubmed, pmc, unpaywall, crossref, openalex
```

This gives biomedical abstracts/PMCID signals first, OA/PDF resolution from
Unpaywall, then broad metadata fallbacks.

### 4. Triage
Triage produces `data/raw/doi_queue.<dataset>.triage_relevant.txt`.

```bash
python pipeline/review/triage_paper_library.py --dataset mechanistic
python pipeline/review/triage_paper_library.py --dataset disorder
```

Triage is recall-safe by default:
- benchmark and curated DOI-contexts are protected
- stale discovery contexts can be synthesized from title/abstract matches
- reports include `screening_status`, rescue reasons, and protected/synthesized
  context counts

### 5. PDF Acquisition
Download only from the triage-relevant queue.

```bash
python pipeline/ingest/sync_paper_library.py \
  --dataset mechanistic \
  --doi-file data/raw/doi_queue.mechanistic.triage_relevant.txt \
  --metadata-provider-order pubmed,pmc,unpaywall,crossref,openalex \
  --max-retries 1 \
  --max-retry-after-sec 30 \
  --timeout-sec 30 \
  --checkpoint-every 100 \
  --progress-every 100
```

The downloader tries multiple legal candidates where available, including PMC /
Europe PMC, Unpaywall, OpenAlex, and publisher/repository URLs. Use
`pipeline/ingest/retry_pdf_downloads.py` for targeted retry queues instead of
rerunning the full sync.

### 6. Seed Context-Level Stubs
Generate stubs from the triage-relevant queues. Stubs are deduplicated by
`DOI + compound + target/disorder`, not DOI alone, so multi-context papers
produce all graph-relevant edges.

```bash
python pipeline/ingest/seed_from_dois.py \
  --dataset mechanistic \
  --doi-file data/raw/doi_queue.mechanistic.triage_relevant.txt \
  --replace

python pipeline/ingest/seed_from_dois.py \
  --dataset disorder \
  --doi-file data/raw/doi_queue.disorder.triage_relevant.txt \
  --replace
```

### 7. Abstract-First Autofill
Run abstract/metadata extraction for all triaged stubs.

```bash
python pipeline/review/autofill_stubs_from_abstracts.py --dataset mechanistic --mark-ready --apply
python pipeline/review/autofill_stubs_from_abstracts.py --dataset disorder --mark-ready --apply
```

Abstract-only disorder rows can become ready when required outcome/provenance
fields are present. Mechanistic rows usually still need PDF evidence for
quantitative affinity fields.

### 8. PDF Autofill
PDF-heavy scripts auto-run inside the `psychkg-pdf` conda environment when it
exists. See `pipeline/review/README.md` for one-time setup.

```bash
python pipeline/review/autofill_mechanistic_from_pdfs.py \
  --dataset mechanistic \
  --mark-ready \
  --apply \
  --progress-every 100

python pipeline/review/autofill_disorder_from_pdfs.py \
  --dataset disorder \
  --mark-ready \
  --apply \
  --progress-every 100
```

### 9. Review Queue
Inspect blockers before promotion.

```bash
python pipeline/review/curation_queue.py --dataset mechanistic
python pipeline/review/curation_queue.py --dataset disorder
```

Reports:
- `data/processed/review_queue_mechanistic.json`
- `data/processed/review_queue_disorder.json`

### 10. Promote, Validate, Export
Dry-run promotion first.

```bash
python pipeline/extract/promote_ready_stubs.py --dataset mechanistic
python pipeline/extract/promote_ready_stubs.py --dataset disorder
```

Apply when dry-run blockers are acceptable:

```bash
python pipeline/extract/promote_ready_stubs.py --dataset mechanistic --apply
python pipeline/extract/promote_ready_stubs.py --dataset disorder --apply
```

Then validate and export:

```bash
python pipeline/validate/validate_claims.py
python pipeline/publish/export_graph_payload.py
```

## Key Outputs
- `data/raw/doi_queue.<dataset>.discovered.txt`
- `data/raw/doi_queue.<dataset>.triage_relevant.txt`
- `data/processed/discovery_report_<dataset>.json`
- `data/processed/discovery_ledger_<dataset>.json`
- `data/processed/paper_library_<dataset>.json`
- `data/processed/paper_inventory_<dataset>.md`
- `data/processed/triage_report_<dataset>.json`
- `data/processed/*_claim_stubs.json`
- `data/processed/abstract_autofill_report_<dataset>.json`
- `data/processed/pdf_autofill_report_<dataset>.json`
- `data/processed/promotion_report_<dataset>.json`
- `data/processed/validation_report.json`
- `data/processed/graph_payload_*.json`

## Evidence Rules
- Provenance fields are mandatory: `source_type`, `access_level`,
  `evidence_location`, `evidence_locator`, and `study_design`.
- Main curated rows should be primary evidence. Reviews, protocols, conference
  abstracts, and weak/secondary evidence should remain blocked or be routed to
  exploratory outputs.
- Disorder labels are canonicalized with `schema/disorder_canonicalization.json`.
- Promotion prunes stale curated DOI-contexts that no longer appear in the
  latest triage matched contexts.
