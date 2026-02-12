# Enrich: Author Backfill

Backfill missing `authors` in curated datasets (`claims.*`, `disorder_claims.*`)
from a DOI->authors lookup.

## Run
Dry run report only:
`python pipeline/enrich/backfill_authors_from_lookup.py`

Apply updates to curated JSON/CSV:
`python pipeline/enrich/backfill_authors_from_lookup.py --apply`

## Inputs
- `data/raw/doi_authors_lookup.json`
- `data/curated/claims.json`
- `data/curated/disorder_claims.json`

## Outputs
- `data/processed/authors_backfill_report.json`
- updated curated JSON/CSV files with `authors`

## Notes
- If a DOI is missing in lookup, fallback text is used.
- Edit lookup and rerun to replace unresolved author strings.
