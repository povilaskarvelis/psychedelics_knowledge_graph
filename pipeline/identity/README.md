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

## The rule

`verify.py` decides whether a text belongs to a paper. A text is verified
when an identifier taken from the source itself (a DOI, PMID or PMCID in the
document header or provider record) and the source's title both agree with the
paper. An identifier alone or a title alone leaves it unconfirmed.

`evidence.py` reads and compares the evidence:

- DOIs that say nothing about the paper are set aside: truncated or run-on
  parses of the paper's own DOI, and funder, ISSN, issue and placeholder DOIs.
  A run-on parse still prints the paper's full DOI and counts as it.
- The paper's DOI printed in the first pages confirms the paper when the
  parser read no other DOI as the document's own. When it read another, the
  text stays unconfirmed: that DOI may be a cited article's, or the paper's DOI
  may be on a cover sheet attached to another text. A preprint or repository
  DOI given as the document's own marks a version.
- Other DOIs printed in the first pages never contradict the paper, because
  page one also prints cited and related DOIs. When only the printed title
  agrees, they mark a page that may hold several items, such as an abstract
  book.
- A repository cover sheet describes the deposit, not the attached file. The
  audit checks the pages after it, from the PDF.
- Titles are compared with numbers kept: otherwise equal titles with different
  numbers are different editions, years or parts. A title without its subtitle
  agrees with the full title.
- A parsed title that is not the document's title (a journal or repository
  masthead, a cover-sheet notice, a section heading or letter-spaced text) is
  ignored unless it agrees with the paper's title. The paper's title printed
  at the start of the text then counts as the title.
- DOIs broken across lines are rejoined before they are read.
- Supplements and correction notices are not the article.

| Verdict | Meaning |
|---|---|
| `verified` | identifier and title agree |
| `version_of` | the source names another DOI of the same work, registered in the work registry |
| `unconfirmed` | only one kind of evidence, or none |
| `conflict` | identifier and title do not point to the same work |
| `wrong_kind` | the text or the paper's DOI is not an article |

## Verdict table

`bindings.py` builds one row per stored full text, and one per abstract or
record that a current decision names. A full text's verdict is the latest
current decision about it, and otherwise the computed verdict. `usable` says
whether extraction may read the text:

| Verdict | Usable |
|---|---|
| `verified` | yes |
| `version_of` | yes, except a preprint as the full text of a published paper (decision D1). Accepted manuscripts are used. A paper whose own DOI is a preprint or repository deposit may read the published text |
| `unconfirmed`, `conflict`, `wrong_kind`, `not_this_work` | no |

A record row with `hold` or `wrong_doi` withholds the paper. Record corrections
change field values and have no row.

A paper with no usable text of its own also gets a row for the usable text of a
DOI the work registry merges into it (column `carried_from`), unless that text
is a preprint. The DOI that is kept then reads the text the merged DOI holds; the
text is not copied.

`IdentityVerdicts` reads the table. The full-text gate (`gate.py`) decides from
it: a text is read only when the table has a usable row for this paper and this
text, and the file has not changed. Every other case rejects that text alone, and
the paper falls back to its abstract. The route builder also holds a paper that
a record row withholds. When the decision file or the work registry has changed
since `apply --install`, the gate stops until the table is rebuilt.

Two DOIs of one work can receive different screening results. The work is
included when any of its DOIs was included: the route builder gives the kept DOI
the screening result of an included merged DOI (`carry_screening_from_merged_dois`).
A curated exclusion still applies, and no paper is re-screened.

A converter or fetcher that writes a full text gets new rows for that text
(`refresh_fulltext_rows`). The text under another DOI is carried only at the
next `apply`.

## Commands

```bash
python -m pipeline.identity migrate
python -m pipeline.identity migrate --check
python -m pipeline.identity audit
python -m pipeline.identity decide --queue <audit folder> --where COLUMN=VALUE --accept-suggested --basis ... --reviewer ...
python -m pipeline.identity apply
```

The order of a correction is: `audit` lists what needs a decision, `decide`
records the reviewed decisions, `apply` lists the papers whose text changes and
installs the verdict table, and `pipeline/update/run_scoped_paper_update.py`
re-extracts or removes those papers.

### audit

`audit` lists the texts and records that need a decision. It changes no
pipeline data; it writes `review_queue.csv` and `audit_summary.json` to a new
folder under `data/processed/identity/audits/`.

| Check | Target | Evidence |
|---|---|---|
| `fulltext` | a stored full text | header identifiers and title, the first pages of the PDF when the parsed text is not enough, document kind |
| `shared_abstract` | an abstract | the same abstract on records that the work registry does not link; the title that agrees with it owns it |
| `record_title` | a record | PubMed's title for the record's DOI |
| `record_doi` | a record | a DOI that names no work, or a part of another item |
| `openalex_pmid_collision` | a record | an OpenAlex work ID equal to the PMID of another work |
| `model_report` | the text the release used | the extraction model wrote that the text and the paper differ (`model_reports.py`) |

It reads the candidate ledger, the stored full texts and PDFs, the PubMed
records kept from discovery, the work registry and the decision file, and the
release's extraction outputs and findings. By default the release is the
active one; another is named with `--outputs` and `--kg-dir`:

```bash
python -m pipeline.identity audit \
  --outputs data/processed/extraction/routed_runs/<run_id>/route_extraction_outputs.jsonl \
  --kg-dir <release folder>/kg
```

Record corrections in the decision file are applied to the audit's copy of
the ledger before texts are checked. An item that a current decision already
settles is left out and counted. A hold settles nothing. Items about records that are neither in the release nor
retained for extraction are counted but not queued; `--include-corpus` queues
them too. Each queued item has:

- `scope`: `release` when the release has findings for the paper, `extraction`
  when the paper is retained for extraction, `corpus` otherwise; the queue is
  sorted by scope, verdict and main-graph findings;
- `verdict` and `rule` from the check;
- a suggested decision (`suggested_verdict`, `suggested_relation`,
  `suggested_related_doi`, `suggested_fields`) with its basis, or `review`
  when the evidence does not point to one;
- `target`: the text or record a decision would name, by SHA-256 and document
  DOI;
- the findings the release has for the paper, and the decisions it already
  has.

### decide

`decide` appends reviewed decisions. They come from one of three sources:

- `--queue`: items of an audit's review queue, selected with `--where
  COLUMN=VALUE` (or `COLUMN!=VALUE`; repeatable). `--accept-suggested` records
  each item's suggested decision; `--verdict` records the same verdict for all.
  Each decision cites the audit and the item in `evidence`.
- `--csv`: rows with the decision file's fields; `target`, `fields`,
  `clear_fields` and `evidence` hold JSON.
- `--doi` with `--target` and `--verdict`: one decision.

`--basis` and `--reviewer` are required, and `--dry-run` checks without
writing. Before anything is written, every decision is checked:

- the text it names is stored now: the full text or its PDF has the SHA-256
  given, or the record's abstract does;
- the verdict fits the target, a version names a relation and the DOI of a
  work, and a basis and a reviewer are given.

If any decision fails, nothing is written. A decision that says the same as a
current one, with the same basis, is skipped, so a batch can be recorded again
without effect. A decision about a text supersedes the current decision about
the same text. A `hold` or `wrong_doi` supersedes the paper's current one, and a
`record_corrected` supersedes earlier corrections of the same or fewer fields.

A `version_of` under a relation that counts two DOIs as one report is also
entered in the work registry, with the decision as its source, so that
deduplication counts the report once. A preprint or repository DOI becomes the
alias of the article DOI. Otherwise the paper's DOI is canonical for a full
text, and the DOI whose abstract it is for a shared abstract. Deduplication
uses a pair only when both DOIs are in the corpus.

### apply

`apply` builds the verdict table and compares, for every paper the base release
extracted, the text the pipeline reads now with the text the table allows:

- now: the full text when the route table sends the paper to it, otherwise the
  abstract; nothing for a paper the route table holds;
- with the table: the full text when the table makes it usable and it holds
  article text, or the text of a DOI merged into this one; otherwise the abstract
  unless a decision says it is not this paper's; nothing for a paper that a
  `hold` or `wrong_doi` withholds.

A DOI merged into another is not compared: it has no route, and the release keeps
the other DOI's findings.

It writes a new folder `data/processed/identity/updates/<update id>/`:

| File | Content |
|---|---|
| `verdicts.parquet` | the verdict table |
| `changes.csv` | each paper whose text changes: `re-extract` when a text remains, `remove` when none does, with the reason and the release's findings |
| `scope_dois.txt` | those papers, for `run_scoped_paper_update.py prepare --doi-file` |
| `apply_summary.json` | inputs with hashes, verdict counts and changes |

The base release is the active one
unless `--outputs` and `--kg-dir` name another. With `--install`, the table is
copied to `data/processed/identity/verdicts.parquet`, with its summary next to
it, and record corrections and cleared unusable abstracts are written to
`data/curated/paper_metadata_overrides.json` with the decision's id
(`source_decision`). The route builder, the KG build and the release assembly
read that file. Without `--install`, nothing outside the update folder changes.

### migrate

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

The full-text gate and the route builder read the verdict table. Retrieval paths
do not call `verify.py` yet: they still write the older acquisition audit report,
which no gate reads (step 6 of the design document). Access overrides and the
DOI alias registry stay where they are: the first decides how text is
retrieved, and the second is the work registry, read through `works.py`.
