**Pipeline repair plan — revised after confidence review, 6 September 2026**

Start with demonstrated input/data problems. Treat failures reproduced only under particular operating conditions as conditional reliability work. Measure improvement before expanding a repair into broad reprocessing or infrastructure redesign.

This supersedes the earlier six-phase ordering. That ordering put preventive state-management work first and treated condition indexing as a confirmed scientific error. The evidence does not justify either as a universal requirement. No pipeline fixes, model jobs, or publication changes have been performed.

The [audit confidence correction](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/pipeline_audit_2026-09-06.md) distinguishes observed impact, reproduced triggers, and unknown historical occurrence.

| Stage | Work | Completion evidence |
| --- | --- | --- |
| 1. Repair known source loss | Preserve JATS figure captions and table captions/notes. Source-check stored corrupt quantities. | Known source text survives conversion; corrected values are supported by the paper. |
| 2. Verify actual operating paths | Match model/retry/conversion findings to commands and saved jobs actually used. Add small guards enforcing existing documented boundaries where appropriate. | Relevant trigger and regression test; historical impact distinguished from future protection. |
| 3. Measure the repair | Rebuild affected packets separately; compare exact inputs; run a bounded extraction comparison if needed. | Source-checked improvement in findings, with task/token cost. Input changes alone do not establish output improvement. |
| 4. Recover affected work | Apply deterministic corrections and justified scoped re-extraction; assemble and reconcile a fresh candidate release. | Complete accounting, explained changes, preserved unrelated evidence, consistent artifacts. |
| 5. Improve reliability/performance where useful | Larger transaction/recovery changes and cache checkpoint optimization. | Operating conditions or measured overhead justify the change; recovery/equivalence checks pass. |

**First implementation package: JATS input preservation**

The parser drops JATS figure content and extracts inner tables without their surrounding captions/footnotes. This is reproduced on fixtures and present in saved corpus packets. A fresh check of the saved source for DOI `10.1001/archgenpsychiatry.2010.90` found four figure captions and two table captions absent from its serialized saved packet text.

Implement format-aware figure/table extraction. Preserve labels, captions, notes, and source identifiers; avoid duplicates; check TEI behavior for regressions. Rebuild into separate outputs from saved sources and compare the text actually supplied to extraction.

Completion means known source passages survive and unaffected inputs retain their behavior. It does not yet establish improvement in any particular final finding. The 2,590 saved PMC-derived packets and 4,360 captionless tables are inventory counts, not paid job counts or an error-rate estimate.

Source-check corrupt fields alongside this work. The audit found control characters in 57 dose fields from 17 reports and 28 effect-size fields from nine reports. Deduplicate reports and make the smallest source-backed correction. Do not infer a missing unit by deleting a character. Mark an unresolved value explicitly; withholding its entire finding requires a reason tied to the meaning affected, not a blanket rule.

**Conditional operational work**

| Audit item | Trigger and appropriate action |
| --- | --- |
| 2. Scoped route replacement | Direct scoped build targeting the canonical route file. The documented updater avoids this and the runbook forbids it. Enforcing that boundary with a guard is reasonable; implementing scoped merging is optional. |
| 3. Interrupted promotion | Interruption between file commits followed by retry. Injected failure reproduces it; historical occurrence is unproven. Inspect handoffs if relevant and repair recovery before depending on automatic retries across that boundary. |
| 4. Concurrent ledger updates | Two writers read the old ledger before either commits. Sequential updates do not trigger it. Check actual overlap; serialize relevant work or introduce shared transactions if concurrency is needed. No past lost update was established. |
| 5. Active-run overwrite and drift | Direct rebuild reuses an active output location. Add a guard where this builder is used. Investigate the observed graph/ledger discrepancy separately: its cause is not established, and timestamps alone do not justify a release-system redesign. |
| 6. Model dispatch | Prepared model differs from the submission choice. Compare saved manifests and job metadata; correct the relevant configuration and provenance. Mislabeling alone does not require re-extraction. |
| 7. Repeated stale work | Accumulating synchronous/mixed history contains an old fingerprint after current success. Verify the runner/history actually used and correct completion selection where applicable. Historical wasted calls have not been counted. |
| 8. Mutable secondary input | Shared source changes between preparation, execution, or validation. Snapshot or verify sources before intentionally rebuilding packets around outstanding secondary jobs. Historical mismatches remain unproven. |
| 9. Batch completion/retry | Missing/partial results or schema failures. Reconcile expected keys and explicit failures in the batch path being used; inspect saved jobs before claiming historical stranded work. |
| 10. Conversion audit | Direct worklist conversion skips refresh; the managed wrapper already refreshes it. Repair the direct path if supported/used, without describing managed conversion as universally broken. |
| 11. Metadata checkpoints | Whole-cache writes every 100 records have measured local cost. Atomic replacement is small reliability work. Benchmark changed-data checkpoints before adopting a larger storage redesign. |

**Condition splitting: investigation, not a confirmed repair requirement**

The pooled-result example `10.1007/s00213-020-05611-y` retains its mixed-diagnosis population in active findings and the browser payload. Its relation is `studied_for_condition`. The primary card displays the population and a written finding. Because the written finding is present, this card does not display the copied effect statistic as its main finding. The earlier claim that users were being shown diagnosis-specific statistical estimates was too strong.

Indexing a report under diagnoses in its cohort may be intended and useful. Before changing 520 condition-split rows from 123 reports, establish whether a consuming view or API interpretation actually treats them as subgroup estimates. Correct a demonstrated misleading use if found; preserve valid indexing. Duplicated internal fields alone do not justify a pooled/subgroup schema migration or blanket re-extraction.

**Recovery decision**

Inventory actual changed model inputs by DOI, depth, task family, and hashes. Include eligible papers with few or no findings when assessing missing-content impact; unchanged abstract inputs stay outside scope.

Start with a small diagnostic set. Expand to a 30–50-report engineering pilot if needed to cover source formats and literature families. Source-check before/after findings and measure task/token costs. This is not a representative accuracy estimate. Do not commit to re-extracting every changed packet before evaluating the pilot.

Use saved outputs and deterministic corrections where sufficient. Any justified replacement must preserve the complete current contribution of each affected DOI through the appropriate literature workflow. Build a fresh candidate, account for expected tasks, explain changes, reconcile graph/ledger/Methods artifacts, and retain rollback before publication.

Larger transaction changes, checkpoint optimization, the two UI test failures, and broader evidence-methodology proposals remain separate work packages with their own expected benefits. They are not blanket prerequisites for testing the demonstrated source repair.
