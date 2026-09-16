# Literature update — 15 September 2026

## Scope and baseline

Corpus surveillance using the existing v3 PubMed/OpenAlex protocol and canonical
research scope. The latest promoted discovery baseline is
`living_full_composite_v3_20260715`, covering through 15 July. The current search
is `living_update_v3_20260915`, covering 1 July–15 September, including the
protocol's 14-day overlap. Strategy and scope hashes match the baseline.

The plan contains 345 executions: 113 PubMed publication-date searches,
113 PubMed Entrez-date searches, and 119 OpenAlex publication-date searches.
OpenAlex historical indexing backfill remains outside this elapsed-period run.
Search completeness describes execution/count reconciliation, not search recall.

Active evidence/graph baseline: `author_identity_20260906_reviewed`.
Existing UI working-tree changes predate this update.

## Stages

1. **Plan/preflight:** complete; initial 33 discovery regression tests passed.
2. **Retrieve:** complete, 345/345 executions, no failed executions or count
   shortfalls; 37,488 hits and 4,194 unique provider records. Artifacts under
   `data/processed/discovery/runs/living_update_v3_20260915/`.
3. **Consolidate/promote discovery:** complete; 3,622 canonical records,
   2,368 new DOI candidates, 1,151 rediscoveries, and 103 no-DOI records retained
   for identifier resolution. Search watermark now 15 September.
4. **Enrich and screen:** complete. Abstract enrichment recovered 781 abstracts.
   All 718 original screening requests now have successful decisions: 47 batch
   successes plus 671 successful standard-API retries. Current prescreen v2.11
   retains 706 of those records; 411 are model-included, including six ineligible
   commentaries. The extraction-eligible cohort contains **405 papers** (238
   primary and 167 secondary). All 48,610 prior screened DOIs are preserved.
   Audit: `data/processed/corpus/living_update_20260915/screening_reconciled_audit.json`.
5. **Retrieve/convert source text:** in progress; PMC supplied 77 DOI-verified
   full texts, access-link refresh completed, and managed PDF retrieval is running.
6. **Extract and validate:** pending source preparation; use fresh run IDs and
   reconcile expected tasks with successful outputs before release assembly.
7. **Build/reconcile updated graph:** pending validated evidence.

## Repairs made during this update

### Procedural protocol versus prospective study protocol

Review of actual exclusions found `10.1002/pan.70286`, a retrospective
18-infant cohort reporting sedation outcomes, excluded solely for the title
phrase "Protocol for". Rule v2.10 now requires a study/trial qualifier in that
title branch; specific study/trial protocol and publication-type rules remain.
The new fixture and existing prescreen suite pass 70 tests and 65 subtests.
This update's cohort is being re-prescreened under the new rule. The first
prescreen snapshot is retained in the discovery run for comparison. Historical
exclusions outside this update have not been reprocessed.

### Rediscovered papers with newly available abstracts

The real update recovered abstracts for three previously unretained records.
Promotion now includes those records with new candidates in
`screening_candidate_dois.txt`, and preserves this scope through interrupted
promotion/retry. `new_candidate_dois.txt` remains the new-only count/handoff for
compatibility. The three changes are recorded in
`rediscovery_metadata_changes.json`; prescreening still applies ordinary
eligibility rules (an abstract does not make a repository deposit eligible).

### Interrupted discovery promotion

Confirmed the September audit's failure mechanism in the current command.
Promotion now saves its original new/rediscovered DOI cohorts, timestamp,
input checksums, and destination paths before canonical writes. Retries retain
the original backups and handoff rather than classifying partially committed
new records as rediscoveries. Changed inputs/destinations fail explicitly.
Injected interruptions at context, unresolved-record, history, and manifest
writes verify recovery. This is retry protection; corpus writers still run
sequentially, and readers must wait for promotion to finish.

### JATS source context

The packet parser now includes JATS figures and table wrappers, preserving
captions, labels, notes, source IDs, section headings, and table cells/spans.
Wrapped tables appear once. Existing TEI extraction tests remain passing.
A namespaced JATS fixture verifies a null-result caption, units, and a table
sign-convention note. Saved-source checks are recorded in the discovery run's
`jats_repair_source_check.json`; these measure restored input content, not
improvement in final extracted findings. No historical extraction rerun has
been performed as part of this parser repair.

The saved-source check covered nine distinct reports and preserved all 49
caption/note passages. The audit example recovered four figures and both
table captions and notes. This diagnostic set is not a representative quality
sample.

The final model-input serializer was checked as well: all 49 passages remain
present. JATS table text now preserves row boundaries and explicit cell-span
annotations, so the model does not receive only flattened cell values. The
focused packet/article/task suite passes 23 tests after this addition.

### Primary batch result accounting

Primary batch parsing now requires a results file and exact reconciliation of
manifest/result keys. Missing, duplicate, or unexpected keys stop parsing
before output writes; explicit keyed provider errors remain available for the
normal error path. Schema errors now produce `issues_found` rather than `ok`.
Partial result sets require recovery before this parser can materialize them.
Schema-invalid outputs are eligible for `--retry-errors`; a successful output
still prevents redundant retry. The focused retry/batch suite passes 21 tests
and two subtests after this additional change.

Validation so far: 80 relevant tests and two subtests pass. The active release
pointer consistency check passes. The configured `gemini-3-flash-preview`
model was verified through the provider API to support batch generation.

### Repeated PubMed summary requests

A partial checkpoint contained 10,093 PubMed query hits for 1,444 unique PMIDs.
The adapter fetched summaries again on every overlapping query. It now caches
up to 4,096 summaries within one adapter/session, retaining per-query record
order, rank, and provenance. Errors/missing summaries are not cached; eviction
and new-session freshness are tested. The discovery provider/runner suite
passes 18 tests. This change applies to subsequent processes/resumes; the
already-running retrieval process retains its original loaded code. No live
runtime saving is claimed for that process.

## Runtime and resume

Latest combined verification: **156 tests and 67 subtests passed**. Full output
is saved at `docs/evaluation/literature_update_2026-09-15_pytest.txt`.
The discovery run also contains `execution_environment.json` and
`pipeline_changes.patch` to identify the runtime and uncommitted code used.

The shell's default Python lacks pandas; use the existing project-compatible
interpreter `/opt/homebrew/Caskroom/miniconda/base/bin/python3`.

Full-text preflight found Colima/GROBID stopped. `colima start` first failed
because its disk was still marked in use by the stopped instance. After
`colima stop --force` and `colima start`, `docker start psychkg-grobid`
restored the existing service. Its `/api/isalive` check now passes. No VM or
container data was deleted or recreated.

```bash
/opt/homebrew/Caskroom/miniconda/base/bin/python3 \
  pipeline/discovery/run_literature_search.py \
  --resume --run-id living_update_v3_20260915 \
  --config pipeline/config.local.yaml \
  --scope-config pipeline/config.example.yaml
```

Do not launch a second writer while this run is executing. Consult the run
manifest/state before resuming. Do not manually advance search history or
active release pointers.

## Current status — local preview complete

**Completed local release:** `living_update_20260916_complete`.
Release ID: `living_update_20260916_complete:6e3923edab70475e912546ea7f9ee6e4`.
Preview: http://127.0.0.1:8011/?data-source=local (server session 23580).
No production deployment, commit, or push. Hourly automation remains PAUSED.

All 405 selected reports have validated extraction outputs and final dispositions:
368 represented, 23 unmapped, 14 without a graphable finding. The active graph has
98,765 findings across 21,743 DOI reports, adding 1,633 findings from 368 reports.
All baseline findings, projections, and reviewed decisions are preserved. All 31
recommendations from seven guideline/consensus reports were extracted but remain
in the normalization audit because their entities lack supported mappings.

Both active-pointer and public-artifact checks pass. Explore, Analyze, and Methods
were inspected in the local browser. The header correctly shows September 15
coverage and identifies the candidate as a local preview; archived release/DOI
metadata remains unchanged. No browser console errors observed.

Final report: `docs/literature_update_2026-09-16_summary.md`.
Audits under frozen inputs: `complete_release_preservation_audit.json`,
`complete_cohort_dispositions.json`, `local_preview_verification.json`, and
`complete_update_code_provenance.json`. Recovery suite: 148 passed; release guard
suite: 21 passed; preview suite: 18 passed. Historical checkpoints below describe
the intermediate work and are superseded by this completed status.


At 04:42:36 UTC September 16, screening attempt 2 finished. At 04:52 UTC,
the parser reconciled all 718 unique keys: 47 successful decisions and 671
provider errors, all code 13, "Internal error encountered." No missing,
duplicate, or unexpected results. The canonical routing table was not merged.
Original results and parse artifacts are preserved under screening_attempts/attempt002.

Recovery completed successfully for all 671 failed records. Reconciliation and
canonical merge are complete: all 718 unique request keys are accounted for,
with no manual classifications. Canonical screening now contains 49,316 DOIs,
preserving every prior DOI and adding the 706 currently prescreen-retained DOIs.
The 405-paper full-text worklist has been built using the explicit screening
queue and the discovery pre-promotion candidate snapshot.

PMC retrieval finished; inspect
`data/processed/fulltext/pmc_xml_report.postscreen_living_update_20260915.json`.
PMC fetched 77 of 89 targeted reports (12 unavailable, no request failures).
All 77 have exact-DOI identity verification; the scoped audit is saved as
`data/processed/corpus/living_update_20260915/pmc_source_identity_audit.json`.
Access refresh queried 55 records with zero provider errors, finding two PDF
links. The regenerated worklist has 77 reusable full texts, 278 actionable PDF
retrieval records, 48 without accessible full text, and two with access still
unknown. Unknown/closed-access records retain abstract-level eligibility.

**Current stage: evidence assembly and local graph release.** Hourly automation
is PAUSED at the user's request. All model runs are complete.
Frozen inputs/artifacts: `data/processed/extraction/living_update_20260916_inputs/`.

Validated primary outputs: `primary_validated_outputs.jsonl`, matched exactly
to all 534 tasks in `primary_validated_tasks.jsonl` across 238 DOI reports.
Converted evidence: `primary_evidence_rows.json` (1,228 rows). Sixteen domain
tasks correctly reported no scoped evidence; they remain accounted for.
532 tasks passed initially; one recovered after correcting the public-health
prompt's nearest-category conflict, and one source-reviewed cell-culture
classification was repaired without changing findings/doses/statistics.
Audits: `primary_cell_model_source_review.json`, `primary_population_model_audit.json`
(no further obvious cell-model mismatches), and `prompt_versions/`.

Validated meta outputs: `meta/validated_extractions.jsonl`, all 11 tasks; evidence
`meta/evidence_rows.json` (43 rows). Native-schema requests were rejected with
HTTP 400, so the new explicit prompt-schema mode was used with unchanged full
post-generation schema validation. Optional null metadata normalization omits
unreported values rather than inventing counts. Source-reviewed locator and
comparison repairs are recorded in `meta/locator_source_repairs.json` and
`meta/source_review_comparison_repairs.json`; raw model outputs remain intact.
All final meta schema, semantic and locator checks pass.

Validated reviews: `reviews/validated_bundles.jsonl`, all 149 tasks exactly
matched. Review evidence conversion completed: 570 rows (422 main-graph eligible,
148 paper-detail-only). Outputs
`reviews/evidence_rows.json` and `reviews/evidence_conversion_report.json`.
The overstrict reverse coverage implication was removed: each paper-defining
aspect must still have at least one paper-defining relationship, while additional
major-supporting relationships may cover it. Tests retain missing-coverage and
noncentral-link checks. Canonical prompts now state this explicitly.
Output selection prefers original valid records: 129 original, 12 retry1,
five retry2, two retry3, and one source-reviewed removal of a major-aspect link
from an already detail-only secondary relationship. See
`reviews/validation_reconciliation_audit.json`, `selected_output_origins.json`,
and `coverage_link_repair.json`. No source claims were invented for these repairs.

Author prefetch completed online: 393/398 DOI reports resolved. Five retain
unresolved metadata fallback. Seed cache: `author_cache_seed.json` under frozen
inputs; use it as AUTHOR_CACHE_SEED for the final build. The active baseline
pointer check still passes for `author_identity_20260906_reviewed`.

Assembly completed for **living_update_20260916_validated** with all three
validated overlays and complete replacement cohorts. Every baseline raw evidence
row was preserved: 110,069 existing + 1,841 new = 111,910 rows across 23,093 DOIs.
These are pre-admission evidence rows; the baseline graph's 97,132 findings across
21,375 DOIs are a different, filtered measure. No rows were removed by eligibility,
replacement, or deduplication. Canonical metadata refreshed 302 papers.
The fresh graph build is running (session 54780, log
`living_update_20260916_inputs/release_build.log`) with the prefetched author cache,
activation and external publication disabled. A release-risk check found that the
standard rebuild does not carry forward the reviewed research-area overlay.
Added `pipeline/validate/carry_forward_research_area_reviews.py` and optional
REVIEW_BASELINE_DIR integration in the build script. Seven targeted tests pass.
After the current build completes, run carry-forward with the active baseline
and new candidate, then re-export query/browser artifacts before promotion.
It requires identical finding IDs, nonempty source fingerprints, and unchanged
normalized projections; it fails closed on changed or missing reviewed records.
Compare admitted graph findings and old projection sets separately. The user's
latest instruction is to finish a local preview for inspection, with no production
push, and summarize both completed fixes and remaining observed issues.
Use guarded local promotion to synchronize Methods and local pointers, start
`scripts/preview_site.sh local` bound to localhost, and open the resulting preview.


Latest recovery regression suite: **148 tests passed** in
`docs/evaluation/literature_update_2026-09-16_final_recovery_pytest.txt`.
Updated code/prompt patch and hashes are under frozen inputs; regenerate them
after the latest review coverage fix before final release provenance.

Access repair completed: all 208 rows refreshed, 61 with new PDF links, 63 with
expanded candidates. Three PMC lookups returned 404; their other provider
lookups completed. Of 63 genuinely new URLs, one PDF downloaded and 62 failed.
Recovery ran against scoped metadata/candidate snapshots containing only new
URLs, with doi.org excluded and no alternate-source replay. All 63 results
retained attempt count 2 and were merged atomically into canonical candidates,
preserving existing URL metadata. Full provenance, before-merge snapshot, and
merge result records are in `data/processed/corpus/living_update_20260915/new_url_recovery/`.
Do not repeat the completed refresh or download passes.

Initial PDF conversion **completed successfully** at 05:59 UTC: all 62 reports
converted, zero failures. The combined scoped identity audit now has **139
verified full texts**: 129 exact DOI and ten title-verified. Saved audit:
`data/processed/corpus/living_update_20260915/source_identity_after_initial_conversion.json`.
Conversion log: `data/processed/corpus/living_update_20260915/pdf_conversion.log`.
Report: `data/processed/fulltext/local_pdf_conversion.postscreen_living_update_20260915.json`.
Do not repeat initial conversion. Routes have not yet been rebuilt.

Managed PDF retrieval is complete: 62 downloaded, 216 failed (106 forbidden,
102 other failures, eight not-found). Standard repository recovery found no
additional tasks. Reports `pdf_direct`, `pdf_recovery`, and `pdf_retrieval` with
suffix `.postscreen_living_update_20260915.json` preserve all attempts.
The frozen 405-DOI selection and pre-PDF worklist remain in the run folder.

**Required correction before extraction:** the retrieval audit demonstrated
literal `nan` URL candidates bypassing access-metadata refresh. The shared URL
split/join/rank helpers now discard missing-cell sentinels. Regression tests
cover both URL handling and unknown-access worklist routing. The first focused
run passed 92 tests; final verification is saved at
`docs/evaluation/literature_update_2026-09-16_null_urls_pytest.txt`.
The affected cohort is **208 failed records** whose original only PDF candidate
was a missing value. Its source snapshot and reasons are saved in
`data/processed/corpus/living_update_20260915/null_url_access_refresh_audit.json`
and `null_url_access_refresh_dois.txt`.

Then regenerate worklist using original queue, discovery pre-promotion candidate
snapshot, and explicit versioned PMC report. Rebuild canonical routes globally,
freeze scoped article inputs/tasks, and continue extraction/assembly below.
CORRECTION: the earlier checkpoint incorrectly called seven guideline/consensus
routes terminal/no-model. Inspection during final release accounting shows the
frozen routes use runnable guideline_consensus/recommendation_consensus_schema.
They must be extracted; no audit-only final disposition should be invented.

Do not resume screening recovery or resubmit/poll its finished batch.

The 22 reviewed metadata corrections have now been materialized with run
living_update_20260916_screening_quality. Prescreen v3 has completed across all
2371 scoped DOIs: 706 retained, 651 obvious irrelevant, 648 non-evidence artifacts,
158 preprints/unpublished, 127 unusable abstracts, 80 non-English, and one
non-paper container. Twelve previously retained records are now excluded:
seven non-English reports, four Wiley book chapters, and one news report.
This is application of existing source eligibility, not a scope change.
Snapshots and change records are saved in screening_recovery/prescreen_decisions_v3.parquet
and prescreen_changes_v3.json. Reconciliation must preserve all 718 raw screening
outcomes while the current prescreen gate restricts materialized routes to 706.

The quality audit queried ESummary for all 1130 PubMed-linked DOIs in this
update, with zero identity mismatches. It found 23 non-English articles; 20
had blank or incorrect English language metadata, including seven of the 718
screened papers. Three already had correct non-English metadata. The PubMed
adapter had discarded the returned lang field; this is now fixed and tested.
A Wiley handbook chapter (10.1002/9781394215683.ch31) and a newsletter news report
(10.1002/adaw.35025) also have evidence-backed publication-type corrections.
Source responses and before/after override files are in screening_recovery/.

Prescreen v2_11_20260916 additionally recognizes Wiley ISBN-13 chapter DOI
identifiers (10.1002/<ISBN>.ch<number>) when providers mislabel them as other.
This catches the demonstrated three handbook chapters without excluding ordinary
Wiley journal articles. Language merging now also prefers explicit PubMed article language over a
longer alternative provider label. Latest focused tests: 85 passed and 52
subtests passed.

A demonstrated queue-budget bug was fixed: approx_input_tokens_char4 now includes
the repeated system instruction and response JSON schema, not just paper text.
The estimate remains approximate; no causal claim is made about provider errors.
Existing submitted files/queues were preserved unchanged. Regression tests cover
splitting when instruction/schema overhead consumes the token budget.

## Screening submission history

Discovery, enrichment, and prescreening are complete. At the user’s request,
the first 718-request screening job was cancelled after nearly eight hours:
`batches/anj7ui0yf8u8jxvn23nxq3wmzl0af6tnsovg` reached
`JOB_STATE_CANCELLED` at 20:55:59 UTC on September 15.

The identical 718 requests were resubmitted with the same model and settings.
Replacement job `batches/0kft2qzncwniql1pk95jz8z6yjymjd2f1osy` was accepted at
20:56:47 UTC with `JOB_STATE_PENDING`. The queue now points to
`screening_attempts/attempt002/job.json`; cancellation evidence, the first
queue snapshot, and input hashes are saved under `screening_attempts/`.
The request-file SHA-256 is
`27458d83de8e13af04659bde2fafcec8daec482d04f10686a2d4b2cc5c20827c`.

A thread heartbeat named **Resume knowledge graph update**, ID
`resume-knowledge-graph-update`, now checks hourly at the user’s request. It
resumes the full remaining pipeline when results arrive and stays quiet for
unchanged status. The earlier 30-minute delay was already reported. Investigate
and report once if attempt 2 is still incomplete after September 16 at
20:56:47 UTC (the provider’s 24-hour target, not a guaranteed deadline).
Do not automatically cancel or resubmit again.
This supersedes the earlier instruction to wait continuously in the active turn.

Do not submit a duplicate job. To check, download, parse, and merge the completed
result using the existing queue controller:

```bash
/opt/homebrew/Caskroom/miniconda/base/bin/python3 \
  pipeline/review/advance_gemini_domain_routing_batch_queue.py \
  --queue-json data/processed/corpus/living_update_20260915/screening_queue.json \
  --no-submit
```

Once the queue completes:

1. Reconcile all 718 request keys with parsed decisions; inspect exclusions,
   ambiguous classifications, and all errors before downstream work.
2. Build the full-text worklist with the same explicit `--queue-json`. Use
   the discovery pre-promotion candidate backup as the previous snapshot.
   Run PMC retrieval, refresh access links for residual records, then use the
   managed PDF retrieval/conversion workflow and source-identity audits.
3. Rebuild canonical extraction routes globally. Make a scoped route snapshot
   for the post-screen selected DOIs and build this update's article packets
   into a separate file. Preserve existing global packets while jobs run.
4. Build primary tasks with the selected DOI file and explicit new packet file
   (`--no-default-article-text-inputs`). Build review and meta-analysis v2 tasks
   from a snapshot of the selected candidate rows and the same frozen packets.
   Do not submit legacy secondary routes through the generic primary runner.
5. Use fresh extraction run IDs, verify prepared versus submitted models, and
   reconcile expected tasks with successful outputs, including zero-finding
   outcomes. Retry only failed work. Convert each literature family through
   its current converter and validate source support.
6. Assemble a fresh candidate with `pipeline/kg/assemble_combined_release.py`
   using the active baseline outputs/evidence and the new family overlays.
   Reconcile preservation of unrelated evidence and explicit replacements.
   Build and validate the graph/Methods release under a new run ID, then
   promote the completed local release through the guarded publisher.
7. Compare with `baseline_counts.json`, verify release pointers and payloads,
   and report the final coverage, inclusion counts, exclusions, unresolved
   records, and remaining access/quality limitations.

This earlier checkpoint preceded extraction and graph assembly. See the current
continuation point and final release section for the latest state.

## Replacement batch delay investigation

At 21:33 UTC September 15, attempt 2 was still running after 36 minutes.
The 30-minute delay notification was issued once. Read-only diagnostics found
the uploaded 12,966,272-byte input ACTIVE, its provider hash identical to the
local input, all 718 unique request keys matching the manifest, and the model
still advertising batchGenerateContent. No upload or cohort-accounting defect
was found. Full diagnostic: screening_attempts/attempt002/delay_diagnostic.json.

Google documents a 24-hour target turnaround for Batch API:
https://ai.google.dev/gemini-api/docs/batch-api . The delay is unusual relative
to this project's history but does not establish that execution has stopped.
Keep the replacement in place and continue scheduled checks; do not repeatedly
notify about the same delay or automatically resubmit again. The public status
page did not expose readable incident details through the web fetch.

## Earlier overnight continuation authorization (now superseded)

The user requested hourly checks and autonomous continuation through all
remaining stages while they sleep. The existing heartbeat was updated in place.
Once screening finishes, continue through full-text retrieval, extraction,
validation, and guarded local graph release. If downstream model batches need
time, use the heartbeat to check their actual queues and resume from saved
checkpoints. Do not stop at an intermediate stage or keep polling the completed
screening job. Pause monitoring after completion or only for a genuine decision
that prevents further progress.

## Additional observed efficiency issue

Managed conversion reruns the all-history source-identity audit even for a
one-paper incremental conversion (roughly 90–110 seconds for over 13,600
artifacts here). A future incremental audit must key verification to artifact
bytes and metadata/registry versions and invalidate changed inputs; do not
simply reuse a stale DOI-only verdict. Current run retains the full audit.

## Review locator contract observation

Unlike meta-analysis prompts, current review prompts do not explicitly require
verbatim supporting_text; they request concise evidence locators. A diagnostic
exact-match audit of the first 145 reports found 267 nonmatching supporting-text
strings across 107 reports, including paraphrases and ellipsis-joined passages.
These are not automatically unsupported claims or quotation errors under the
current review contract. The diagnostic is saved as
`living_update_20260916_inputs/reviews/source_quote_audit_initial.json`. No record
is rejected solely by that screen. A future contract should distinguish a
verbatim source excerpt from an evidence summary and validate them separately.
Current review validation checks schema, prominence/coverage consistency, and
source interpretation in targeted review; do not claim every review relationship
has undergone exhaustive sentence-level source verification.

## Final release verification (in progress)

The new tables contain 98,765 findings across 21,743 DOI reports: 1,633 new
findings across 368 reports (1,210 primary-study and 423 secondary-literature
findings). Of the new findings, 1,297 are main-graph and 336 paper-detail records.
All 97,132 baseline finding IDs, evidence fingerprints, domains, normalized
subjects/entities, admission statuses/reasons, and review origins are unchanged.
The complete baseline edge projection set is identical, with zero losses and
zero unexpected reintroductions. Review carry-forward preserves 3,157 decisions
and removes 791 previously held edges from the unreviewed rebuild. Total edge
rows: 96,428 → 98,065. See `release_preservation_audit.json` under frozen inputs.

The initial build wrapper exited after table generation because its source was
edited while the shell was executing it. Completed tables were retained; the
review carry-forward, author build, and exports were resumed explicitly and
serially. The revised script passes shell syntax validation. Future changes to
an executing shell script should be deferred until it exits.

Author tables rebuilt successfully: 22,246 papers resolved through OpenAlex,
119,342 authorships, 66,562 unique authors, 97.98% structured authorships.
The prior curated author-list reviews were reapplied. Query export completed;
browser payload export is running in session 23683 (`release_exports.log`).
No production deployment or push has occurred. Local synchronization/preview
and final active-release validation remain before completion.

### Completion guard caught an omitted literature family

Initial local promotion failed before changing the active release: seven selected
guideline/consensus papers had no completed extraction or final disposition.
The earlier checkpoint's terminal-route statement was incorrect. All seven have
supported runnable profiles and ready source text (four full text, three abstract).
Tasks rebuilt from frozen inputs into `guideline_tasks.jsonl`; standard API run
`living_update_20260916_guidelines` is processing all seven, log `guideline_run.log`.
After validation/conversion, assemble a NEW complete release candidate including
this fourth overlay, rebuild with REVIEW_BASELINE_DIR set, and redo preservation
checks and guarded local synchronization. The incomplete candidate remains
inactive. Correct source-update manifest counts and all final summaries.
