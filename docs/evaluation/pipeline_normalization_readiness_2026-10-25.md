# Luna corpus rerun: normalization readiness audit

Date: 25 October 2026. Scope: saved code, manifests, screening decisions, extraction inputs/outputs, recovery receipts, and focused offline tests. No new model calls, normalization, graph builds, or promotions were performed.

## Verdict

**The accepted V5 + PCP corpus is at the pre-normalization checkpoint. Extraction is mechanically complete with explicit source holds. It is not yet a clean handoff for a release described as incorporating the later V6.1 screening corrections.**

Two matters need resolution before freezing final normalization inputs: reconcile the unfinished, staged screening correction with the accepted corpus; and project ten newly held reports into the canonical candidate/routing state. Neither finding requires repeating the entire extraction.

## What is complete and consistent

| Extraction family | Usable outputs / current tasks | Distinct reports | Revalidated schema errors |
| --- | ---: | ---: | ---: |
| Primary and guideline/consensus | 36,798 / 36,798 | 20,250 | 0 |
| Review relationships v2 | 4,859 / 4,859 | 4,859 | 0 |
| Meta-analysis v2 | 347 / 347 | 347 | 0 |
| Total | 42,004 / 42,004 | 25,456 | 0 |

- All 13 original batch request/task files match their saved hashes. Their manifests consistently identify GPT-6 Luna with low reasoning effort.
- All 60 frozen prompt/schema assets and their snapshots match their recorded hashes. The original frozen task files and full-text packets also match.
- Original submission: 42,020 requests across 25,466 reports. Applying the documented recovery replacements and removing 16 held routes produces exactly the current 42,004 task IDs: no missing or unexpected IDs.
- Every usable output was matched to its task and DOI and revalidated. There are no duplicate output task IDs or cross-family report overlaps. Primary input fingerprints and meta-analysis source fingerprints match current tasks. Primary corruption, source-mismatch, category, and recommendation-tone guards also pass.
- The three families are accounted for together; reviews and meta-analyses have not disappeared because a primary-only task builder was used.
- The saved migration state explicitly disables reuse of previous screening decisions and extractions. Older Gemini material remains archived rather than being the source of this new extraction inventory.

Current canonical screening contains 141,334 distinct reports, with 26,149 included and 115,185 excluded; all screening rows identify Luna and there are no conflicting decisions for a DOI. The canonical screening hash matches the accepted run state.

The difference between 26,149 screened-included records and 25,456 reports with usable extractions is accounted for: 523 post-retrieval exclusions, 79 duplicate DOI aliases, 70 explicitly context-only/skipped records, 11 earlier source holds, and ten new source holds. The last ten have stale candidate statuses, described below. Screening inclusion alone does not override later publication/source checks.

## 1. Resolve the screening-version boundary before a final release

The production extraction follows accepted **V5 screening with explicit PCP scope**, plus separately recorded publication/source cleanup and accepted scholarly-analysis routing. It does not incorporate the later V6.1 correction experiment.

The V6.1 high-reasoning correction covers 23,070 reports. Its status is `main_results_ready_for_audit`, promotion requires an audit, and `canonical_outputs_changed` is false. Its result audit produced a 4,390-paper review queue.

The saved source-adjudication checkpoint contains 1,202 records: 639 candidate inclusions, 337 candidate exclusions, and 226 unresolved judgments. It explicitly records that canonical changes have not been applied. **241 of those 337 candidate exclusions currently have usable extraction outputs.** Examples include poster abstracts and papers where the eligible compound appears only as background. These are staged model-based source judgments, not final human gold labels; this audit did not independently adjudicate every paper or convert them into accepted exclusions.

Keeping experimental corrections separate was correct. However, the corpus cannot be described as having incorporated the latest screening corrections until that review is completed and its accepted changes are explicitly applied or rejected. Apply resulting exclusions and route changes through a scoped reconciliation, retaining existing valid outputs for unaffected reports.

Evidence: [correction run](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/screening_correction_20261019/high_reasoning_validation/run.json>), [result audit](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/screening_correction_20261019/high_reasoning_validation/result_audit_summary.json>), [source checkpoint](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/screening_correction_20261019/high_reasoning_validation/fulltext_result_audit/global_source_candidate_reconciled_1202_checkpoint_v2.json>), [staging-only audit code](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/review/run_screening_correction.py:395>).

## 2. Reconcile ten source holds across the handoff tables

The hold registry contains **21** reports: 11 held before batch preparation and ten held during recovery. All ten recovery reports are absent from usable outputs, as intended. Their source/abstract identities could not be authenticated, so a source hold is appropriate and is not a new topical exclusion.

However, those ten still have `retained_for_extraction_candidate=True` and `extraction_route_status=ready_for_abstract_extraction` in `candidate_papers.parquet`. The earlier 11 are correctly marked `hold_source_review` and not retained. The top-level `source_review_holds_pending` also still says 11, while the recovery subsection separately records ten more.

The repair path writes the hold registry and the batch materializer filters held outputs, but the candidate disposition is not reconciled in the same operation. A later corpus/graph status check can therefore encounter apparently selected reports with no successful extraction and fail. No usable extraction from these held reports was found.

Before normalization handoff, reconcile all 21 hold dispositions and current summary counts, preserving repaired task identities and completed output fingerprints. Add an invariant that every selected report has either its complete expected family outputs or an explicit, consistently projected hold/disposition. A generic full task rebuild is unnecessary and risks obscuring recovery lineage.

Evidence: [hold registry](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/extract/manual_extraction_route_overrides.json>), [repair application](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/extract/repair_extraction_inputs.py:215>), [corpus status guard](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/kg/update_corpus_graph_status.py:386>).

## Instruction testing and normalization changes

The extraction-instruction experiments were documented and tested rather than automatically promoted. The 18 October primary refinement assessment recommends retaining the existing Luna prompt and schemas: the broader rewrite improved familiar sets but did not establish a convincing improvement on the unseen set. The accepted changes include deterministic normalization repairs for chemical identity, comparators, study design, labels, and graph admission. Those per-item repairs are distinct from running corpus-wide evidence/entity normalization now.

Routing 813 accepted scholarly analyses through the review lane was an explicit policy change: 399 commentary/editorial reports and 414 other non-primary analyses. This was not accidental loss from the primary lane.

This approach makes sense. The remaining problem is recording one unambiguous accepted screening/extraction version at the handoff, rather than treating every experimental instruction file as already deployed.

Evidence: [primary instruction assessment](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/primary_instruction_refinement_2026-10-18.md>), [accepted routing receipt](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/accepted_review_routing_20261022/completion.json>).

## Search additions and coverage

The monthly update is promoted with general coverage through **15 October 2026**: 1,031 new DOI candidates, 987 rediscovered candidates, and 69 unresolved records. The PCP addition is a separate historical PubMed/OpenAlex backfill through **19 October 2026**: 5,474 new DOI candidates, 2,429 rediscoveries, and 1,289 unresolved records.

The search strategy disambiguates the ambiguous PCP acronym with drug context while retaining unrestricted full-name coverage. The promoted historical addition is recorded for future scope planning without advancing the coverage date of all other search modules. This is an appropriate separation. Mechanical completion and these record counts do not establish literature-search recall; unresolved records remain explicit limitations.

Evidence: [search history](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/discovery/search_history.json>), [versioned strategy](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/discovery/search_strategy.v3.json>).

## Preserve scientific QA during normalization

Schema-valid JSON is not equivalent to source-verified scientific accuracy. Saved advisory QA flags occur in **385 review reports** and **202 meta-analysis reports**; these counts are reports with one or more flags, not confirmed erroneous papers.

Review flags mainly concern central-aspect coverage and relationship importance. Meta-analysis flags include nonverbatim support text, bundled estimates, contradictory significance wording, and unsupported numeric values. Some can reflect formatting or optional-field issues; others warrant withholding individual findings. The meta-analysis converter already holds several serious cases, including bundled estimates, unsupported estimate values, and incompatible support/interval combinations. Preserve those holds and inspect the resulting disposition report before graph admission.

Evidence: [meta-analysis converter](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/kg/convert_meta_analysis_v2_to_evidence_rows.py:435>). This audit revalidated every output's structure and relevant deterministic guards; it did not source-review all 25,456 reports.

## Reproducibility and tests

The focused offline suite returned **284 passed, 24 subtests passed, and one failure**. The failure is a missing `bs4` dependency when importing the source-repair path, rather than a failed scientific assertion. Supplying the already-installed Beautiful Soup package from the PDF environment to one temporary test process made that entire test file pass: **11 passed**. The ordinary environment remains missing that dependency.

Dependency declarations also differ from the recorded batch runtime: `pipeline/requirements-models.txt` constrains OpenAI below version 3, while the run-specific runtime records `openai==3.36.1`. The ordinary audit interpreter has OpenAI 2.15.0 and pandas 3.0.0; the declared pandas range is below 3. Consolidate the intended environment and dependency declarations before the next repeated update. This is a reproducibility issue, not evidence that the existing saved outputs are invalid.

The run state and dated runbook preserve useful history but mix old preparation counts with current recovery counts. Generate the current handoff summary from actual family inventories and dispositions, leaving historical receipts immutable.

## Recommended next sequence

1. Complete/reconcile the staged screening correction and explicitly record the accepted eligibility version.
2. Reconcile all source holds and dispositions; freeze a single normalization input manifest covering primary/guideline, review v2, and meta-analysis v2, with recovery lineage and asset hashes.
3. Convert all three families and assemble a **fresh Luna replacement release**, then run evidence/entity normalization with an explicit new run ID. Do not carry old Gemini evidence into this full replacement as if it were a routine incremental update.
4. Review scientific QA holds, graph admission, corpus disposition counts, and entity identity checks; build the local preview for inspection.

No new Luna graph build was found. The active routed release pointer still identifies `living_update_20260917_author_identity_reviewed`, so the existing preview is not evidence that Luna normalization has already happened.

## Audit artifacts

- [Reproducible read-only reconciliation script](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/normalization_readiness_20261025/audit.py>)
- [Machine-readable results, handoff findings, and example staged scope differences](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/normalization_readiness_20261025/audit_results.json>)
- [Focused test record](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/normalization_readiness_20261025/test_results.json>)

Only audit artifacts were written for this assessment. Scientific decisions, accepted model outputs, canonical tables, and release pointers were not changed.
