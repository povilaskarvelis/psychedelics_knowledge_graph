# Postvalidation normalization repairs — 18 October 2026

This is a separate deterministic repair stage performed **after** the frozen prompt comparison. No additional model requests were made. The original prompts, schemas, extraction outputs, comparison graphs and source judgments were preserved. The results below must not be presented as the original unseen-set validation result.

The replay covered **20 saved model/prompt arms, 1,889 task instances and 5,379 extracted-item instances**. It includes the eight newly paired arms, the previous Luna arms, saved controlled/previous-fresh Gemini outputs, and the archival graph replay. These are repeated item instances across arms, not 5,379 independent papers. Archival replay includes 193 historical tasks, not only the 167 tasks in the matched-model comparison; use the exact matched key set for a model comparison.

**334 item projections changed.** All frozen-before projections reproduced the saved comparison, and every raw extracted item remained identical. No item that previously had a retained finding disappeared into audit-only storage.

| Result of repair | Item instances |
|---|---:|
| Remain main graph, with changed identity/endpoint/metadata | 200 |
| Remain paper detail, with changed label/metadata/reason | 51 |
| Move from main graph to paper detail | 54 |
| Recovered from audit-only to paper detail | 27 |
| Move from paper detail to main graph | 2 |

These are change counts, **not 334 scientifically incorrect items corrected**. In particular, analytical-method evidence can be correct while inappropriate for an in-vivo exposure link; some compound-package restrictions also reduce valid atomic-drug visibility. The admission tradeoffs are listed below.

## What changed

| Family | Representative consequence |
|---|---|
| Specific chemical identity versus class or parent compound | Named ketamine and 25C-NBOMe take precedence over their descriptive classes. BAB benzyl derivatives retain their distinct identity as paper detail instead of becoming bufotenin/5-MeO-DMT. BOL's expanded parent-name description does not add an independent LSD link. Salvinorin acid derivatives do not inherit the parent drug. |
| Product descriptions and source-local identifiers | A complete blotter-product claim cannot become a canonical atomic compound through class recovery. Bare numbered compounds with explicit chemical provenance survive as study-local detail, without creating global drug identities. |
| Single drug versus combination metadata | Expanded chemical names and dose descriptions do not by themselves create combination records. Genuine mixtures remain separate. Sequential hair segments do not imply sequential drug administration. |
| Study design | Explicit randomized trial prose resolves generic clinical-trial/dose-finding categories. An open-label or generic clinical-trial label alone no longer proves nonrandom allocation. |
| Follow-up and comparator metadata | Baseline-plus-follow-up observations keep the later observation window; unspecified timing does not become acute merely because improvement is described as rapid. Saline stays inactive placebo, escitalopram remains an active treatment comparator, and a prior post-treatment score is not another active treatment arm. |
| Endpoint identity | Plain methamphetamine use does not become a diagnosed use disorder. Diarrhea or nonspecific GI discomfort does not become nausea. Sucrose preference does not become drug self-administration. Explicit locomotor constructs retain the controlled locomotor detail label. |
| Observation role | Explicit unobserved interview concerns, analytical-method validation, and named rescue/continuation packages retain their scientific content without acquiring unsupported atomic-event/exposure projections. Actual dose–experience associations in mixed validation records remain graphable. |
| Molecular specificity | IL-10/IL-17 numeric boundaries cannot match IL-1. This is covered by positive and negative regression fixtures; no corpus prevalence or measured sample gain is claimed for this rule. |

Changed-field counts overlap: 120 study-design instances, 57 follow-up instances, 11 comparator instances, 73 subject-kind instances, 31 endpoint/detail-label instances, and 49 overview-subject/admission representations. Detailed item lineage and the raw input for each change are in [change_review.json](change_review.json).

## Verified examples and tradeoffs

- **N20:** all three paired BAB records retain the novel chemical in paper detail, with no bufotenin or 5-MeO-DMT overview. This removes a false parent-drug identity.
- **N28:** both paired noribogaine safety records retain the explicitly randomized, double-blind, placebo-controlled design.
- **P82:** all four paired focal ketamine observations use atomic Ketamine, rather than the NMDA-antagonist class. The separate apomorphine control items are not relabeled ketamine.
- **P93:** sequential hair segments no longer create a treatment regimen. Analytical-process stability is distinguished from a person's measured hair exposure.
- **P94:** raw methamphetamine use is retained without inventing a use-disorder diagnosis. If an extraction itself already falsely says “use disorder,” normalization does not silently undo that source error.
- **P73:** bare numeric chemical identifiers with explicit compound provenance are restored to paper detail. This improves retention; it does not certify their extracted affinity values or repair source-text corruption.
- **P76:** all three archived harm-reduction intervention details are retained. This is a regression control for parenthetical punctuation, not a newly recovered scientific result.
- **P23:** explicit hyperactivity maps to the correct Locomotor activity detail label. Locomotion remains outside the main graph under the existing policy, so this is not a main-link recovery.
- **P90:** rescue-agent packages retain the complete induction/rescue text as detail. Some items also contain valid ketamine-induction findings that now lose an atomic overview link. This is a conservative visibility tradeoff, not an unqualified correction of all previous links.
- Generic open-label trial descriptions now receive an unknown allocation bucket when the extraction does not state allocation. This avoids an unsupported claim, but does not establish that each source study was randomized.
- Pure analytical validation is retained as detail. Detection limits, assay calibration and storage stability are valid methods results; they are not made factually incorrect by this admission decision. Genuine detected/concentration observations and mixed dose-association controls remain represented.

## Verification and limits

**322 tests and 305 subtests passed**, including 54 new focused postvalidation tests. The full saved-output replay passed input identity and frozen-before equivalence checks. **39 targeted saved-output checkpoints** passed. The before loader explicitly binds frozen PK, converter, clinical-comparator, follow-up and export helpers, preventing accidental use of repaired code in the comparator.

The durable outputs are [verification.json](verification.json), [checkpoint_verification.json](checkpoint_verification.json), the complete `replay/` lineage and public payloads, and exact dependency snapshots under `before/` and `after/`. Replay and verification scripts are in the parent `scripts/` directory. Original review judgments remain the source of scientific adjudication; the automated change classification is not a new full paper audit.

Remaining limitations include mixed-compound exposure-history attribution, circuit/result binding, ambiguous broad molecular categories, malformed raw source roles and missing scientific observations. Complex dose/comparator strings in P12/P48 can still receive combination metadata despite a correct atomic overview. H24's refined clinical items1/2 still inherit later study-schedule timing even though their reported result concerns an earlier observation: replacing the old incorrect Baseline label does not make that result-specific time correct. These repairs do not establish that every remaining canonical link is correct. No production graph was published, no full extraction rerun was started by this stage, and the production extraction prompt/schema was not changed.

The independent [controlled-history peer review](peer_review_controlled_historical.json) checked all18 changes across7papers and23 unchanged controls. It found no confirmed new wrong relationship or lost valid relationship, while retaining the H24 timing ambiguity and conservative allocation-precision tradeoffs. The fresh peer review is recorded separately when complete.

## Separate evaluation-envelope correction

The P31 result echoed an incorrect DOI and therefore lost five scientifically supported safety items before normalization. Production already assigns DOI and route identity from the trusted task; the evaluation runner had omitted that step. Future evaluation runs now use production identity assignment, preserve experimental schema versions and raw response text, and log every changed echoed field. Existing saved outputs are untouched. Explicit source-content mismatch warnings still fail closed; the warning checker now also recognizes the grammatical plural “do not match.” **42 related transport/runner tests passed.**

The isolated [P31 trusted-envelope replay](p31_trusted_identity/summary.json) recovers **5 converted rows,5 main findings and5 public records**, with all extracted items unchanged. [Source and projection review](p31_trusted_identity/scientific_projection_review.json) confirms the recovered body-temperature and neurotoxicity results, retaining the coarse quinidine-modifier attribution limitation. This is an experimental transport artifact and a production-equivalence check, excluded from the original prompt-comparison score and from the 334 normalization-change count. No API request was required.
