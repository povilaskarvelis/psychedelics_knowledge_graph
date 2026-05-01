# Pipeline

Provenance-aware ETL for building a psychedelics evidence graph. The current
workflow combines deterministic retrieval/validation with LLM-assisted abstract
screening and full-text evidence assessment. It is optimized for high-recall
literature discovery, explicit screening provenance, conservative extraction,
and schema-validated graph outputs.

## Stages
1. **Discover**: search multiple literature sources and write DOI queues.
2. **Sync metadata**: build the paper library from PubMed, PMC, Unpaywall,
   Crossref, and OpenAlex metadata.
3. **Semantic abstract screening**: run a deterministic no-signal pre-screen,
   then use a local LLM only to classify abstract-level relevance and
   quote-supported compound/entity contexts for retained rows.
4. **Acquire PDFs**: download legal OA PDFs for relevant and uncertain papers.
5. **Full-text evidence assessment**: convert local PDFs, assess full-text
   eligibility/source family, and extract structured study/result variables.
6. **Seed stubs**: create one claim stub per DOI + compound + target/disorder
   context.
7. **Autofill claims**: fill fields from abstracts first, then PDFs.
8. **Promote**: move schema-clean rows into curated claim datasets.
9. **Validate and publish**: run validation and export graph payloads.

Detailed stage docs:
- Ingest/discovery/PDF acquisition: `pipeline/ingest/README.md`
- Full-text conversion: `pipeline/fulltext/README.md`
- Triage/autofill/review queue: `pipeline/review/README.md`
- Promotion: `pipeline/extract/README.md`
- Validation: `pipeline/validate/`
- Publishing: `pipeline/publish/README.md`

Run the non-destructive full-text provenance stage with:

```bash
python pipeline/fulltext/run_fulltext_provenance.py --dataset all --limit 50
```

This converts missing full-text artifacts, rebuilds provenance repair reports,
and exports curator review CSVs. It does not apply curated-claim edits.

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
for a final search-completeness pass when PubMed/PMC/Crossref coverage should
be included during discovery.

### 2. Search Completeness Check
The known relevant study set is stored at `data/raw/benchmark_manifest.json`.
The filename is retained for compatibility with older commands, but project
documentation should treat it as a literature-search completeness aid rather
than as a definitive claim that every relevant study has been found.
See [`docs/search_completeness.md`](../docs/search_completeness.md) for the
terminology and maintenance policy.

```bash
python pipeline/ingest/recall_audit.py --dataset mechanistic --min-discovered 95 --fail-under-threshold
python pipeline/ingest/recall_audit.py --dataset disorder --min-discovered 95 --fail-under-threshold
```

If the completeness check misses the threshold, revise seeds/synonyms or
document why the missed study is outside scope or unavailable in the selected
sources before syncing and extracting claims.

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
pubmed, pmc, unpaywall, crossref, openalex, semantic_scholar
```

This gives biomedical abstracts/PMCID signals first, OA/PDF resolution from
Unpaywall, then broad metadata fallbacks. To target missing abstracts without
touching PDFs, rerun only missing metadata with abstract-focused providers:

```bash
python pipeline/ingest/sync_paper_library.py \
  --dataset mechanistic \
  --skip-download \
  --refresh-missing-metadata \
  --metadata-provider-order semantic_scholar,openalex,pubmed,pmc,crossref \
  --timeout-sec 30 \
  --max-retry-after-sec 30 \
  --checkpoint-every 100 \
  --progress-every 100
```

### 4. Local LLM Abstract Screening
Run semantic screening before PDF acquisition. The current strategy is a
high-recall cascade: deterministic pre-screening removes obvious no-signal rows,
then `qwen3:14b` reviews retained abstracts for relevance only. Source family,
paper type, study design, evidence strength, and claim details are deferred to
   full-text evidence assessment or, when full text is unavailable, an explicit
   abstract-only evidence fallback.

First run the deterministic pre-screen over the synced library:

```bash
python pipeline/review/run_local_llm_abstract_screening.py \
  --dataset mechanistic \
  --deterministic-prescreen \
  --deterministic-prescreen-only \
  --only-with-abstract \
  --only-undownloaded

python pipeline/review/run_local_llm_abstract_screening.py \
  --dataset disorder \
  --deterministic-prescreen \
  --deterministic-prescreen-only \
  --only-with-abstract \
  --only-undownloaded
```

Then run LLM screening only on the retained DOI queue:

```bash
python pipeline/review/run_local_llm_abstract_screening.py \
  --dataset mechanistic \
  --doi-file data/raw/doi_queue.mechanistic.deterministic_prescreen_retained.txt \
  --model qwen3:14b \
  --only-with-abstract \
  --continue-on-error \
  --timeout-sec 0 \
  --resume-from-checkpoint \
  --num-ctx 4096

python pipeline/review/run_local_llm_abstract_screening.py \
  --dataset disorder \
  --doi-file data/raw/doi_queue.disorder.deterministic_prescreen_retained.txt \
  --model qwen3:14b \
  --only-with-abstract \
  --continue-on-error \
  --timeout-sec 0 \
  --resume-from-checkpoint \
  --num-ctx 4096
```

While a long local-model run is in progress, materialize whatever has already
landed in the checkpoint into the normal JSON/CSV/DOI queue outputs without
calling the model again:

```bash
python pipeline/review/run_local_llm_abstract_screening.py \
  --dataset mechanistic \
  --doi-file data/raw/doi_queue.mechanistic.deterministic_prescreen_retained.txt \
  --materialize-checkpoint-only \
  --only-with-abstract
```

Primary outputs:
- `data/processed/deterministic_prescreen_report_<dataset>.json`
- `data/raw/doi_queue.<dataset>.deterministic_prescreen_retained.txt`
- `data/raw/doi_queue.<dataset>.deterministic_prescreen_excluded.txt`
- `data/raw/doi_queue.<dataset>.llm_fulltext_candidates.txt`
- `data/raw/doi_queue.<dataset>.llm_relevant.txt`
- `data/raw/doi_queue.<dataset>.llm_uncertain.txt`

During calibration, run small batches first with `--limit 25` and inspect the
CSV report before treating the LLM queue as the default PDF-download gate. Rows
skipped by the deterministic pre-screen are marked
`screening_path=deterministic_excluded`.

After disorder metadata sync and abstract screening have produced relevant or
uncertain rows, registry enrichment can run independently of the live metadata
sync:

```bash
python pipeline/enrich/enrich_trial_registries.py --dataset disorder
```

Add `--require-primary-source` after full-text assessment when you want the
registry pass limited to rows already labeled as original empirical/primary
evidence.

For relevant/uncertain papers that cannot be downloaded or converted to full
text, run abstract-only full-text-assessment fallback after acquisition
attempts:

```bash
python pipeline/fulltext/run_local_llm_evidence_assessment.py \
  --input data/processed/llm_abstract_screening_report_disorder.json \
  --evidence-mode abstract_only \
  --only-without-fulltext \
  --only-with-abstract \
  --model qwen3:14b \
  --continue-on-error \
  --timeout-sec 0
```

### Optional Legacy Heuristic Triage Audit
Rule-based triage produces `data/raw/doi_queue.<dataset>.triage_relevant.txt`.
This is no longer part of the default screening path. The abstract screener only
loads an old triage report if you explicitly pass `--use-heuristic-audit` or
`--triage-report-json`.

```bash
python pipeline/review/triage_paper_library.py --dataset mechanistic
python pipeline/review/triage_paper_library.py --dataset disorder
```

Triage is retrieval-safe by default:
- known-study and curated DOI-contexts are protected
- stale discovery contexts can be synthesized from title/abstract matches
- reports include `screening_status`, rescue reasons, and protected/synthesized
  context counts

### 5. PDF Acquisition
Download from the LLM full-text candidate queue.

```bash
python pipeline/ingest/sync_paper_library.py \
  --dataset mechanistic \
  --doi-file data/raw/doi_queue.mechanistic.llm_fulltext_candidates.txt \
  --metadata-provider-order pubmed,pmc,unpaywall,crossref,openalex,semantic_scholar \
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
Generate stubs from the context-verified queues. Stubs are deduplicated by
`DOI + compound + target/disorder`, not DOI alone, so multi-context papers
produce all graph-relevant edges.

```bash
python pipeline/ingest/seed_from_dois.py \
  --dataset mechanistic \
  --doi-file data/raw/doi_queue.mechanistic.llm_relevant.txt \
  --replace

python pipeline/ingest/seed_from_dois.py \
  --dataset disorder \
  --doi-file data/raw/doi_queue.disorder.llm_relevant.txt \
  --replace
```

### 7. Abstract-First Autofill
Run abstract/metadata extraction for all screened stubs.

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
- `data/raw/doi_queue.<dataset>.llm_fulltext_candidates.txt`
- `data/raw/doi_queue.<dataset>.llm_relevant.txt`
- `data/raw/doi_queue.<dataset>.llm_uncertain.txt`
- `data/processed/discovery_report_<dataset>.json`
- `data/processed/discovery_ledger_<dataset>.json`
- `data/processed/paper_library_<dataset>.json`
- `data/processed/paper_inventory_<dataset>.md`
- `data/processed/llm_abstract_screening_report_<dataset>.json`
- `data/processed/*_claim_stubs.json`
- `data/processed/abstract_autofill_report_<dataset>.json`
- `data/processed/pdf_autofill_report_<dataset>.json`
- `data/processed/promotion_report_<dataset>.json`
- `data/processed/validation_report.json`
- `data/processed/graph_payload_*.json`

## Evidence Rules
- Provenance fields are mandatory: `source_type`, `access_level`,
  `evidence_location`, `evidence_locator`, and `study_design`.
- Bibliographic/study fields such as journal, publication type/date, ISSNs,
  publisher, trial registry IDs, MeSH/keywords, funders/grants, publication
  relations, sample size, comparator/intervention, outcomes, effect sizes,
  funding, conflicts of interest, and risk-of-bias notes should be preserved
  whenever available.
- Main curated rows should be primary evidence. Reviews, protocols, conference
  abstracts, and weak/secondary evidence should remain blocked or be routed to
  exploratory outputs.
- Disorder labels are canonicalized with `schema/disorder_canonicalization.json`.
- Promotion does not consult old heuristic triage reports unless
  `--prune-by-triage-report` or `--triage-report-json` is supplied explicitly.
  This keeps the live heuristic-era graph from being silently pruned while the
  slower LLM-based pipeline is rerun.
