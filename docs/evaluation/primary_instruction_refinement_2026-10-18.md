# Primary extraction refinement — 18 October 2026

**Recommendation: retain the current Luna extraction prompt and the tested normalization repairs. Do not promote the broader instruction rewrite. Keep the current schemas.** The rewrite improves the familiar sets substantially but does not show a convincing benefit on the new set: coverage rises only 2.6 percentage points, material errors increase, and more central findings are entirely missing. The full extraction rerun has not started; no graph was published.

## Clear performance comparison

Both arms were generated anew with GPT-6 Luna, low reasoning effort, identical source packets, assigned domains, unchanged native schemas and output limits. Only the extraction instructions differ. Both use the same frozen normalizer for this table.

| Papers | Current Luna: full coverage | Refined Luna: full coverage | Current: material errors | Refined: material errors |
| --- | --- | --- | --- | --- |
| Existing audit (96) | 240/317 (75.7%) | 271/317 (85.5%) | 19 items / 15 papers | 20 items / 14 papers |
| Controlled historical set (40) | 63/84 (75.0%) | 73/84 (86.9%) | 8 items / 4 papers | 7 items / 3 papers |
| Previous fresh set (48) | 104/165 (63.0%) | 129/165 (78.2%) | 2 items / 2 papers | 3 items / 3 papers |
| New unseen set (64) | 106/151 (70.2%) | 110/151 (72.8%) | 2 items / 2 papers | 5 items / 4 papers |

The first three sets are development evidence; only the 64-paper set is new validation. “Coverage” means fully retained **central finding-and-qualification groups**, not the fraction of all facts in a paper. “Material errors” includes wrong numbers, bindings, scientific roles and unsupported specificity; it excludes scope disputes, minor wording and uncertain source corruption. It is not an accuracy percentage. Every one of the 1,969 newly generated items received a source and graph review.

## What the fresh set actually says

| New 64 papers | Current Luna | Refined Luna |
| --- | --- | --- |
| Central groups fully covered | 106/151 (70.2%) | 110/151 (72.8%) |
| Partially covered groups | 26 | 20 |
| Entirely missing groups | 19 | 21 |
| Material-error items / papers | 2 items / 2 papers | 5 items / 4 papers |
| Eligible tasks incorrectly returned empty | 0 | 2 |
| Out-of-scope tasks incorrectly returned findings | 3 | 1 |
| Items generated | 159 | 165 |
| Same-task API cost | $0.0814 | $0.0921 (+13.1%) |

Among 55 papers with scored central groups, the candidate improves 13, worsens 9 and ties 33. Its mean within-paper coverage gain is 1.4 percentage points; an exploratory paper-level bootstrap 95% interval is −7.3 to +10.2 points. This sample does not establish a reliable overall improvement. The error counts are small, so they also do not prove a precise population-wide worsening rate. They are enough to reject an automatic upgrade under the predeclared promotion rule.

| Fresh stratum | Current coverage | Refined coverage | Current errors | Refined errors |
| --- | --- | --- | --- | --- |
| Ordinary (32) | 53/73 (72.6%) | 49/73 (67.1%) | 1 item / 1 paper | 3 items / 2 papers |
| Challenging (32) | 53/78 (67.9%) | 61/78 (78.2%) | 1 item / 1 paper | 2 items / 2 papers |
| Abstracts (32) | 45/55 (81.8%) | 47/55 (85.5%) | 0 items / 0 papers | 1 item / 1 paper |
| Article packets (32) | 61/96 (63.5%) | 63/96 (65.6%) | 2 items / 2 papers | 4 items / 3 papers |

The rewrite helps the challenging half but loses coverage in the ordinary half. This is the new finding that the familiar datasets could not establish. It also returns no extraction for a ketamine sensitization study despite the assigned safety contract including abuse-liability evidence (N60), and omits the eligible ayahuasca-tourism observation in N57. These are scope/coverage failures, separate from factual errors.

### All confirmed fresh factual errors

| Paper | Prompt | What is wrong | Why it counts |
| --- | --- | --- | --- |
| N40 | Current | Reports 36 participants for the self-rated comparison | Source says all 37 assessed; t(35) is an independent-samples test, not a paired-test denominator. |
| N52 | Current | Calls 18.20 the median and 22.43 the mean | Intact table: median 12.07, mean 18.20, SD 22.43. |
| N22 | Refined | Types urinary nondetection as a metabolized-via relationship | Correct nondetection prose, wrong typed scientific relationship. |
| N42 | Refined | Supplies 6/group for a 5-MeO-MET head-twitch result | Six/group belongs to a different compound/optimization experiment; target denominator unavailable in supplied packet. |
| N53 | Refined | Reports stability accuracy upper bound 108.62% | All quality-control levels extend to 113.04%; a table column is omitted. |
| N64 | Refined, 2 items | Calls 14.5 sessions the mean | It is the median; mean 13.8. Main subjective-rating estimates are correct. |

All six cases received a second source check by a reviewer other than the original reviewer. N42 is unsupported specificity, not proof the actual experimental denominator differed. N53 and N64 are numerical metadata mistakes, not reversals of the study's main conclusion. See [fresh paper casebook](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/primary_refinement_cases_2026-10-18/fresh.md>) and [independent checks](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_refinement_20261018/reviews/fresh_independent_root.json>) / [numeric checks](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_refinement_20261018/reviews/peer_numeric_fresh_agent_a.json>).

## Normalization fixes, tested independently

No model calls were used to test deterministic repairs; the raw saved extractions were held unchanged.

| Stage | Unchanged saved item instances | Changed projections | Validation |
| --- | --- | --- | --- |
| Before paired prompt experiment | 3,410 across 12 saved arms | 471 | 273 tests + 305 subtests; frozen-before reproduction passed. |
| Additional repairs after scientific review | 5,379 across 20 saved arms | 334 | 322 tests + 305 subtests; 39 saved-output checkpoints; frozen-before reproduction passed. |

These are repeated item instances across model/prompt arms, not independent papers or counts of scientific errors fixed. The stages overlap and must not be added. The later 334 changes comprise 200 main records with changed fields, 51 detail records with changed fields, 54 main-to-detail moves, 27 audit-to-detail recoveries and 2 detail-to-main moves. No previously represented raw item disappears into audit-only storage.

| Repair family | Concrete improvement |
| --- | --- |
| Chemical identity | Distinct derivatives retain their identity instead of inheriting LSD, bufotenin or 5-MeO-DMT; specific ketamine takes precedence over its descriptive drug class. |
| Study design / timing / comparators | Explicit RCTs retain randomization; baseline-plus-follow-up is not reduced to baseline; saline remains inactive placebo and escitalopram an active treatment. |
| Clinical and biological labels | Drug use does not become a diagnosed use disorder; diarrhea does not become nausea; IL-10 cannot match IL-1. |
| Roles and graph admission | Laboratory assay validation and anticipated concerns stay distinct from observed exposure or harm; rescue packages retain their actual combination context. |
| Retention | Study-local numbered compounds survive as detail; single-drug chemical names do not become mixtures solely because of punctuation. |

The later repairs were developed after seeing validation failures, so they are **regression-tested repairs, not another unseen validation result**. Independent implementation checks covered 18 changed controlled-set items plus 23 unchanged controls; the lead reviewer checked all 25 changed fresh projections. Five of the six strict wrong canonical fresh records are corrected; the remaining N22 parent-MDA projection is documented.

There are real tradeoffs and residuals: broad open-label descriptions now receive unknown allocation, which loses useful specificity for genuine single-arm studies; N04 and H24 still show schedule-versus-result timing ambiguity. Some rescue packages move to details and lose valid atomic-drug visibility. Complex compound-kind text, pooled-exposure attribution, circuit/result binding and vocabulary gaps remain. **This is not a claim that every normalization problem is solved.** Full lineage and checks: [first repair report](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_refinement_20261018/normalization_repairs.md>) · [postvalidation repair report](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_refinement_20261018/postvalidation_normalization/report.md>).

## Extraction and graph errors are different

The following uses the **frozen pre-comparison normalizer**, before the later repairs, to isolate the prompt effect. A wrong canonical record has an incorrect graph subject, endpoint, relation or admission. A bad metadata record can have a correct edge but wrong design, timing, population or combination label. Counts refer to finding records, not unique edges or precision percentages; granularity differs between arms.

| Set | Wrong main canonical records: current → refined | Main records with any material extraction/graph defect: current → refined | Extracted items losing valid links: current → refined |
| --- | --- | --- | --- |
| Existing audit (96) | 8 → 16 | 119 → 196 | 37 → 36 |
| Controlled historical set (40) | 4 → 6 | 12 → 22 | 7 → 9 |
| Previous fresh set (48) | 0 → 0 | 27 → 33 | 17 → 23 |
| New unseen set (64) | 3 → 3 | 25 → 23 | 6 → 13 |

The candidate does not consistently make graph construction easier. More detailed prose can increase useful coverage while creating more binding and metadata problems. Intentional scope exclusions and ambiguous pooled compound-to-literature associations are outside strict wrong-link counts.

A separate test-harness defect affected five current-Luna items in P31: a mistyped echoed DOI prevented conversion. Production already takes identity from the trusted task. An isolated production-equivalent replay restores all five unchanged findings; the original comparison is preserved, the defect is not counted as five scientific errors, and future evaluations now follow production identity handling. Source-content mismatch warnings still fail closed. The identity/runner suite passes 49 tests and 2 subtests. [P31 replay](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_refinement_20261018/postvalidation_normalization/p31_trusted_identity/summary.json>)

## Saved Gemini context

No new Gemini requests were made. Earlier source judgments on the same papers remain useful historical context:

| Historical source set | Saved Gemini material-error items / papers | Previously audited wrong canonical records | Provenance |
| --- | --- | --- | --- |
| Controlled 40 | 18 / 12 | 3 | Verified same input, original prompt and schema in prior model comparison. |
| Previous fresh 48 | 7 / 4 | 17 | Historical prompt/schema differ; original full-text equality unverified. |
| Existing matched 85 / 167 domain tasks | 29 / 17 | 18 after earlier repairs; 24 as published | Archive from Gemini era; per-call provider/prompt/input unverified. |

These graph counts use the **previous round's normalizer and judgments**, not the new graph table above; do not subtract them to estimate a new model advantage. For raw extraction, the controlled 40 new runs show 8 current-Luna errors in 4 papers and 7 candidate errors in 3 papers, versus the historical 18 Gemini errors in 12 papers. These older Gemini judgments were not regraded blind in this round. They provide historical context, not a new controlled estimate of model advantage; one generation per prompt also does not give a stable error rate. Missing archived papers are never counted as correct empty answers.

For the new 64 papers, same-domain Gemini-era outputs exist for 49; only 14 have verified identical source content, original prompt identity is not verified, and there are **zero clean model-only pairs**. Their availability is documented; no new accuracy score is invented from those records. [Saved Gemini availability](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_refinement_20261018/fresh/archived_gemini_availability.md>) · [Previous complete Gemini comparison](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/primary_extraction_improvement_2026-10-17.md>).

## What changed in the instructions, and what this round adds

The candidate retains all ten schemas and existing domain routes. It asks Luna to define the actual observation before filling fields; bind numbers to their table row, outcome and comparison; preserve central nulls and restrictions; keep single compounds, mixtures and roles explicit; choose truthful controlled categories; and abstain on damaged or missing values. It was built from 126 previously documented failure items across 41 papers, not written before examining the failure modes. [Design evidence](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_refinement_20261018/prompt_design_evidence.md>) · [Exact tested candidate](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/extraction_profiles/candidates/primary_instruction_refinement_v3.md>).

The previous round showed that longer instructions and extra schema fields could increase completeness while adding errors. This round removes the schema expansion, regenerates both arms, masks prompt identities during review, checks every item and its actual graph fate, and tests a disjoint 64-paper sample. **It shows that the same-schema rewrite still fails to generalize convincingly.** Familiar-set gains alone would have led to the wrong promotion decision. The evidence supports retaining the architecture and current prompt, improving deterministic handling, and targeting table/contrast validation rather than adding another broad layer of instructions.

## How correctness was established

Codex reviewers checked the exact supplied paper text and metadata, not prior Gemini decisions. Fresh central references were prepared before generation; reviewers saw randomly relabeled X/Y outputs. Judgments for all 248 papers were saved and hashed before the lead reviewer opened arm keys. Every output item has a source assessment and graph assessment. All six fresh material-error cases received independent source rechecks. These are **model-based source judgments, not human expert gold labels**; reviewers knew the hypothesis and could recognize familiar papers.

The new sample has 32 abstracts, 32 article packets, 32 ordinary and 32 challenging papers, crossed evenly, with 6–7 papers per domain. Selection used source complexity and availability, excluding 1,677 prior identity keys. It is not a representative corpus sample. One existing assigned domain is assessed per new paper, so this does not measure routing recall or every finding in the full paper. Sources with damaged tables, unknown figures or unresolved scope remain explicitly uncertain. One generation per arm leaves sampling variability unmeasured.

Reference corrections were applied equally before unmasking:13 redundant old groups were removed prospectively, plus documented scope/provenance corrections during source review. Final denominators are 317/84/165/151, so the older report's 336/84/168 denominators are not directly interchangeable. The candidate was not edited after outputs were inspected.

All 720 calls returned schema-valid JSON without logged transport retries, at **$0.9881 total token-based API cost**. This is usage-based estimated billing, not an invoice. The candidate cost 13.1% more on the fresh set. There were no production extraction or publication runs.

## Reproducible results

- [Existing audit (96)](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/primary_refinement_cases_2026-10-18/existing.md>)
- [Controlled historical set (40)](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/primary_refinement_cases_2026-10-18/controlled_historical.md>)
- [Previous fresh set (48)](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/primary_refinement_cases_2026-10-18/previous_fresh.md>)
- [New unseen set (64)](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/primary_refinement_cases_2026-10-18/fresh.md>)

[Protocol](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_refinement_20261018/evaluation_protocol.md>) · [Frozen review hashes](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_refinement_20261018/masked_review_freeze.json>) · [Complete scientific totals](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_refinement_20261018/scientific_summary.json>) · [Review completeness checks](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_refinement_20261018/review_integrity.json>) · [Request/cost checks](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_refinement_20261018/execution_validation.json>)

[Versioned checkpoint: screening status, scientific judgments, references and verification](primary_refinement_2026-10-18/README.md).
