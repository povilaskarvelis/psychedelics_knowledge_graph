# Literature update — 16 September 2026

## Final local release

Local preview: [open the updated graph](http://127.0.0.1:8011/?data-source=local&v=1&mode=explore&from=2000&to=2026).

- Run: `living_update_20260916_fulltext_recovery_complete`
- Search window: 1 July–15 September 2026, with a 14-day overlap for late indexing.
- Selected update cohort: 405 reports; all 405 have a terminal validated extraction.
- Source disposition: 268 reports have verified article text, 126 retained
  reports use abstract fallback, and 11 records were excluded after document
  inspection.
- Final normalized graph: **99,100 findings across 21,735 reports**.
- Reviewed decisions preserved: 3,157 findings and 2,366 edge projections.
- Production was not pushed or deployed.

The initial update selected 238 primary studies, 149 reviews, 11 meta-analyses,
and seven guideline/consensus reports. The manual recovery pass then replaced
the abstract-based extraction for 128 of those reports with verified full-text
extraction. The release contains 112,311 validated evidence rows before graph
normalization.

The seven guideline/consensus reports contain 31 validated recommendations.
Those recommendations remain in the normalization audit because their topic
entities do not yet have supported graph mappings; they were not silently
projected as unstable concepts.

If the preview server stops, restart it with:

```bash
RUN_ID=living_update_20260916_fulltext_recovery_complete bash scripts/preview_site.sh local
```

## Manual full-text recovery

The browser-review queue contained 264 records in six batches:

| Batch | Recovered PDFs | Confirmed closed | Excluded | Total |
|---|---:|---:|---:|---:|
| 1 | 34 | 15 | 1 | 50 |
| 2 | 36 | 12 | 2 | 50 |
| 3 | 20 | 29 | 1 | 50 |
| 4 | 35 | 11 | 4 | 50 |
| 5 | 0 | 47 | 3 | 50 |
| 6 | 2 | 12 | 0 | 14 |
| **Browser batches** | **127** | **126** | **11** | **264** |

One additional PDF was recovered immediately before batch 1, giving **128
newly verified full-text reports** in the re-extraction cohort. All 128 PDFs
were converted to canonical article-text artifacts and passed source-identity
validation.

The 11 exclusions were based on landing-page or document inspection: two
out-of-scope records, two conference/poster records, one dissertation, one
non-English unsuitable source, two unpublished institutional documents, and
three educational video lectures. Their 39 old evidence rows and 21 raw output
rows were removed from the release by the current-eligibility gate.

## Full-text re-extraction and release assembly

The 128 recovered reports split across the extraction families as follows:

| Extraction family | Reports | Tasks | Admitted evidence rows |
|---|---:|---:|---:|
| Routed primary/consensus | 85 | 198 | 710 |
| Review relationships v2 | 39 | 39 | 188 |
| Meta-analysis v2 | 4 | 4 | 15 |
| **Total** | **128** | **241** | **913** |

Every task used verified article text. Assembly replaced 504 prior evidence
rows for these reports with 913 new rows and removed 39 rows from the 11 newly
excluded reports, a net increase of 370 release evidence rows. The required
cohort guard passed 128/128.

Four additional meta-analysis result rows were held by quality gates: three
bundled multiple estimates in one result and one contained a numeric value not
found in the source. The held rows have explicit audit dispositions.

The provider batch jobs were cancelled after the decision to finish the small
remainder synchronously. Cancellation raced with provider completion and
returned partial successes. Reconciliation retained every valid completed
response, reused valid direct responses already produced, and synchronously
retried only unresolved request keys. Final coverage was 198/198 routed tasks,
39/39 reviews, and 4/4 meta-analyses.

## Pipeline fixes made during the update

| Area | Problem found | Fix |
|---|---|---|
| Discovery promotion | Partial retries could leave unclear state, and restored abstracts could miss handoff. | Added durable promotion intent, recovery-aware cohort bookkeeping, backups, and restored-abstract handoff. |
| Screening metadata | Language was discarded, and several chapters, news records, protocols, or non-English records survived screening. | Preserved source language, added source-backed metadata corrections, improved publication-format detection, and fixed a protocol-title false positive. |
| Provider recovery | A completed provider batch contained hundreds of per-request errors. | Added exact request-key reconciliation and targeted retries that do not repeat successful work. |
| URL handling | Missing URL values became the literal string `nan`. | Shared URL helpers now reject missing-value sentinels before retrieval. |
| Full-text packets | XML table structure could be lost. | Preserve table rows, spans, captions, and notes in model packets. |
| PDF identity | Cited DOIs, long first pages, preprint/published title ties, and multiple citations could misidentify valid PDFs. | Exact PDF metadata titles now outrank DOI prose; page-one identity inspection covers 12,000 characters; a unique metadata DOI resolves exact-title ties; multiple citations alone no longer imply a conference abstract. |
| Publication formats | Video lectures and several repository documents were treated as ordinary papers. | Added narrow deterministic format rules and persistent post-retrieval exclusions. |
| Extraction instructions | Public-health category instructions conflicted, while review validation required coverage more strictly than the prompt. | Corrected the prompt and validator contract, retained richer comparison/locator/qualification details, and applied documented source-reviewed repairs. |
| Mixed extraction families | The generic scoped updater omitted v2 review/meta tasks and would have treated 43 valid reports as deletion-only. | The scoped updater now builds, validates, converts, and assembles primary/consensus, review v2, and meta-analysis v2 cohorts together; a runnable route without a current task fails before replacement. |
| Scoped refresh | A full route rebuild activated 25,475 unrelated papers from the prescreen backlog. | Full deterministic rebuilds now preserve the prior selection state outside the requested DOI scope. The promotion guard caught this before activation. |
| Batch cancellation | Provider cancellation can return a mix of successes and cancelled requests. | Added explicit output reconciliation and direct retries by unresolved request key. |
| Graph ontology | Correct gut-microbiome findings exceeded the residual threshold because common taxa, metabolite, and microbial-function wording lacked subtopic mappings. | Expanded the microbiome subtopic rules and added a microbial function/metabolism category with coverage tests. |
| Build environment | The shell graph builder invoked a system Python without required packages. | The build wrapper now accepts `PYTHON_BIN` and uses one interpreter consistently. |
| Review preservation | Rebuilding could restore held edges or lose reviewed classifications. | Added checked carry-forward for unchanged reviewed evidence and projections; changed evidence stops carry-forward. |

## Remaining work worth prioritizing

1. **Add a first-class synchronous meta-analysis v2 runner.** This update used the archived prompt, schema, request payload, and existing parser directly because only the batch runner is currently packaged for v2 meta-analysis extraction.
2. **Add a single execution command for scoped updates.** Mixed-family task preparation, validation, conversion, and candidate assembly are integrated. Provider execution still requires invoking the primary, review, and meta-analysis runners separately.
3. **Map guideline and consensus concepts.** The 31 held recommendations form a concrete test cohort. Their recommendation status and conditional wording must remain distinct from empirical findings.
4. **Make full-history deterministic work incremental.** A full graph build still takes roughly 11–12 minutes, and article/task layers are rebuilt globally. Add phase timing and safe content-hash reuse.
5. **Standardize provider cancellation and fallback policy.** Avoid cancellation when a small batch is near completion, and always reconcile partial terminal results before retrying.
6. **Continue source-depth improvement.** The remaining 126 retained reports use abstract fallback. The other 11 records from the gross 137-report remainder were excluded after document inspection.
7. **Strengthen source-support contracts.** Separate exact excerpts from summaries and validate recommendation qualifications against source context.

## Validation and audit trail

- Candidate assembly: 128/128 required recovered reports completed.
- Graph build: 99,100 findings; ontology residual checks passed.
- Active release and graph pointers agree on the same release ID.
- Local preview returned HTTP 200 with cache disabled.
- Focused regression tests cover PDF import identity, scoped update safety,
  mixed-family guards, microbiome normalization, assembly, release guards, and
  preview behavior.

Detailed chronology: [operation log](literature_update_2026-09-15.md).
Versioned extraction outputs, evidence overlays, assembly reports, source
manifests, and graph payloads are retained under `data/processed/`.
