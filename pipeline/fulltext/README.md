# Full-Text Conversion

This stage converts locally available PDFs into structured full-text artifacts
that downstream extraction and provenance checks can reuse.

The first goal is provenance repair: rows marked `full_text_seen` should point
to durable paper locations such as sections, tables, figures, pages, or TEI
elements rather than stale abstract snippets.

## Stage Runner

Run the full non-destructive maintenance stage:

```bash
python pipeline/fulltext/run_fulltext_provenance.py \
  --dataset all \
  --backend grobid \
  --limit 0 \
  --include-existing-artifacts
```

This performs three steps for each dataset:

1. Convert PDFs for stale `full_text_seen` abstract locators.
2. Rebuild `provenance_repair_report_<dataset>.json/.csv`.
3. Rebuild `evidence_triage_report_<dataset>.json/.csv`.
4. Export a blank `provenance_review_<dataset>.csv` for curator decisions.

With `--backend grobid`, the runner uses managed GROBID mode by default:

1. It builds a DOI queue for PDFs that do not already have a successful GROBID extraction.
2. It starts GROBID with the memory-safe Docker config from `start_grobid.py`.
3. It processes the queue in batches, restarting GROBID before each batch.
4. It runs the repair report only after conversion finishes.

The default batch size is 50. The client also retries transient GROBID failures
twice with a 5-second wait, and disables header/citation consolidation by
default for reproducible local parsing. Override these only if needed:

```bash
python pipeline/fulltext/run_fulltext_provenance.py \
  --dataset all \
  --backend grobid \
  --limit 0 \
  --include-existing-artifacts \
  --grobid-batch-size 25 \
  --grobid-retries 3 \
  --grobid-retry-wait-sec 10
```

Use `--grobid-batch-size 0` to disable managed batching and return to the old
single conversion call.

Preview the commands without running conversion:

```bash
python pipeline/fulltext/run_fulltext_provenance.py --dataset all --limit 50 --plan-only
```

Use per-dataset limits when clinical and mechanistic backlogs differ:

```bash
python pipeline/fulltext/run_fulltext_provenance.py \
  --dataset all \
  --disorder-limit 100 \
  --mechanistic-limit 0
```

The runner never applies curated-claim edits. Applying accepted repairs remains
a separate explicit step through `apply_provenance_repairs.py --apply`.

## Backends

- `grobid`: primary scholarly-article parser backed by a local GROBID service;
  preserves TEI XML with article sections, references, tables, and figure
  locators for downstream evidence packets.
- `docling`: fallback document conversion backend when the `docling` Python
  package is installed, especially for non-article PDFs or GROBID failures.
- `pdftotext`: lightweight plain-text converter using Poppler when explicitly
  requested for diagnostics or local inspection.

`auto` uses GROBID only. Use `all` for a comparison run across every configured
backend. Managed batching is currently only enabled for explicit
`--backend grobid` runs.

## Example

```bash
python pipeline/fulltext/convert_pdfs.py --dataset disorder --backend grobid --limit 25
```

Target rows where the curated claim says `full_text_seen` but still points to an
abstract snippet:

```bash
python pipeline/fulltext/convert_pdfs.py --dataset disorder --stale-fulltext-locators --limit 25
```

Restrict to a hand-picked DOI queue:

```bash
python pipeline/fulltext/convert_pdfs.py --dataset mechanistic --doi-file data/raw/my_doi_list.txt
```

To include a local GROBID service:

```bash
python pipeline/fulltext/run_fulltext_provenance.py \
  --dataset disorder \
  --backend grobid \
  --limit 0 \
  --include-existing-artifacts
```

Outputs:

- `data/processed/fulltext/<dataset>/*.json`
- `data/processed/fulltext/fulltext_report_<dataset>.json`

These artifacts are intentionally separate from curated claims. No claim rows
are modified by this stage.

## LLM Evidence Packets

After PDF conversion, build frontier-LLM-ready JSONL packets from the preserved
GROBID TEI plus paper-library metadata:

```bash
python pipeline/fulltext/build_llm_evidence_packets.py --dataset all
```

Outputs:

- `data/processed/fulltext/llm_packets_disorder.jsonl`
- `data/processed/fulltext/llm_packets_mechanistic.jsonl`
- `data/processed/fulltext/llm_packets_disorder_report.json`
- `data/processed/fulltext/llm_packets_mechanistic_report.json`
- `data/processed/fulltext/llm_packets_run_report.json`

Each packet includes DOI-level metadata, candidate compound/entity contexts,
source-type hints from publication metadata, selected reconstructed TEI
sections, tables, figures, references, and stable `llm_chunks` with
section/document offsets. The packet builder uses raw full TEI, not the
truncated artifact section snippets, so it is the preferred input layer for
API-based evidence assessment and data extraction.

Use `--packet-profile full` to preserve all extracted sections. Use
`--packet-profile lean_primary` for the Gemini extraction workflow; it keeps
title/abstract metadata, methods/results-like chunks, tables, and
marker-matched mechanistic/clinical sections while dropping most discussion,
conclusion, references, and secondary review body text.

For a quick preview:

```bash
python pipeline/fulltext/build_llm_evidence_packets.py --dataset disorder --limit 5 --packet-profile lean_primary
```

## Provenance Repair Report

After conversion, build a review report for stale full-text locators:

```bash
python pipeline/fulltext/build_provenance_repair_report.py --dataset disorder
```

Outputs:

- `data/processed/fulltext/provenance_repair_report_<dataset>.json`
- `data/processed/fulltext/provenance_repair_report_<dataset>.csv`

This report proposes section-level locators for human review. It does not edit
curated claims.

## Accepted Repair Gate

Export an explicit review template from the proposed repair rows:

```bash
python pipeline/fulltext/apply_provenance_repairs.py \
  --dataset disorder \
  --export-review-csv data/processed/fulltext/provenance_review_disorder.csv
```

A curator should mark only approved rows in the `decision` column, using values
such as `accepted`, `yes`, or `true`. Blank, rejected, or deferred rows are
ignored.

Dry-run the accepted decisions before editing curated claims:

```bash
python pipeline/fulltext/apply_provenance_repairs.py \
  --dataset disorder \
  --accepted-review data/processed/fulltext/provenance_review_disorder.csv
```

Apply only after the dry-run report looks correct:

```bash
python pipeline/fulltext/apply_provenance_repairs.py \
  --dataset disorder \
  --accepted-review data/processed/fulltext/provenance_review_disorder.csv \
  --apply
```

The apply gate verifies that each accepted row still matches the current
curated claim before writing. This prevents stale repair reports from silently
overwriting newer curation work.

## Evidence Triage

Evidence triage is separate from locator repair. A row can legitimately have
`access_level=full_text_seen` while still being the wrong source type for a
primary-study claim, such as a review, protocol, commentary, erratum, conference
abstract, or case report.

The triage taxonomy separates source family from evidence strength:

- `original_empirical`: original data, including trials, observational studies,
  preclinical assays, case reports, and case series.
- `evidence_synthesis`: systematic reviews, meta-analyses, and narrative reviews.
- `opinion_or_commentary`: editorials, letters, perspectives, critiques.
- `protocol`: planned study/protocol without outcome results.
- `correction`: errata/corrigenda/retractions.
- `conference_abstract`: abstract-only meeting reports.

Case reports are therefore not treated as synthesis/commentary. They are
`original_empirical` with low evidence strength.

Build the deterministic triage report:

```bash
python pipeline/fulltext/build_evidence_triage_report.py --dataset disorder
```

By default this only triages `full_text_seen` rows, because absence of a
full-text artifact for `abstract_only` rows is not a triage failure. Use
`--scope artifacts` or `--scope all` only for broader audits.

Outputs:

- `data/processed/fulltext/evidence_triage_report_<dataset>.json`
- `data/processed/fulltext/evidence_triage_report_<dataset>.csv`

Rows marked `propose_source_reclassification` with
`automation_status=auto_apply_eligible` can be applied automatically through a
dry-run/apply gate:

```bash
python pipeline/fulltext/apply_evidence_triage.py --dataset disorder

python pipeline/fulltext/apply_evidence_triage.py --dataset disorder --apply
```

This does not demote `access_level`: if the full text was seen, it remains seen.
It updates source/evidence-type fields such as `source_type`, `paper_type`, and
`study_design`, preserving an audit note on the curated row.

## Evidence Triage QA Sample

After high-confidence triage proposals are applied, the remaining
`needs_targeted_qa` rows should not be reviewed exhaustively by hand. Export a
small stratified quality-check sample instead:

```bash
python pipeline/fulltext/export_evidence_triage_qa_sample.py --dataset all
```

Outputs:

- `data/processed/fulltext/evidence_triage_qa_sample.csv`
- `data/processed/fulltext/evidence_triage_qa_sample.json`

The sample includes:

- `targeted_rule_qa`: uncertain rows, stratified by predicted class.
- `auto_triage_audit`: already auto-triaged non-empirical rows, for false-positive checks.
- `primary_control`: rows kept as original empirical evidence, for false-negative checks.

The CSV has blank quality-check columns such as `correct_classification`,
`correct_primary_vs_non_primary`, and `review_notes`. Use this to estimate rule
accuracy and decide which deterministic rules can be safely tightened next.

## Local LLM Full-Text Evidence Assessment

Run a local Ollama model over the QA sample to get semantic source-type,
claim-support, locator, and variable-extraction proposals:

```bash
python pipeline/fulltext/run_local_llm_evidence_assessment.py \
  --model qwen3:14b \
  --limit 10
```

If the model is not installed yet:

```bash
ollama pull qwen3:14b
```

For a quick smoke test with an already installed smaller model:

```bash
python pipeline/fulltext/run_local_llm_evidence_assessment.py \
  --model llama3.1:8b \
  --limit 1
```

Outputs:

- `data/processed/fulltext/local_llm_evidence_assessment.json`
- `data/processed/fulltext/local_llm_evidence_assessment.csv`

The preferred script name is now `evidence_assessment`. The older
`run_local_llm_evidence_adjudication.py` entry point and legacy output names
remain available for compatibility with existing checkpoints and scripts. In
methodology text, call this stage **full-text eligibility/evidence assessment
and data extraction**. Reserve `adjudication` for final conflict resolution
between model proposals, deterministic rules, and curator decisions.

This stage is non-destructive. It supplies bounded GROBID evidence chunks to
the model, asks for JSON matching a fixed sectioned schema, and records whether
the model's `supporting_quote` is actually present in the supplied chunks. Each
row has `assessment.eligibility_assessment`,
`assessment.source_classification`, and `assessment.data_extraction`; a legacy
top-level `adjudication` mirror is also written during the migration. Treat LLM
results as proposals until quote verification and QA metrics are acceptable.
Rows are only marked `semantic_auto_eligible` when the quote verifies, model
confidence exceeds the configured threshold, labels are internally consistent,
and the model does not request a human check.

The assessment also writes explicit routing fields. Primary empirical papers
route to `primary_evidence`; reviews, systematic reviews, and meta-analyses
route to `secondary_literature`; protocols, commentaries, conference abstracts,
and corrections route to `non_primary_context`. Secondary literature is retained
for the secondary-source graph view rather than handled as failed primary
evidence.

### Abstract-Only Evidence Fallback

For relevant/uncertain papers whose full text cannot be downloaded or converted,
run the same evidence-assessment schema in abstract-only mode. This is separate from
abstract screening: screening only decides relevance, while this fallback
extracts source/provenance and study variables that are explicitly stated in the
abstract.

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

Outputs default to:

- `data/processed/fulltext/local_llm_abstract_only_assessment.json`
- `data/processed/fulltext/local_llm_abstract_only_assessment.csv`

When the input is an abstract-screening report, verified compound/entity
contexts are expanded into claim-level assessment rows. Rows are marked with
`evidence_mode=abstract_only`; the prompt requires `best_evidence_location` to
be `abstract` or `none` and tells the model to use `not_reported` for details
not explicitly present in the abstract.
