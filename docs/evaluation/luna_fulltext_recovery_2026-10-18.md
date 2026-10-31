# Full-text recovery after Luna screening — 18–19 October 2026

**All 1,951 papers in the remaining browser queue have been reviewed. The browser and automated follow-up passes are complete; your manual recovery pass remains. Evidence extraction has not started.**

| Measure | Before this full browser pass | Now |
|---|---:|---:|
| Eligible reports | 22,469 | **22,451** |
| Usable verified article text | 10,484 | **10,855 (48.3%)** |
| Further usable article texts | — | **+371** |
| Browser/manual queue | 1,951 | **1,563** |
| Expected Luna Batch extraction cost | $28.60 | **$28.99** |
| Planning allowance | $39.93 | **$40.49** |

## New recoveries

| Verified new article-text source | Papers |
|---|---:|
| PDF converted through GROBID | 275 |
| Original PDF recovered through OCR | 38 |
| Complete English publisher HTML | 58 |
| **Total new usable texts** | **371** |

The original queue accounts for 370 recovered DOI records. One additional published DOI gained its text through a reconciled wrapper identifier. Two duplicate identifiers were suppressed. Sixteen records were excluded under the existing publication-format/language rules: three theses, two conference abstracts, seven non-English articles, two letters, and two news/commentary items. The frozen Luna screening table is unchanged.

The first pass covered every queue entry. Follow-ups included 441 known independent OA/repository locations, 179 publisher viewer/download cases, 494 distinct saved PDF locations, 125 potentially complete HTML pages, 13 correct-main retries and 105 final browser/network retries. These scopes overlap. A small final focused web-search pilot found no further complete public article. No author requests, login submissions, paid access or security-check bypasses were used.

## Source checks

Printed titles/front matter, body excerpts, language, publication format and article boundaries were checked before import. The new-artifact body/readability audit covers all 371 additions, with no unresolved automatic body-quality flags. The authoritative source-identity audit passes for all 15,552 stored article artifacts. There are no pending or failed conversions in the approved source batches.

The audit rejected 129 source-to-paper assignments: 24 supplementary/data-only copies and 105 unrelated papers or bibliographic conflicts. Some PDFs were encountered for multiple requested records; these are assignment counts. Rejected bytes and the review evidence are preserved. The requested papers remain eligible unless there is a separate positive format/language decision. None of the rejected foreign PDF URLs was present in the current candidate URL fields, so no candidate source URL was rewritten.

Complete HTML text was accepted only after checking current-paper narrative; previews and abstract-plus-reference pages were rejected. A bilingual article retained its complete explicit English narrative. OCR derivatives retain their original PDF and per-page provenance; exact formulae, symbols, spectra and complex tables can still require checking against the original. One chemical-table scan remains held for manual review.

## Your manual pass

[Browser checklist](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/fulltext_recovery_20261018/browser_full_pass_20261018/manual_recovery.html) · [CSV](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/fulltext_recovery_20261018/browser_full_pass_20261018/remaining_manual_review.csv) · [clean download inbox](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/raw/papers/manual_pdf_inbox/luna_fulltext_browser_manual_after_full_pass)

The browser checklist supports title/DOI search, category filters, locally saved notes/handled markers, PDF filenames and annotated CSV export. Checklist markers do not import a paper or change eligibility. Place new main-article PDFs in the clean inbox; the earlier mixed staging inbox contains rejected material and should not be bulk-imported.

| Remaining manual category | Papers |
|---|---:|
| saved document review | 3 |
| bibliographic identity review | 1 |
| publisher reader or download | 188 |
| browser or publisher error | 116 |
| security challenge | 143 |
| correct main article needed | 117 |
| publisher login or paywall | 129 |
| no usable public copy found | 866 |
| **Total** | **1,563** |

Four entries already have saved PDFs needing a decision: two publication-format policy reviews, one difficult chemical-table OCR source, and one bibliographic title/DOI conflict. The checklist opens those originals. Other entries still need the correct complete main article or successful browser access. Technical failures are not evidence of closed access.

The entire eligible cohort still contains 11,596 papers without usable text. Of those, 10,033 are outside this specific browser queue, predominantly provider-negative/no-access records. The 1,563-row handoff is the remainder of the requested 1,951-paper scope. Additional lawful copies may exist elsewhere online.

## Extraction inputs

Local inputs now contain **37,506 ready extraction tasks across 22,451 papers**. The eligible paper set, input/source hashes, prompt/schema hashes and representative production request bodies were checked. Current Luna prompts, schemas, low reasoning setting and packet-selection methods are unchanged. No input exceeds the configured model limit. No evidence-extraction model calls or jobs were submitted.

The cost is a local estimate from the saved official pricing snapshot and prior metered Luna usage. The $40.49 allowance permits input cache-write premiums and output variation; it is not a guaranteed cap. Inputs and cost remain provisional until your manual source recovery is reconciled. The published graph pointer is unchanged.

## Provenance

[coverage and reconciliation receipt](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/fulltext_recovery_20261018/browser_full_pass_20261018/recovery_summary.json) · [All browser outcomes](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/fulltext_recovery_20261018/browser_full_pass_20261018/browser_observations.json) · [Append-only browser observations](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/fulltext_recovery_20261018/browser_full_pass_20261018/runner_results.jsonl) · [Rejected source assignments](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/fulltext_recovery_20261018/browser_full_pass_20261018/document_source_holds.json) · [New article body checks](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/fulltext_recovery_20261018/browser_full_pass_20261018/new_article_body_quality_audit.json) · [HTML review](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/fulltext_recovery_20261018/browser_full_pass_20261018/processing_html/document_review.json) · [Current full-text worklist](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/fulltext_recovery_20261018/browser_full_pass_20261018/worklist.final.parquet) · [Cost calculation](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/extraction_refresh_20261019_after_full_browser/cost_projection.json) · [Frozen inputs](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/extraction_refresh_20261019_after_full_browser/input_freeze.json) · [Input verification](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/extraction_refresh_20261019_after_full_browser/verification.json)

Earlier automation recovered 1,231 usable article texts, followed by 15 from the initial 50-case browser pilot. Both gains precede this round’s 371 additions. Earlier snapshots are preserved. [Report before this full pass](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/fulltext_recovery_20261018/browser_full_pass_20261018/report.before_full_browser_pass.md).
