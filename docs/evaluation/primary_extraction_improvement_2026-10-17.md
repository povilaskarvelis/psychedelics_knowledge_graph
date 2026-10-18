# Primary extraction repairs and comparison results

Experiment dated 17 October 2026; review completed 18 October 2026.

**The tested normalization repairs work on saved outputs. Revised Luna instructions improve completeness, but introduce some material errors on fresh papers. The expanded schema adds further mistakes and should not be promoted.** Keep Luna, retain the verified repairs, and resolve the specific observation-binding and graph-meaning failures before the full extraction rerun. Neither candidate meets the predeclared requirement to improve coverage without a material error increase on fresh data.

This experiment covers **184 distinct papers across three disjoint cohorts**, **640 successful new Luna calls**, and **3,359 extracted items across cached and new outputs**. No new Gemini calls were made. The production extraction prompt and graph publication have not been switched to the candidate.

## Changes tested separately

| Test | What changed | What stayed fixed |
|---|---|---|
| Normalization repairs | Entity matching, scientific category/system precedence, observation identity, field transport and browser/API consistency | All saved extraction outputs |
| Luna revised instructions | Shared instructions for central/null findings, source attribution, comparisons, experimental preparation and scientific roles | Existing domain schemas and domain routing |
| Luna revised instructions plus schema | Same revised instructions plus eight explicit observation fields, and comparator where absent | The same source and fixed normalizer |

The eight fields describe observation role, exposure role, comparison basis, measurement type, analysis unit, result pattern, value status and value locator. They are preserved through transport but **do not yet drive semantic normalization**. This test measures whether Luna supplies them reliably and whether the schema changes its extraction; it does not test a future normalizer that consumes those roles.

## Normalization results on saved extractions

The frozen before-version reproduces all 467 saved findings exactly. Replaying the same 96 papers and 565 raw items isolates these code changes from model variation.

| Measure | Before | After |
|---|---:|---:|
| Raw items represented in a finding | 441 | 454 |
| Findings admitted to main graph | 389 | 407 |
| Findings retained as paper detail | 78 | 83 |
| False combination rejections in the tested cases | 17 | 0 |
| Excess duplicate finding identities | 5 | 0 |
| Missing primary-study subject links in query API | 25 | 0 |

Of the **13 newly represented items, 11 restore source-supported identities across nine papers**. One is an out-of-scope control retained as detail, and one exposes an existing unsupported extraction claim. Identity restoration does not validate every scientific property: docking specificity and intervention-package interpretation still need care. No previously represented item loses all findings.

Field transport now retains 145 dose values, 37 timing values and 24 design aliases previously lost across 188 converted rows. Browser detail also retains relevant tissue, values, units and timing. The final selected regression suite passes **200 tests and 305 subtests**, and all 12 experiment replays match the frozen code hashes. These checks verify the specified repairs, not every possible wording or scientific inference. [Repair verification](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/normalization_verified.json>) · [Scientific review of changes](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/builder_verification/scientific_change_adjudication.md>) · [Final regression verification](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/normalization_final_verification.json>)

## Fresh validation is the deciding result

The fresh set contains 48 papers: 24 ordinary and 24 challenging, half abstracts and half article packets, across ten domains. Selection used source characteristics, not the new outputs. There are 168 eligible central finding/qualification groups across 36 papers; the other papers are scope controls or unresolved eligibility cases.

| Fresh 48 papers | Current Luna | Revised instructions | Revised instructions plus schema |
|---|---:|---:|---:|
| Central groups fully covered | 113/168 (67.3%) | 134/168 (79.8%) | 135/168 (80.4%) |
| Central groups partially covered | 22 | 20 | 18 |
| Central groups entirely missing | 33 | 14 | 15 |
| Items with material errors in existing fields | 0 | 5 in 2 papers | 8 in 3 papers |
| Items with material errors in new fields | — | — | 21 in 8 papers |
| Unique items with either type of material error | 0 | 5 in 2 papers | 28 in 10 papers |
| Separate scope-error items | 1 | 0 | 2 |

Revised instructions increase full coverage by **12.5 percentage points** and reduce completely missing central groups by **58%**. They improve coverage in 13 eligible papers, worsen it in five and tie in 18. These are grouped findings, not atomic-claim recall or an estimate of corpus-wide accuracy. More extracted items are not automatically better; multiple errors in the same item count once.

| Fresh stratum | Current fully covered | Revised instructions | Revised instructions plus schema |
|---|---:|---:|---:|
| Ordinary papers | 48/62 (77.4%) | 51/62 (82.3%) | 51/62 (82.3%) |
| Challenging papers | 65/106 (61.3%) | 83/106 (78.3%) | 84/106 (79.2%) |
| Abstracts | 33/41 (80.5%) | 37/41 (90.2%) | 36/41 (87.8%) |
| Article packets | 80/127 (63.0%) | 97/127 (76.4%) | 99/127 (78.0%) |

All five material instruction-only errors occur in challenging papers. The larger schema produces material errors in both strata. The gains extend beyond the previously inspected sample, but the regressions do too.

## Results on the previously audited 96 papers

| Existing 96 papers | Current Luna | Revised instructions | Revised instructions plus schema |
|---|---:|---:|---:|
| Central groups fully covered | 266/336 (79.2%) | 301/336 (89.6%) | 288/336 (85.7%) |
| Completely missing groups | 31 | 14 | 21 |
| Items with material errors in shared fields | 31 in 15 papers | 42 in 14 papers | 27 in 15 papers |
| Material errors including new fields | 31 in 15 papers | 42 in 14 papers | 45 in 21 papers |
| Wrong canonical graph links/admissions | 10 | 14 | 21 |
| Main records with shared-field or graph errors | 40 | 65 | 60 |

The increase to 42 affected items is partly one repeated mistake: revised instructions label all 15 rhesus-monkey findings in one paper as a mouse model, while the prose identifies monkeys correctly. Reporting only an item total would overstate the number of independent failures; reporting only papers would hide how many graph records are affected. These are development results: the earlier calibrated baseline judgments are reused and coverage groups were harmonized after inspection.

## Same-paper Gemini comparison

The **40-paper controlled comparison** is the clean model comparison: saved Gemini and current Luna outputs use verified identical source, prompt and schema. Each revised Luna arm then uses the same source. Half are abstracts, half articles, with four tasks per domain.

| Controlled 40 papers | Saved Gemini | Current Luna | Revised instructions | Revised instructions plus schema |
|---|---:|---:|---:|---:|
| Central groups fully covered | 51/84 (60.7%) | 66/84 (78.6%) | 81/84 (96.4%) | 75/84 (89.3%) |
| Material error items in shared fields | 18 in 12 papers | 1 in 1 paper | 2 in 2 papers | 0 |
| Material error items including new fields | 18 in 12 papers | 1 in 1 paper | 2 in 2 papers | 8 in 3 papers |
| Wrong canonical graph links or primary-evidence admission | 3 | 8 | 10 | 10 |
| Main records with shared-field or graph errors | 19 | 10 | 12 | 11 |
| Main records including transported new-field errors | 19 | 10 | 12 | 15 |

**Luna clearly wins on source extraction in this controlled sample. It does not win every graph metric.** The fixed normalizer makes fewer wrong canonical links from these Gemini outputs, but more Gemini records carry incorrect extracted values or context. This distinction is why model selection and graph correctness need separate tests.

For the fresh 48 papers, saved June Gemini outputs contain **seven material error items in four papers**, plus nine scope-error items. Replaying them through the same fixed normalizer produces **17 wrong canonical links/admissions** and **24 main records carrying a confirmed material error**. This is useful history, not a controlled model comparison: the old prompt/schema differs and original full-text packet equality cannot be verified. Full-text omission differences are therefore not attributed to Gemini capability.

For the existing 96, archived pipeline outputs are available on **85 papers and 167 matching domain tasks, containing 491 items**. They contain **29 material error items in 17 papers**, plus 11 scope-error items. The 11 unavailable papers are not counted as correct empty results. Per-call provider, prompt and input identity are unverified, so these are labelled pipeline outputs from the Gemini era. The casebook includes the saved outputs, actual published graph and corrected replay for those same papers; extra historical domains are excluded from comparative totals.

| Same 85 papers and 167 domain tasks | Historical archive | Current Luna | Revised instructions | Revised instructions plus schema |
|---|---:|---:|---:|---:|
| Material error items in shared fields | 29 | 28 | 41 | 27 |
| Material error items including new fields | 29 | 28 | 41 | 45 |
| Wrong canonical links using fixed normalizer | 18 | 9 | 13 | 20 |
| Main records with shared-field or graph errors | 54 | 38 | 64 | 59 |

The historical column uses the same repaired normalizer as Luna. On those identical archived outputs, normalization alone reduces wrong canonical records from **24 published to 18 in replay**, and records with shared-field/graph errors from **64 to 54**. Historical output provenance prevents attributing the whole archive-versus-Luna difference to the model. [Exact matched comparison](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/matched_archive_comparison.json>) · [Matched graph comparison](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/matched_archive_graph_comparison.json>)

## Extraction correctness and graph correctness diverge

All Luna arms below use the same corrected normalizer. Wrong canonical links/admissions concern subject, object, relation or primary-evidence status. The broader record-error count also includes incorrect scientific metadata or extracted fields carried into an admitted record; it is **not** a count of false edges alone. The structured arm includes errors in new fields retained as detail even though those fields do not drive graph decisions.

| Fresh graph assessment | Current Luna | Revised instructions | Revised instructions plus schema |
|---|---:|---:|---:|
| Total main graph finding records | 99 | 104 | 105 |
| Wrong canonical links/admissions | 5 | 5 | 10 |
| Main records with shared-field or graph errors | 9 | 10 | 18 |
| Main records including transported new-field errors | 9 | 10 | 31 |

Record granularity differs, so these counts are not precision percentages. Intentional paper-detail retention, unresolved scope and vocabulary gaps are not automatically wrong inclusion.

## Concrete improvements and regressions

| Example | What the new tests reveal |
|---|---|
| Conditioned-place-preference study, F29 | Revised instructions recover 14 central contrasts versus seven with current instructions. This is the intended completeness gain. |
| MDMA and oxytocin, F15 | Revised instructions correctly discuss increased oxytocin in prose but label one observation as changed MDMA parent-drug exposure. This is a wrong analyte/relation, not an invented numeric concentration. |
| Ketamine followed by riluzole trial, F36 | Four instruction-only observations inherit randomized-trial design from the later riluzole phase; the ketamine comparison was open-label before/after. The means are not the error. |
| Protein/proteomics abstract, F10 | The schema arm assigns the day-14 behavioral-testing time to six molecular results whose measurement time is not reported. |
| Clinical dissociation report, F44 | The schema arm attaches a PTSD population of 20 to a TRD dissociation row. Its prose acknowledges uncertainty about the 78% rate; the counted error is the population field. |
| Lithium/placebo after ketamine, F45 | The schema arm turns descriptive headache counts into a claimed null result without a reported headache-specific comparison. Separately, all Luna arms can become ketamine-only graph links despite the continuation-treatment comparison. |
| Crossover experiments | The new comparison enum lacks an explicit within-person condition contrast. Several correct crossover narratives are labelled between-groups. More mandatory labels created false specificity. |
| Psychotic-symptom questionnaire, F47 | A scale score becomes a Psychosis risk safety node. The source can be correctly extracted while the graph adds a stronger clinical interpretation. |

The previous audit identified these failure families. **This round establishes which attempted repairs actually help, which regress on unseen papers, and where normalization remains wrong despite better extraction.** Merely adding explicit fields did not reliably eliminate inference: fields can contradict correct prose, and a consumer that ignores roles still misrepresents the observation.

## Decision and next technical priorities

Retain the verified deterministic repairs. Keep the instruction-only candidate as the more promising basis for refinement, but do not replace production extraction with it yet. Do not promote the eight-field schema as tested: it offers almost no fresh coverage gain beyond revised instructions and adds material errors and cost.

Prioritize a smaller, explicit observation binding: the actual exposure/comparison, measured outcome, experimental population/preparation, timing and source analysis. Any controlled field needs a valid abstention choice and faithful categories, including crossover contrasts. Then make graph admission respect those bindings: distinguish measured experience from diagnosed harm, focal intervention from background treatment, and a chemical analogue from its parent. Remaining examples include ETH-LAD/MLD-41 inheriting LSD and racemic ketamine inheriting R-ketamine. These require additional mapping work; the verified repair suite is not a claim that all normalization is solved.

The evidence supports focused contract and normalization changes rather than replacing the ten-domain routing architecture. Existing routing omissions remain outside this prompt-only experiment: an uncalled domain cannot be repaired inside another domain's extraction prompt.

## Evaluation quality and cost

Reviewers checked the supplied source rather than treating Gemini output or previous inclusion decisions as truth. Fresh central references were frozen before generation. All generated items were examined for support, numerical binding, population, comparison, timing, roles, typed-field consistency and scope, followed by actual graph lineage. Material disputes, source corruption and unresolved eligibility were kept separate. Three consequential fresh judgments received an independent second Codex review. Item-level review entries are complete for the existing 96 and their matched archive. For 36 fresh/controlled papers reviewed by the lead reviewer, the ledger records paper-arm summaries and exact error indices rather than a separate assessment entry for every correct item; counts and raw-output identities were validated.

These are **unblinded Codex judgments, not independent human gold-standard labels**. Source packets limit what can be established; abstracts were assessed as abstracts. There is one generation per arm, cached development baselines are reused, and the fresh pool is drawn from available historical pilot papers. Ordinary/challenging balance broadens the test but does not make it a representative corpus sample. Error counts include unsupported specificity as well as directly contradicted facts.

All 640 new results pass their JSON schemas; the scientific errors demonstrate why that is insufficient. Successful requests have **$1.016 in logged token-based cost**. Twenty-eight timed-out attempts have unknown billing, with a reserved allowance of $0.369; these are estimates, not an invoice. On the same fresh tasks, revised instructions cost **14.4% more** than baseline and the schema arm **27.6% more**. Neither cost increase includes a separate semantic normalization model.

## Evidence and paper-level results

- [Existing 96 papers including matching archive and graph mistakes](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/primary_improvement_cases_2026-10-17/existing.md>)
- [Controlled 40-paper Gemini and Luna comparison](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/primary_improvement_cases_2026-10-17/controlled_historical.md>)
- [Fresh 48-paper validation and June Gemini history](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/primary_improvement_cases_2026-10-17/fresh.md>)
- [Frozen evaluation protocol](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/evaluation_protocol.md>) · [Candidate instructions](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/extraction_profiles/candidates/primary_observation_v2.md>)
- [Scientific results](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/results_scientific.json>) · [Graph results](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/results_graph.json>) · [Paired and stratified results](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/paired_and_stratified_results.json>)
- [Detailed scientific judgments](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/all_scientific_reviews.json>) · [Detailed graph judgments and finding IDs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/all_graph_reviews.json>)
- [Request and cost verification](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/execution_validation.json>) · [Independent judgment checks](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/reviews/independent_spotcheck.json>)

[Review integrity checks](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/scientific_review_integrity_validation.json>)
