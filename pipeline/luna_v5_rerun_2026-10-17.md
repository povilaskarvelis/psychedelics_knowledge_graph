# Luna V5 migration and complete screening rerun

17 October 2026

The active screening and extraction model is **`gpt-6-luna`, low reasoning**.
Screening uses the exact evaluated V5 prompt in
[`title_abstract_screening.md`](../docs/screening/title_abstract_screening.md).
Primary extraction, guidelines/consensus, review relationships v2 and
meta-analysis v2 all use OpenAI Responses and its Batch API. New calls to the
retired provider are blocked, including from the old evaluation command.

## Approved scope

| Screening cohort | Records |
|---|---:|
| Previously retained by the full deterministic prescreen | 49,713 |
| Reopened topical exclusions with usable abstracts | 87,543 |
| **Fresh Luna V5 screening** | **137,256** |
| Records excluded by publication-format, language or usable-text cleanup | 134,364 |

Preprints/unpublished records, theses/dissertations, unsuitable publication
formats, non-English records, and unusable abstracts retain their cleanup
exclusions. Topic eligibility is delegated to Luna. This is now the default
production prescreen policy; `--legacy-topical-filters` reproduces the previous
topical filters for audits only.

The new generation is **`luna_v5_20261017`**. Its candidate metadata, original
prescreen decisions, selected screening frame, V5 prompt, requests and
manifests are frozen under
`data/processed/model_runs/luna_v5_20261017/`. The smaller 49,713-paper queue
was superseded before any of its requests were submitted.

## Progress and budget

**18 October checkpoint:** screening is complete. All 137,256 expected papers
have reconciled Luna results across 28 batches; 23,620 papers were included in
scope. The completed screening table is frozen by its recorded SHA-256 in
`run.json`. Extraction tasks have been prepared, but the full extraction run
has not been submitted.

The extraction audit decision is to retain the current production instructions
and schemas, using GPT-6 Luna with low reasoning. The broader same-schema prompt
rewrite was not promoted after fresh validation. Keep the verified deterministic
normalization repairs. See the
[final comparison](../docs/evaluation/primary_instruction_refinement_2026-10-18.md).

The currently prepared task inventory is a checkpoint, not the final submission
manifest:

| Extraction lane | Ready tasks | Other tasks |
|---|---:|---:|
| Primary studies and guidelines/consensus | 30,751 | Ready-only task file |
| Review relationships v2 | 3,989 | 64 awaiting article packets |
| Meta-analysis v2 | 344 | 6 awaiting article packets |

Before submission, rebuild selection and tasks from the completed Luna screening
and the latest verified source library. This incorporates subsequent PDF/access
and publication-format corrections. Freeze the resulting tasks, source hashes,
current prompt/schema hashes, task counts and Batch cost estimate under the clean
run IDs below. Existing research domains, primary schemas, review relationships
v2 and meta-analysis v2 methods remain in use.

Then submit resumable, size-checked Batch jobs; reconcile every expected task;
retry only failed or incomplete tasks with preserved lineage; and build a separate
replacement graph through the repaired normalizer. Check extraction completeness,
source identity, numerical/contrast binding, and graph inclusion and retention
before promoting a complete replacement release. Earlier published releases and
archived outputs retain their provenance. No previous extraction supplies a
completed task in this replacement generation.

The following paragraphs record the original screening setup and execution.

The four-request live Batch integration check passed for screening, primary
evidence, review relationships and meta-analysis extraction. Its estimated
cost was **$0.003582**. The full screening controller has been started.

The user authorized a **$100 model-API budget**. The shared transport records
conservative reservations for in-flight requests, replaces them with
usage-derived costs when results arrive, and rejects new submissions that
would exceed the remaining budget. Unknown paid attempts retain their
reservation until reconciled. Costs are token-price estimates rather than
reconciled invoices. Current measured V5 usage projects approximately **$38**
for screening; extraction volume will be known after fresh screening.

Inspect the run without creating new requests:

```bash
python pipeline/rerun_luna.py status
```

The initial queue used 503 small parts and only one active job, based on an
unnecessarily conservative local token cap. On 17 October, the account's
Limits page showed **1,000,000,000 queued tokens for GPT-6 Luna**. After stopping
the local controller, the seven already-submitted parts (1,838 papers) were
preserved. The remaining **135,418 papers were repacked from 496 parts into
21 batches**, each at most **150 MB** (mostly about 6,600 papers). The active
queue now has 28 parts total. Hash checks verify that every pending request
is byte-for-byte unchanged; the original queue is retained beside the
repack report under `screening/repacked_20261017T044351Z/`.

The controller now allows **six active batches**, with a **900,000,000-token**
local queue cap, while the shared $100 budget guard may defer a batch until
another finishes and its reservation is settled. These settings are saved
in `run.json`, so resuming uses them automatically. The controller checks
progress every minute, downloads both successful responses and per-request
errors, and stops for integrity or parsing failures. It keeps completed
work on disk. A process lock prevents duplicate controllers or repacking
while the controller is running.

To resume after the controller has stopped:

```bash
python pipeline/rerun_luna.py advance-screening --submit --watch \
  --prepare-extraction-after-screening
```

Do not start a second controller while one is already running. The current
log is `data/processed/model_runs/luna_v5_20261017/controller.log`.

For future consolidation, stop the local controller without cancelling the
remote jobs, then use `repack-screening --max-active N
--max-enqueued-tokens VERIFIED_ACCOUNT_CAPACITY`. This command preserves
every part with a job file, including attempts with an unknown submission
outcome, and only consolidates unsubmitted requests. Never assume another
account has this run's queue capacity.

## Screening before extraction

Canonical routing is now `data/processed/corpus/paper_domain_routing.parquet`.
It is promoted only after every expected screening result is reconciled,
validated and attributed to Luna. Partial screening does not replace that
table. Default extraction/task builders are blocked until screening completes.

At completion, the controller rebuilds extraction routes, primary/guideline
tasks, review-relationship v2 tasks and meta-analysis v2 tasks using the fresh
Luna decisions and available source texts. It does **not** submit extraction
calls as part of the screening controller. The clean extraction run IDs are:

- `luna_v5_20261017_primary` — primary-domain and guideline/consensus tasks.
- `luna_v5_20261017_review` — review relationships v2.
- `luna_v5_20261017_meta` — meta-analysis v2.

Each extraction runner now defaults to Luna and strict structured outputs.
Use these new run IDs; earlier model outputs must not be appended, treated as
completed tasks, or combined into the replacement release. Primary and
guideline tasks use `run_route_extraction_batch_api.py`; review relationships
use `run_review_relationship_batch_api.py`; meta-analyses use
`run_meta_analysis_v2_batch_api.py`. Their existing input snapshots, semantic
validation and source-location checks remain in place.

## Retired data and preserved sources

Mutable earlier screening queues/results, extraction routes/tasks and loose
extraction outputs are archived under
`data/archive/20261017_gemini_retired/`. Previous report-level screening and
route overrides are archived and cleared from the active run. No old model
decision is used to determine completion or eligibility in this generation.
The archive manifest records paths and hashes. Bibliographic corrections,
PDFs, full-text packets, source identity and access corrections remain reusable.

Historical evaluation reports and previous published releases retain their
true provenance. The published graph remains the previous release until the
fresh extraction is completed, validated and promoted as a complete replacement.
Historical outputs are not renamed as Luna results or silently mixed into the
new generation.

## Installation and checks

Model runners require `pipeline/requirements-models.txt` and
`OPENAI_API_KEY` in the project environment. Retired-provider variables were
removed from the project `.env`; credentials are never written to the run logs.
The screening prompt is checked against the evaluated V5 file. Regression
tests cover the cleanup policy, source/schema compatibility, asynchronous
result reconciliation, incomplete responses, budget reservations, and the
screening-to-extraction gate.

The [OpenAI Batch guide](https://developers.openai.com/api/docs/guides/batch)
documents the Responses endpoint, keyed result reconciliation, file/request
limits, partial failures and the 50% Batch discount used by this setup.
