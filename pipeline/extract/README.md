# Extract: Promote Ready Stubs

This step promotes curated-ready rows from processed stub files into curated
datasets, enforcing schema rules before write.

## Workflow
1. Generate stubs from DOI queue (`pipeline/ingest/seed_from_dois.py`).
2. Curate stubs in `data/processed/*_claim_stubs.json`:
   - fill required fields
   - add `authors`
   - set `stub_status` to `ready_for_promotion`
3. Run promotion in dry-run mode (default) to see blockers.
4. Run with `--apply` to write curated JSON/CSV and remove promoted stubs.

## Commands
Mechanistic dry run:
`python pipeline/extract/promote_ready_stubs.py --dataset mechanistic`

Mechanistic apply:
`python pipeline/extract/promote_ready_stubs.py --dataset mechanistic --apply`

Disorder dry run:
`python pipeline/extract/promote_ready_stubs.py --dataset disorder`

Disorder apply:
`python pipeline/extract/promote_ready_stubs.py --dataset disorder --apply`

## Reports
- `data/processed/promotion_report_mechanistic.json`
- `data/processed/promotion_report_disorder.json`

## Notes
- Rows that match existing curated signatures are not promoted; their
  `stub_status` becomes `duplicate_existing` on apply.
- Rows failing required fields/types/enums are blocked and listed in report
  errors.
