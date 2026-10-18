# Luna extraction comparisons and normalization tests

17 October 2026. **Full extraction rerun: not started. No production extraction prompt or schema was promoted.**

**Follow-up:** the [deeper primary-study source audit](luna_primary_source_audit_2026-10-17.md) now checks 150 baseline items against 24 papers and traces their graph representation. It establishes specific extraction, source-conversion and normalization problems. Retaining the baseline below is a decision between tested candidates, not a finding that the baseline is ready for an unrestricted rerun.

**Recommendation: retain the present family/domain architecture and existing extraction prompts. Keep the narrow statistical-check and circuit-vocabulary fixes.** The source-first primary candidate is promising, but its small fresh-set gain does not clear the predeclared attribution gate. The broader review projection should remain disabled.

## Fresh validation: the main result

The selected candidates were frozen before fresh predictions. The final assessment includes findings **and** paper-level frame, overview, assessment and conclusion fields.

| Measure | Existing primary prompt | Source-first primary candidate |
|---|---:|---:|
| Fresh primary papers | 48 | 48 |
| Fully captured reference facts | 214/259 (82.6%) | 218/259 (84.2%) |
| Coverage giving half credit for partial capture | 86.5% | 88.0% |
| Papers with retained material flags after Codex review | 10/48 | 9/48 |
| Extraction calls | 112 | 112 |
| Estimated standard API cost for these calls | $0.1464 | $0.1546 |

The gain is **1.5 percentage points** in fully captured facts, with a paper-clustered bootstrap interval of **−4.4 to +7.2 points**. This is a small favorable point estimate, not established superiority. Cost rose **5.6%**. Eleven papers gained fully captured facts and eight lost them.

A concrete new defect prevents promotion under the frozen rule: in [the qualitative integration-group study](https://doi.org/10.1556/2054.2024.00381), the candidate describes the community/peer group accurately in prose but sets `real_world_use_context` to **Clinical care** in two items. This changes the structured interpretation of care context. Unsupported statistical-significance wording also remains in another fresh case. Better average coverage does not eliminate these attribution problems.

For **eight fresh guideline papers**, weighted coverage changed **54.5% → 53.6%**; fully captured facts changed **25/55 → 24/55**. Neither arm had a retained material flag. The small development gain did not repeat, so retain the baseline guideline prompt.

## Development comparisons

All paired arms received the same paper text, task domains, model and reasoning setting. Except for the named schema/architecture experiment, only the instructions changed. Scores below give full credit for complete capture and half credit for partial capture.

| Candidate | Papers | Existing → candidate coverage | Change |
|---|---:|---:|---:|
| Primary: general clarification | 48 | 82.6% → 84.3% | +1.7 pp |
| Primary: source-first contract | 48 | 81.4% → 85.3% | +3.9 pp |
| Primary: one call per paper (exploratory) | 48 | 84.6% → 80.6% | -3.9 pp |
| Reviews: clarification | 20 | 80.5% → 81.8% | +1.4 pp |
| Meta-analysis: clarification | 20 | 88.2% → 77.2% | -11.0 pp |
| Meta-analysis: clarification + scalar/summary schema | 20 | 85.8% → 76.8% | -9.1 pp |
| Guidelines: clarification | 8 | 76.1% → 77.3% | +1.1 pp |

The primary paper-centered wrapper also included the bibliographic abstract alongside the canonical article source; the per-domain baseline omits that duplicate metadata field for article inputs. Its information context was therefore not perfectly identical. Treat that arm as an exploratory implementation comparison, not a pure estimate of the effect of call consolidation. The scalar/summary schema arm builds on the clarification arm; its baseline comparison measures that combined candidate, not the isolated causal effect of the schema constraint.

The source-first primary contract reorganizes eligibility, original-result selection, statistic-to-analysis attribution, source ambiguity and cross-field consistency checks while retaining the scientific domain schemas. The general clarification arm adds family-specific instructions to the existing contract. The meta schema arm adds scalar-estimate constraints and a distinct reported-summary representation. The architecture arm returns the existing primary domain schemas together in one call.

Reading each primary paper once reduced development calls **96 → 48**, but saved only **16.8%** of API cost and reduced reference coverage. This does not justify replacing the current domain calls. The meta changes fixed known packing/range/network cases in the separate four-paper diagnostic test, but lost coverage on fresh development papers; diagnostic success did not generalize sufficiently to promote them. Reviews showed a small, uncertain change with no clear decision advantage.

The unchanged-baseline repeat used **26 tasks from 18 complete papers**. It showed ordinary output and grading variation. Identical baseline outputs also received somewhat different scores in different anonymous pairings. Small changes should therefore be interpreted cautiously; each row uses its own paired baseline, rather than mixing scores across comparisons.

## Normalization: tested independently on identical saved outputs

No new extraction calls were needed for these comparisons. Each replay used isolated graph tables and retained the original source item and proposition.

| Repair | Historical diagnostic replay | Fresh development | Fresh validation | Decision |
|---|---|---|---|---|
| Distinguish I² percentages from multiple treatment estimates | Recovers one valid pooled-effect finding | No added/removed findings | No added/removed findings | Keep narrow fix |
| Give VTA→BLA dopamine circuit its own identity | Recovers one previously unmapped circuit finding | No added/removed findings | No added/removed findings | Keep exact vocabulary entry |
| Project additional named review objects | 31 additional unique projections; at least 5 rejected and 6 needing further mapping/scope review | Not promoted | Not promoted | Keep disabled |

Together the two safe repairs changed historical normalized findings **421 → 423**, with no removed findings. On the full fresh baseline outputs, counts remained **377 → 377** in development and **374 → 374** in validation. The provisional fresh candidate mix also remained **399 → 399**. These neutral fresh results establish no observed regression in those cohorts; they do **not** establish a general coverage gain, because those cohorts did not trigger the two repaired cases.

The statistical repair retains genuine multi-estimate blocks. The circuit entry stays distinct from the VTA, BLA and other circuits. The broader review experiment exposed existing mappings such as **self-acceptance → psychological insight**, **generic cognitive function → executive function**, and **hallucinations → psychosis risk**. Adding endpoints before fixing those distinctions would expand questionable graph relations. More normalized rows are not a correctness measure.

## What was tested, and how correctness was assessed

- **191 distinct papers:** 96 development and 95 held out, with 303 original domain tasks. Each cohort includes primary studies, reviews, meta-analyses and guidelines, and both article-text and abstract inputs. One apparent holdout paper was excluded before predictions because its different DOI identified the same report as a development paper.
- All development candidates were compared. Fresh paired prompt validation covers **48 primary and 8 guideline papers**. The remaining **39 fresh review/meta-analysis papers** were extracted with baseline contracts for normalization/operational validation; rejected review/meta prompt candidates were not retested there.
- **Luna only**, low reasoning. Exact source bytes, instructions, schemas, raw responses, usage and selection decisions are saved. No Gemini calls or production extraction run occurred.
- Reference inventories were drafted from source text before candidate extraction. Codex checked source spans and scope, corrected references, and reviewed a separate source-only scope audit. **Reference errata after development inspection are logged and applied equally to arms.** The final effective inventories were frozen before held-out extraction.
- Anonymous paired Luna grading assessed source support and reference coverage. Codex reviewed material flags, rejected false allegations, recorded ambiguity, and directly checked abstention controls and additional source defects. Counts of retained flags are **lower bounds from this assessment**, not exhaustive wrong-paper rates or measured claim precision.
- This is **AI-assisted assessment, not independent human gold**. Neither old screening decisions nor model agreement defined truth. The intentionally stratified samples do not support an unweighted corpus-wide accuracy estimate.

Two evaluation defects were corrected before final scoring: the test harness initially removed a genuine schema property named `description`, and the initial grading view omitted paper-level context. Affected meta extractions were rerun; every final paired assessment was rerun with the complete scientific output. Initial results remain archived and are excluded from the tables above. Prompt and source changes were not made from held-out results. The grading correction occurred after extraction, so this is a controlled extraction holdout with a documented assessment correction, rather than a wholly preregistered benchmark.

## What this adds to earlier testing

The earlier [design audit](luna_extraction_design_audit_2026-10-17.md) replayed 120 saved Luna outputs and identified failure mechanisms; it made no new calls. Earlier July review tests and October model comparisons informed the existing design but did not establish these fresh prompt/schema/architecture outcomes.

**New this round:** controlled Luna extraction trials across all four families; a separate primary architecture comparison; source-first references and logged corrections; a complete-paper repeat subset; prospective candidate selection before fresh extraction; independent normalization ablations; and a fresh test showing that the guideline gain disappeared and the primary gain was modest. This supports targeted downstream repairs and caution about broad prompt or schema replacement.

## Cost, verification and remaining work

**Estimated API spend: $3.80 of the $5 cap**, including reference drafts, scope audit, grading, diagnostic calls, repeats, invalidated preliminary calls and corrective reruns. All local reservations are settled. These are token-metered estimates using the pipeline pricing table, not an invoice. Final selected extraction arms had no schema-validation failures. **81 relevant regression tests passed**, including schema-property preservation, complete-context grading, real multi-estimate negative controls, and review-package preservation. No production graph was rebuilt or published.

The full rerun remains on hold. The next useful work is a primary-output consistency/admission check for unsupported study-design, analysis-denominator, care-context and domain assignments, plus repair of the specific unsafe normalization aliases. Those are more directly supported by these results than another broad schema redesign. The existing hard-coded significance-threshold concern remains unresolved; it was not part of the two validated normalization fixes.

Reproducible artifacts: [experiment directory](../../data/processed/evaluation/luna_extraction_comparison_20261017/), [final decision](../../data/processed/evaluation/luna_extraction_comparison_20261017/final_decision.json), [reference errata](../../data/processed/evaluation/luna_extraction_comparison_20261017/reference_errata.json), and per-comparison `summary.json`, `codex_review.json` and `reviewed_scores.json` files. The production state remains `extraction_status: tasks_prepared`.
