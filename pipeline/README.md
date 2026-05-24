# Pipeline

This pipeline builds a reproducible literature corpus for the psychedelics
knowledge graph, screens papers for relevance, retrieves available full text,
and prepares clean inputs for structured claim extraction.

The pipeline should be described by its actions, not by historical run labels.
Run labels such as `boolean_full_v1` or `pairwise_direct_v1` are provenance
labels for specific searches, not pipeline stages.

## Canonical Stages

1. **Search planning**: generate grouped search modules and direct pair-search
   files from the configured compound, target, and indication registries.
2. **Literature discovery**: query literature providers and write discovered
   DOI queues plus provider-specific reports.
3. **DOI add gate**: normalize DOIs and add only papers that are not already in
   the paper corpus.
4. **Metadata sync**: collect bibliographic metadata, abstracts, identifiers,
   and open-access/PDF signals.
5. **Abstract screening**: use deterministic title/abstract pre-screening only
   for obvious no-signal rows, then use a local LLM to classify abstract-level
   relevance.
6. **PDF retrieval**: download legal open-access PDFs for papers screened as
   relevant or uncertain.
7. **Full-text conversion**: convert local PDFs into structured full-text
   artifacts with reproducible provenance.
8. **Extraction preparation**: combine screened papers into DOI-level
   extraction cohorts from the corpus manifest and build full-text packet files.
9. **Claim extraction**: extract compound-target and compound-indication claims
   from full text, with abstract-only extraction reserved for papers without
   obtainable full text.
10. **Validation and publishing**: validate extracted evidence, resolve
    conflicts/curation flags, and export graph payloads.

Older stub/autofill/promotion scripts are still available for maintaining the
first-generation graph, but they are no longer the canonical extraction path.

## Main Commands

### Search Planning

Build the current search files from configured registries:

```bash
python pipeline/ingest/build_boolean_search_modules.py --dataset all --run-id search_2026_05
python pipeline/ingest/build_comprehensive_search_plan.py --dataset all --profile standard --run-id search_2026_05
```

The script names still contain some older implementation wording. In methods
text, describe these as **grouped search modules** and **direct pair searches**.
If `--run-id` is omitted, scripts write to the neutral
`data/raw/search_strategies/literature_search/` run directory.

### Literature Discovery

Run grouped search modules or direct pair-search files through
`discover_literature.py` or the batch runners in `pipeline/ingest/`.

Example:

```bash
python pipeline/ingest/discover_literature.py \
  --dataset mechanistic \
  --provider pubmed \
  --seed-file data/raw/search_strategies/search_2026_05/grouped_modules/mechanistic_grouped_pubmed_seeds.csv \
  --max-results-per-seed 500 \
  --max-results 0
```

### DOI Add Gate

```bash
python pipeline/ingest/add_new_dois.py \
  --dataset mechanistic \
  --input data/raw/doi_queue.mechanistic.discovered.txt
```

This is DOI-level. Rediscovered papers are logged for provenance but are not
processed downstream as new papers.

### Metadata Sync

Run metadata first without downloading PDFs:

```bash
python pipeline/ingest/sync_paper_library.py \
  --dataset mechanistic \
  --skip-download \
  --checkpoint-every 100 \
  --progress-every 100
```

Default metadata sources are PubMed, PMC, Unpaywall, Crossref, OpenAlex, and
Semantic Scholar.

### Abstract Screening

First run deterministic pre-screening:

```bash
python pipeline/review/run_local_llm_abstract_screening.py \
  --dataset mechanistic \
  --deterministic-prescreen \
  --deterministic-prescreen-only \
  --only-with-abstract \
  --only-undownloaded
```

Then run LLM screening on the retained DOI queue:

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
```

For batch-specific screening, use `--prescreen-output-label <run_label>` and
explicit report/queue paths. The label is provenance, not a new pipeline stage.

### PDF Retrieval

Download PDFs only for papers retained by abstract screening:

```bash
python pipeline/ingest/sync_paper_library.py \
  --dataset mechanistic \
  --doi-file data/raw/doi_queue.mechanistic.llm_fulltext_candidates.txt \
  --metadata-provider-order pubmed,pmc,unpaywall,crossref,openalex,semantic_scholar \
  --checkpoint-every 100 \
  --progress-every 100
```

### Full-Text Conversion

```bash
python pipeline/fulltext/convert_pdfs.py \
  --dataset mechanistic \
  --doi-file data/raw/doi_queue.mechanistic.llm_fulltext_candidates.txt \
  --backend grobid \
  --only-missing-artifacts
```

### Extraction Preparation

Build the DOI-level extraction cohort from the corpus manifest:

```bash
python pipeline/extract/prepare_extraction_inputs.py --dataset all
```

Build full-text packet files from papers that already have converted full text:

```bash
python pipeline/fulltext/build_llm_evidence_packets.py \
  --dataset mechanistic \
  --doi-file data/raw/doi_queue.mechanistic.extraction_fulltext_ready.txt \
  --out-jsonl data/processed/extraction/mechanistic_fulltext_packets.jsonl \
  --report-json data/processed/extraction/mechanistic_fulltext_packets_report.json \
  --omit-section-text \
  --omit-candidate-contexts \
  --packet-profile lean_primary \
  --max-references 0
```

Repeat with `--dataset disorder` and the disorder DOI queue/output paths.

## Canonical Outputs

- `data/raw/doi_queue.<dataset>.discovered.txt`
- `data/raw/doi_queue.<dataset>.new.txt`
- `data/processed/discovery_report_<dataset>.json`
- `data/processed/discovery_ledger_<dataset>.json`
- `data/processed/paper_library_<dataset>.json`
- `data/processed/paper_inventory_<dataset>.md`
- `data/processed/deterministic_prescreen_report_<dataset>*.json`
- `data/processed/llm_abstract_screening_report_<dataset>*.json`
- `data/raw/doi_queue.<dataset>.llm_fulltext_candidates*.txt`
- `data/raw/doi_queue.<dataset>.llm_relevant*.txt`
- `data/raw/doi_queue.<dataset>.llm_uncertain*.txt`
- `data/processed/fulltext/<dataset>/*.json`
- `data/processed/extraction/*_extraction_candidates.jsonl`
- `data/processed/extraction/*_fulltext_packets.jsonl`
- `data/processed/extraction/extraction_readiness_report.md`

## Run Labels

Use run labels to separate artifacts from different searches or batches:

- Good labels describe the run: `grouped_search_2026_05`,
  `direct_pairs_2026_05`, `monthly_update_2026_06`.
- Historical labels such as `boolean_full_v1`, `pairwise_direct_v1`, and
  `comprehensive_baseline_v1` are retained only so existing outputs remain
  reproducible.
- Do not use run labels as public method names.

## Corpus Manifest

`data/processed/corpus_manifest.json` is the inclusion list for regenerated
extraction inputs and methods-page graph outputs. Add completed
abstract-screening reports there when a new search or update run should become
part of the current corpus.

The raw run reports remain append-only provenance. The files under
`data/processed/extraction/` are current views regenerated from the manifest,
paper library, and full-text artifacts.

## Local Config

Keep credentials in the ignored local config:

```bash
cp pipeline/config.local.example.yaml pipeline/config.local.yaml
chmod 600 pipeline/config.local.yaml
```

Common settings:

- `openalex.api_key`
- `pubmed.email`
- `pubmed.api_key`
- `crossref.email`
- `unpaywall.email`
- `semantic_scholar.api_key`

Scripts that use `pipeline/config.example.yaml` automatically overlay
`pipeline/config.local.yaml` when it exists.

## Legacy Maintenance Path

The first-generation graph used context-level stubs, autofill scripts, and
promotion into curated claim files. Those tools remain under `pipeline/review/`
and `pipeline/extract/promote_ready_stubs.py` for maintenance and comparison,
but new KG evidence should flow through extraction candidates and extraction
packets first.
