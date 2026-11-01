# Source identity

Engine code that records which text belongs to which paper. It contains no
field-specific terms. The design and its causes are in
[`docs/source_identity_2026-11-01.md`](../../docs/source_identity_2026-11-01.md).

## Decision file

`data/curated/source_identity_decisions.jsonl` holds one reviewed decision per
line. Each decision is about one paper, keyed by the candidate ledger's DOI key.

| Field | Content |
|---|---|
| `decision_id` | `sid-` and 20 hex characters, stable for the decision |
| `doi` | the paper |
| `target` | `{"kind": "record"}`, or an abstract or full text named by `sha256`, `pdf_sha256`, `document_doi`, `source_url` or `provider` |
| `verdict` | see below |
| `relation`, `related_doi` | for `version_of`: how the text's work relates to the paper (`pipeline/identity/works.py`) |
| `fields`, `clear_fields` | for `record_corrected`: the bibliographic values replaced or cleared |
| `basis`, `evidence`, `reviewer`, `decided_at` | why, from what, by whom, when |
| `supersedes` | ids of earlier decisions this one replaces |
| `origin`, `legacy` | for migrated decisions: the older file and its original fields |

Verdicts:

| Target | Verdicts |
|---|---|
| abstract or full text | `verified`, `version_of`, `not_this_work`, `wrong_kind` |
| record | `record_corrected`, `wrong_doi`, `hold` |

Rules:

- The file is append-only. A decision is changed by adding one that supersedes it.
- `register.py` validates every line, and pipeline runs never write the file.
- Earlier lines are kept byte for byte when decisions are appended.

## Commands

```bash
python -m pipeline.identity migrate
python -m pipeline.identity migrate --check
```

`migrate` copies the decisions still kept in older files into the decision
file:

- `pipeline/fulltext/source_identity_registry.json`;
- `pipeline/fulltext/source_identity_pdf_hash_registry.json`;
- the `hold_source_review` records in
  `pipeline/extract/manual_extraction_route_overrides.json`;
- `data/curated/paper_metadata_overrides.json`;
- the `source_not_verified` groups in
  `data/curated/graph_inclusion_disposition_overrides.json`;
- `data/curated/pdf_source_url_corrections.json`.

Migrated entries are regenerated on every run. Decisions added directly to the
file are kept. `--check` writes nothing and exits 1 when the file no longer
matches those sources. Run `migrate` after editing any of them.

The pipeline still reads the older files. Readers move to the decision file in
later steps (`audit`, `decide`, `apply`; §8 of the design document). Access
overrides and the DOI alias registry stay where they are: the first decides how
text is retrieved, and the second is the work registry, read through `works.py`.
