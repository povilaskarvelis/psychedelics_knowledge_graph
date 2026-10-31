# Literature update — 15 October 2026

## Scope and checkpoint

Corpus surveillance using the existing v3 PubMed/OpenAlex protocol and canonical
research scope. The previous promoted discovery run is
`living_update_v3_20260915`, covering through 15 September. This run is
`living_update_v3_20261015`, covering 1 September–15 October with the protocol's
14-day overlap. Scope and strategy hashes match the previous search.

The saved plan contains 345 executions: 113 PubMed publication-date searches,
113 PubMed Entrez-date searches, and 119 OpenAlex publication-date searches.
OpenAlex historical indexing backfill remains outside this elapsed-period run.
Provider count reconciliation measures mechanical retrieval completeness, not
search recall.

The active graph baseline is `living_update_20260917_author_identity_reviewed`.
Pre-update canonical snapshots and checksums are stored under
`data/processed/corpus/living_update_20261015/baseline/` and
`baseline_manifest.json`. Existing UI changes predate this update.

## Authorized handoff

Run discovery, metadata enrichment, screening, and bounded automated full-text
recovery. At the manual-access boundary, provide a deduplicated list of papers
with potentially accessible full text, grouped into batches of at most 50, for
the user to inspect and download. Do not automatically open the batches. Manual
downloads go into `data/raw/papers/manual_pdf_inbox/`. Unsuccessful retrieval
remains an access state rather than an eligibility exclusion. Complete graph
extraction and promotion after the manual source-recovery pass.

## Progress

- Plan: saved and inspected; 345 executions; no scope changes.
- Regression preflight: 106 tests and 52 subtests passed across discovery,
  screening, and manual-PDF queue handling.
- Discovery: complete and promoted; all 345 executions reconciled without
  failures or count drift. 20,564 hits, 2,395 unique provider records, 1,031 new
  canonical DOI candidates, 987 rediscoveries, and 69 unresolved no-DOI records.
- Screening handoff: 1,034 DOIs (new records plus three restored abstracts).
- Abstract recovery: 331 from PubMed and 16 from Crossref. The optional
  Semantic Scholar stage returned HTTP 429. Completed PubMed/PMC checkpoints
  were reused in a separately identified fallback run; the failed original
  manifest and checkpoint-inheritance hashes remain available. No contaminated
  abstracts were found by the quality repair stage.
- Prescreen: 373 retained; 286 clearly unrelated, 196 non-evidence artifacts,
  76 preprints/unpublished records, 68 unusable abstracts, and 35 non-English.
- Standard-API screening: all 373 succeeded; 220 model-included and 153
  model-excluded. Eight parts ran with four concurrent workers, using the
  previous model and prompt. No provider batch job was submitted.
- Source review: 21 of the included records were excluded under existing scope
  and source-format rules. Two already-excluded records also received durable
  corrections for mismatched abstracts. The final cohort is 199 reports.
- Automated full text: 37 DOI-verified PMC XML artifacts and 44 validated PDFs
  recovered. Access refresh checked the other 163 reports and found fresh OA
  evidence for 118. Four transient PDF failures were retried once, with no
  further PDF recoveries. Alternate-source lookups added three PMC identifiers;
  a second XML pass recovered one additional article (included in the 37 total).
- Manual handoff: 73 potentially accessible reports in batches of 50 and 23.
  Another 45 reports have provider-reported closed access, without browser
  verification. They remain eligible and are preserved in an optional list.
- Extraction and graph release: waiting for manual PDF collection. The active
  September graph release is preserved.

Use standard-API screening for this cohort, preserving raw results and retrying
only failed records; avoid the batch-provider wait encountered in September.

## Manual PDF handoff

Readable list: [`literature_update_2026-10-15_pdf_review.md`](literature_update_2026-10-15_pdf_review.md).

All operational artifacts are under
`data/processed/corpus/living_update_20261015/`. The `manual_fulltext_review/`
directory contains the HTML list, CSV, batch URL files, browser batch manifest,
and optional provider-closed list. All 73 DOI/article URLs are unique. No exact
normalized-title duplicates were found within the cohort or under another DOI
in the active graph. Similarity checks remain candidate signals, not proof of
report identity.

Save manual downloads into `data/raw/papers/manual_pdf_inbox/`. Import and verify
them before conversion. The 44 automated PDFs are already stored under
`data/raw/papers/pdfs/`; their PDF signatures and stored SHA-256 checksums were
verified at handoff. Convert automated and manually imported PDFs together after
the manual pass, then build extraction routes and run all applicable primary,
review, meta-analysis, and consensus pipelines.

## Fixes and observed limitations

- Fixed the screening DOI-list reader: commas in valid DOI suffixes were being
  treated as CSV delimiters even in newline-delimited `.txt` files. The queue
  initially lost one retained report; it was regenerated to account for all 373
  records before model calls. A regression test covers comma-bearing plain-text
  DOIs and quoted CSV input.
- Added `--require-automated-retrieval-complete` to manual-queue export. A final
  handoff now refuses pending PMC, access-refresh, or unattempted direct-PDF
  actions and preserves the existing queue. This caught the second-wave PMC
  handoff gap demonstrated by this update. Three regression cases cover the
  protected output behavior.
- Saved 11 metadata corrections and 23 report-level exclusions in the existing
  curated registries. These include publisher-confirmed language corrections,
  a lecture misidentified as a guideline, background-only mentions, a proposal
  without completed results, and two title/abstract mismatches. Original model
  decisions and source snapshots remain under the run directory.
- Corrected the ClinicalTrials.gov landscape analysis
  `10.1186/s13063-026-10053-6` to use the review family rather than primary-study
  extraction.
- Optional provider failure still prevents the abstract-enrichment command from
  reaching its final merge. Completed checkpoints make recovery possible, but a
  first-class partial-provider/fallback completion path would remove this
  operational workaround.
- Full-text preparation and source-identity audit still scan historical
  artifacts during small updates. Content-hash-based incremental reuse remains
  a material efficiency improvement; verification must be preserved.
- Model screening required source review for false positives and publication
  types. Language detection identified candidates, and publisher metadata or
  original source text supported the resulting source-language decisions.

Validation: initial preflight 106 tests and 52 subtests passed; the later focused
metadata, extraction-route, and screening regression run passed 60 tests.
The final handoff, worklist, and screening regression run passed 27 tests.

## Manual review — batch 1 completed 16 October 2026

- Imported all 30 inbox PDFs into the canonical PDF store after document identity checks; all stored hashes match. Two ambiguous matches were resolved against article titles, authors, journal details, and source location. No unresolved files remain.
- Excluded `10.1016/j.dld.2026.07.043` in the canonical post-retrieval eligibility ledger. The user identified a conference/poster abstract; Crossref independently matches its PII and supplement page S18. The eligible update cohort is now 198 reports.
- Batch 1 reconciles to 30 recovered, 1 excluded, and 19 reviewed without an accessible PDF. These 19 retain provider OA metadata; the mixed report of failed links and paywalls does not prove closed access per record. Retrieval suppression and browser progress preserve that distinction.
- Available source files now cover 111 reports: 37 PMC XML and 74 PDFs (44 automatic + 30 manual). Another 23 await batch 2 review, 19 were reviewed without a usable PDF, and 45 remain provider-reported closed without browser verification. Original batch files and numbering are preserved.
- Reconciled stale candidate selection through the existing scoped route builder before import. The post-screen full-text worklist does not project selection to candidates, so the importer initially refused all matched PDFs in its dry run. Documented the required selection-preparation step; historical candidates outside this update were unchanged.
- Browser reconciliation now reads the current post-retrieval eligibility ledger by default and ignores explicit retain decisions. Added the completed `reviewed_no_accessible_pdf` outcome so a finished mixed-access batch can avoid repeated retrieval without falsely setting every paper to closed access. Later recovery still removes suppression.
- Fifty focused importer, eligibility, reconciliation, and queue tests passed. All 30 imported PDF hashes verified; the inbox is empty; active graph and extraction pointers remain unchanged. PDF conversion and extraction await completion of the manual collection pass.

## Manual review — batch 2 completed 16 October 2026

- Imported and verified all 16 batch-2 PDFs; the inbox is empty and there are no unresolved document matches.
- Excluded `10.13023/2020.ruhrc/15` and `10.13023/2026.ruhrc/32` per the user’s source/scope decision. Repository source review identifies research-center reports rather than journal-article citations. The first report is dated November 2020, contrary to the provider-derived 2026 date; a durable curated correction and scoped candidate materialization restore the source date.
- Batch 2 reconciles to 16 recovered, 2 excluded, and 5 reviewed without an accessible PDF. All 73 manual records now reconcile to 46 recovered, 3 excluded, and 24 reviewed without usable PDFs; no record is left pending and original batch numbering is preserved.
- The eligible update cohort now contains 196 reports: 37 PMC XML, 90 PDF sources (44 automatic + 46 manual), 24 manually reviewed without usable full text, and 45 provider-reported closed without browser verification. PDF conversion has started; extraction and graph release remain unchanged.
- Persisted the two exceptional batch-1 document identity reviews in the existing exact-PDF-hash registry so later conversion and verification can reuse those decisions without loosening identity checks.

- Made the canonical post-retrieval eligibility ledger eligible for Git tracking. It was unintentionally covered by the generic ignored-data rule, so positive source exclusions could be omitted from future repository checkpoints. No commit or push was performed.

- All 90 selected PDFs converted successfully through GROBID and passed the converter’s source-identity write gate. A global source-identity audit is running before the extraction routes are refreshed.

- The complete source-identity audit passed: all 13,935 artifacts verified, including the 90 newly converted PDFs. A versioned audit snapshot is saved with this update. The update has 127 verified full-text reports and 69 abstract-only reports; extraction preparation is the next stage.
