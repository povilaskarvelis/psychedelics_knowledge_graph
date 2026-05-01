# Enrichment Stages

Standalone enrichment scripts add external metadata without mutating the live
metadata-sync outputs unless a script explicitly says it applies changes.

## Trial Registry Enrichment

`enrich_trial_registries.py` enriches screened disorder candidates that already
have trial registry identifiers. It currently fetches NCT records from
ClinicalTrials.gov v2 and reports other registry IDs as unsupported-but-kept, so
they are visible for later ISRCTN/EudraCT/etc. adapters.

Light candidate pass after abstract screening and metadata sync:

```bash
python pipeline/enrich/enrich_trial_registries.py --dataset disorder
```

Stricter pass after full-text assessment has labeled primary/original empirical
rows in stubs or curated data:

```bash
python pipeline/enrich/enrich_trial_registries.py \
  --dataset disorder \
  --require-primary-source
```

Inputs:
- `data/processed/paper_library_disorder.json`
- `data/processed/llm_abstract_screening_report_disorder.json`
- `data/raw/doi_queue.disorder.llm_relevant.txt`
- `data/raw/doi_queue.disorder.llm_uncertain.txt`
- `data/processed/disorder_claim_stubs.json` and
  `data/curated/disorder_claims.json` when using `--require-primary-source`

Outputs:
- `data/processed/trial_registry_cache_disorder.json`
- `data/processed/trial_registry_enrichment_disorder.json`
- `data/processed/trial_registry_enrichment_disorder.csv`

The cache stores normalized registry fields such as trial phase, enrollment,
status, conditions, interventions, arms, outcomes, dates, sponsors,
eligibility, and registry URL. Raw ClinicalTrials.gov payloads are retained by
default; pass `--omit-raw` for a smaller cache.

## Author Backfill

Backfill missing `authors` in curated datasets (`claims.*`, `disorder_claims.*`)
from a DOI->authors lookup.

Dry run report only:

```bash
python pipeline/enrich/backfill_authors_from_lookup.py
```

Apply updates to curated JSON/CSV:

```bash
python pipeline/enrich/backfill_authors_from_lookup.py --apply
```

Inputs:
- `data/raw/doi_authors_lookup.json`
- `data/curated/claims.json`
- `data/curated/disorder_claims.json`

Outputs:
- `data/processed/authors_backfill_report.json`
- updated curated JSON/CSV files with `authors`
