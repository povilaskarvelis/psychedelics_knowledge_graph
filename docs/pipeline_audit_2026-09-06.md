**Processing pipeline audit — 6 September 2026**

The audit identified **observed source/data problems, reproducible conditional failures, and measured overhead**. These are different kinds of evidence. The initial summary and repair order overstated their equivalence and urgency. A reproduced failure does not establish that it occurred in past processing, and an unsafe direct command does not establish a failure in the managed updater.

**Confidence correction after tracing the UI and documented update path**

- **Confirmed current input loss:** JATS figure captions and table context are missing from saved extraction packets. A fresh check of the saved artifact and packet for `10.1001/archgenpsychiatry.2010.90` confirmed that its four figure captions, two table captions, and table notes are absent from the serialized packet text. How many final findings are wrong or missing remains unmeasured.
- **Confirmed stored text corruption:** the control-character counts below describe real saved fields. Each affected value needs source verification; counts alone do not establish the intended replacement or the number of visibly incorrect quantities.
- **Reproducible conditional failures, historical occurrence unproven:** findings 2–10 require their stated trigger. In particular, the [runbook](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/scoped_paper_updates.md:201) already forbids scoped canonical route writes, and the [updater](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/update/run_scoped_paper_update.py:343) deliberately rebuilds all routes. Concurrent-write loss requires overlapping writers, not repeated sequential updates. The current ledger/graph discrepancy in finding 5 is observed, but its cause is not established.
- **Withdrawn as a confirmed display error:** the pooled-condition example retains its mixed-diagnosis `population` in both the active finding and browser payload. Its relation is `studied_for_condition`. The [primary card](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/ui/app.js:4397) displays population, sample, and a written finding; [finding text selection](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/ui/app.js:5148) uses the statistic only when the written summary is absent. For this example the summary is present. Copying a report/result into several diagnosis indexes therefore does not by itself prove that the interface asserts separate subgroup estimates. Treat this as a question about indexing and attribution semantics, not an established need to remove or remodel 520 findings.
- **Measured overhead, benefit not yet validated:** finding 11 has a local checkpoint benchmark. Its whole-pass timing is an estimate, not a production incident or a measured speedup.

The P1/P2 labels retained below reflect the original assessment of possible consequence, **not evidence that every item is an urgent production problem**. The revised [repair plan](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/pipeline_repair_plan_2026-09-06.md) prioritizes demonstrated impact and requires validation before larger changes.

This assessment follows discovery → metadata enrichment → screening → retrieval/conversion → extraction inputs → primary/review/meta-analysis extraction → normalization → release assembly/promotion → public exports and Methods. I reviewed the principal entry points and their handoffs, ran the complete Python regression suite, executed 11 isolated diagnostic reproductions, queried the current corpus and graph, and inspected all 2,717 PMC-derived XML artifacts. It is not a line-by-line review of every historical utility or a representative source-to-finding accuracy study. I did not submit model jobs, retrieve new papers, publish anything, or change pipeline implementation or production data.

The inspected commit is `13bff62`. The active local run is `full_corpus_normalization_patch_qa_20260724`, containing 97,195 findings from 21,383 reports. The candidate ledger contains 268,221 unique, nonblank DOIs. Raw DOI joins initially suggested two orphan findings; both resolve through the existing alias registry and are **not** defects.

Evidence, SQL, counts, input/code hashes, and benchmark results are saved in the [evidence file](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/pipeline_audit_2026-09-06_evidence.json). The [offline reproductions](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/pipeline_audit_2026-09-06_reproductions.py) use temporary fixtures and mocked network clients. They assert the observed defects; after fixes, those assertions should fail and be replaced by regression tests for the desired behavior. The [corpus scanner](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/pipeline_audit_2026-09-06_corpus_scan.py) is read-only.

**1. [P1] PMC XML loses figure captions and table context before extraction**

The section parser recognizes JATS `<sec>` elements, but the table/figure parser recognizes TEI `<figure>` rather than JATS `<fig>`. Its fallback extracts the inner `<table>` alone, leaving behind the surrounding `<table-wrap>` caption, label, and footnotes. The section walker deliberately skips these elements, so their content is absent from the model input rather than appearing elsewhere in the packet. [Parser](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/fulltext/build_llm_evidence_packets.py:487), [section walker](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/fulltext/build_llm_evidence_packets.py:402).

The source scan found 9,012 JATS figures across 2,153 artifacts, 4,261 table captions across 1,688 artifacts, and 2,827 table-footnote containers across 1,269 artifacts. The current parser returns zero figures from those artifacts. The saved input file independently confirms the problem: **2,590 PMC-derived packets contain zero figures; all 4,360 saved tables have empty captions**. Of the source artifacts with figures, 1,993 belong to reports represented in the active findings. These are affected-input counts, not counts of proven incorrect findings.

The isolated example loses both a table's unit and its sign convention, plus a figure's null-result statement. Implement explicit JATS figure/table-wrapper handling and preserve captions, footnotes, labels, and row/column structure. Rebuild affected packets and selectively re-extract findings that depended on the missing content. Expanding extraction volume before this repair would propagate the same loss.

**2. [P1] A scoped route build replaces the entire route table**

`build_extraction_routes.py --doi-file …` filters the generated routes to the requested DOIs, then unconditionally writes those rows to its output table. The default output remains the canonical `paper_extraction_routes.parquet`. Candidate status updates are scoped correctly, but the route table itself is not merged. [Write and candidate-update handoff](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/extract/build_extraction_routes.py:1743).

The reproduction builds routes for A and B, then rebuilds A into the same output: B disappears. Subsequent task construction or conversion with the active-route gate can then omit otherwise valid out-of-scope work. This affects the direct scoped CLI; the documented scoped-update orchestrator's full route refresh avoids this particular trigger.

Either replace only the selected DOI contributions under a transaction, or require an explicitly separate output path for scoped builds and refuse the canonical default. Verify preservation of all out-of-scope route rows.

**3. [P1] Retrying interrupted discovery promotion loses the new-paper handoff**

Promotion writes candidates, contexts, unresolved records, DOI handoff files, history, and the manifest sequentially. Atomic replacement of individual files does not make that sequence transactional. If execution stops after the candidate table is replaced, the retry regards the newly inserted DOIs as rediscoveries. It also overwrites the original pre-promotion backup. [Promotion commit sequence](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/discovery/promote_search_run.py:598).

With an injected failure at the context-table write, a new DOI survives in the candidate ledger but the successful retry writes an **empty `new_candidate_dois.txt`**, reports zero new records, and advances promotion history. The normal enrichment/screening handoff can therefore miss it.

Persist the intended promotion delta and original backups before committing, then resume that same transaction after interruption. Recovery must preserve the original new-DOI cohort rather than recomputing it from partially committed tables.

**4. [P1] Concurrent candidate updates silently lose successful writes**

The shared candidate updater reads the entire ledger, applies changes in memory, and atomically replaces the file without a lock or version check covering the read–modify–write operation. Two workers can each read the old ledger and then overwrite each other's changes, even when updating different DOIs. [Shared updater](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/ingest/candidate_status.py:38).

The barrier-controlled reproduction performs two disjoint updates. Both report success; **only one persists**. The release-promotion lock does not protect ordinary callers of this helper, and other stages also write whole candidate snapshots. This is a demonstrated concurrency defect, not evidence that a particular production update was lost.

Use one shared ledger transaction/locking mechanism across all writers, holding it from reading through replacement, or apply versioned deltas with conflict detection. Serializing only each final rename is insufficient.

**5. [P1] Reusing an active run ID bypasses release isolation; current artifacts already disagree**

The KG builder protects the legacy `data/processed/kg` path, but does not protect the versioned directory referenced by the active pointer. Reusing the active run ID reaches a builder that deletes existing tables before writing replacements. The build shell script does this before any optional promotion, so `ACTIVATE_DEFAULT=0` does not prevent active-directory mutation. [Overwrite guard](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/kg/build_evidence_tables.py:10845), [table replacement](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/kg/build_evidence_tables.py:10678), [build entry point](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/scripts/build_routed_kg_payload.sh:81).

The isolated CLI probe confirms that the active output directory is accepted without an overwrite flag; actual writes are mocked. The current data also exposes a consistency gap: DOI `10.1080/14746700.2026.2637223` has a finding in the active KG but remains `not_represented` in the candidate ledger. The project's own graph-status writer defines representation from all finding DOIs. The KG and payload manifests were generated on July 28, while the Methods manifest and candidate graph decisions date to July 24 under the same evidence release ID. These observations establish drift; they do not identify the historical command that caused it.

Both `validate_active_pointer_pair()` and `validate_active_public_release()` currently pass. Their checks verify identifiers and public-file checksums, but do not reconcile this finding/ledger discrepancy. [Pointer validation](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/publish/promote_routed_run.py:534).

Make activated evidence snapshots immutable, require a new build/run identity, and stage replacements before publication. Bind graph/Methods decisions to the actual evidence snapshot and verify represented DOI sets, including alias handling, as part of release validation.

**6. [P2] Primary batch submission ignores prepared model choices**

Preparation records `model_for_task(...)`, which honors text-depth-specific and generic model settings. Submission instead chooses `args.model or DEFAULT_GEMINI_MODEL` and does not reconcile that choice with the prepared records. The serialized per-row requests contain no model override. [Prepared metadata](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/extract/run_route_extraction_batch_api.py:275), [submission](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/extract/run_route_extraction_batch_api.py:414).

The mocked submission declares `task-configured-model` in the manifest but dispatches `gemini-3-flash-preview`. This can change cost and extraction behavior, while the parsed raw record continues to report the manifest's model. Partition prepared tasks by their resolved model, submit that model, and record the actual job model as execution provenance. Reject conflicting submission overrides.

**7. [P2] A successful correction can remain eligible for extraction indefinitely**

`stale_input_fingerprint_task_keys()` flags a route when **any historical row** has a different fingerprint. The synchronous accumulating runner retains both old and new attempts. Consequently, after a repaired input has already been successfully extracted, the older row continues to release the route on every subsequent batch selection. [Fingerprint check](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/extract/run_routed_extraction_batch.py:112).

The reproduction contains an old successful attempt and a newer successful attempt matching the current task. The route is still classified as stale. This can repeatedly spend model calls and obstruct queue completion. Use the latest applicable attempt/current successful fingerprint when deciding completion. The async-only materialized projection usually removes historical rows, so this specific trigger primarily affects accumulating synchronous or mixed histories.

**8. [P2] Review/meta-analysis source fingerprints are recorded but not enforced at use time**

Secondary tasks save a source fingerprint and a path to the shared packet file. Their runners reload the packet by ID/DOI and use its current text without checking that fingerprint. Rebuilding `fulltext_packets.jsonl` after task construction can therefore change the source sent to the model while retaining the old task identity and source hash. Meta-analysis result validation also reloads source text during parsing. [Review source loader](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/extract/run_review_relationship_extraction.py:157), [meta-analysis source loader](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/extract/run_meta_analysis_v2_batch_api.py:292).

The reproduction changes a packet's text after constructing the task. Both loaders accept the changed text although its hash differs. Snapshot the exact selected packets/request text within the run, verify source hashes before preparation/submission, and validate responses against the source snapshot used by that job. Prompt/task snapshots alone do not freeze an external packet path.

**9. [P2] Batch completion reporting and retry selection can strand failed work**

The primary batch parser iterates only the result rows it can read. The shared JSONL reader returns an empty list for a missing file; the parser does not reconcile the returned keys with the manifest. An absent results file therefore produces an `ok` report with zero results, and its expected routes remain reserved. [Parser](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/extract/run_route_extraction_batch_api.py:691).

There is a related schema-failure path: the parser's overall status excludes `schema_error` from its failure check, while `--retry-errors` still treats rows present in the parsed output file as completed. An isolated schema-failure record remains excluded from retry. [Completion status](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/extract/run_route_extraction_batch_api.py:785), [retry selection](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/extract/run_routed_extraction_batch.py:92).

Require the result artifact, reconcile expected/returned keys including duplicates, assign explicit missing-result failures, and include schema failures in the actionable failure accounting. Reservation state must release completed failed attempts for controlled retry or explicitly place them in a review queue.

**10. [P2] The direct worklist PDF-conversion path does not refresh its identity audit**

`convert_fulltext_worklist_pdfs.py` always supplies a selection table. In the underlying converter, identity-audit refresh is conditional on `selection_table is None`, together with route rebuilding. Successful worklist conversions consequently leave the authoritative audit unaware of the newly written artifact. [Conditional](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/fulltext/convert_routed_local_pdfs.py:456).

The isolated conversion writes one artifact but never calls audit refresh. Downstream identity-gated routing/packet preparation can reject it or treat it as unavailable until a separate audit runs. The managed batch orchestrator has its own audit step and avoids this gap; the direct worklist command documented in the full-text guide does not. Refresh the audit after successful writes independently of whether extraction routes should be rebuilt, matching the PMC XML path.

**11. [P2] Metadata checkpoints repeatedly rewrite the entire cache**

The enrichment runner merges and rewrites every cached DOI at each 100-row checkpoint, including passes that simply reuse existing metadata. Writes go directly to the destination Parquet file, so interruption during a checkpoint also threatens that cache's readability. [Checkpoint loop](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/ingest/enrich_paper_metadata.py:657), [writer](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/ingest/enrich_paper_metadata.py:141).

A single temporary-file benchmark of the existing 131,099-row cache took **0.905 seconds to merge and 1.877 seconds to write 135.3 MB**, excluding its initial 3.155-second read/index. At unchanged cache size, a 10,000-row pass triggers approximately **13.5 GB of checkpoint writes and 4.6 minutes of merge/write work**, before the final checkpoint or provider requests. Those scaled figures are estimates from one local measurement, not measured end-to-end runtime.

Append small durable result checkpoints, then compact once or periodically by elapsed time/changed-data volume. Avoid rewriting unchanged cached rows and use atomic replacement for compaction.

**Stored quantity corruption and a condition-indexing question**

The [5 September assessment](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/project_critical_assessment_2026-09-05.md) documented source checks and corrupt dose units. Its pooled-result interpretation needs the UI qualification above: the mixed population is preserved and displayed, and the copied statistic is not displayed in that primary card. This audit initially rechecked implementation and counts without adequately tracing that distinction.

- **Condition attribution — needs semantic validation:** `condition_expanded_rows()` copies a result, including its statistic and sample-size fields, for each recognized condition without requiring subgroup evidence, while the example's original mixed population remains available. The active findings contain **520 rows from 123 reports** marked `condition_text_split`. That identifies a potential review cohort, not proven errors. Establish whether downstream consumers treat these as report associations or subgroup results before proposing changes. [Expansion code](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/kg/build_evidence_tables.py:7636).
- **Scientific quantity integrity:** **57 dose fields from 17 reports and 28 effect-size fields from 9 reports** still contain disallowed ASCII control characters. New primary model responses have a corruption check, but release assembly/builds do not apply an equivalent gate to all carried-forward findings. Revisit affected quantities against their sources and gate complete releases; deleting a corrupt character alone cannot recover a missing unit.

There are also methodological limitations that should remain distinct from software defects: all 82,297 primary findings have an empty dedicated supporting-quote field; 86,584 candidate records are excluded for lacking a usable abstract, including 172 with a local-PDF flag; and report counts do not resolve study/cohort independence. Locators and summaries still provide some provenance, local PDF flags do not prove eligibility, and these counts do not estimate screening or extraction accuracy.

**Verification and repair order**

The regression run produced **1,105 passed, 2 failed, and 367 passing subtests** in 22.74 seconds. The failures are the favicon-markup and constrained graph-column CSS assertions. They are outside the evidence-processing core and need review as potentially stale UI tests; this audit did not establish a visual defect from those assertions alone. [Test output](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/pipeline_audit_2026-09-06_pytest.txt).

Both active-pointer and public-payload validation pass, and the existing DOI alias machinery resolves the apparent orphan findings. These safeguards are useful, but the reproductions show that the current suite does not exercise several failure and concurrency boundaries.

Prioritize the demonstrated JATS input loss and source-check confirmed corrupt fields. Small guards can enforce existing documented operational boundaries without redesigning the workflow. Establish which conditional failures affect the commands actually used before broader transaction or runner changes; do not make an all-writer redesign a prerequisite for measuring the input repair. Require a before/after pilot before authorizing a large extraction rerun. No production fixes were applied as part of this assessment.
