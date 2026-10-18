# Luna evidence extraction design audit and evaluation plan

17 October 2026

**Keep the separate primary, review, meta-analysis and recommendation workflows. Test targeted changes to result structure and normalization before deciding whether primary studies should be extracted once per paper.** The initial audit identifies problems at several stages; revising extraction instructions alone would leave some of them intact.

This investigation used the repository, earlier evaluation records, source text and saved Luna outputs. It made **zero new model calls**, changed no production prompts or schemas, and left the completed screening and published graph intact. The intended standard is a research knowledge graph with traceable evidence and controlled promotion, rather than a validated systematic review.

## Current design

| Family | Active approach | Reason to retain it initially |
|---|---|---|
| Primary studies | Shared primary prompt for each text depth, domain scope addendum, domain schema; one task per selected domain | Separates original measured results and domain-specific detail. The common instructions are already shared. |
| Reviews | One paper-centered call; relationships, anchors, paper frame and importance; domains assigned within the answer | Preserves the review's purpose and qualifications across domains. |
| Meta-analyses | One paper-centered call; questions, synthesis results, assessments and conclusions | Quantitative synthesis needs comparisons, estimates, uncertainty and evidence counts. |
| Guidelines and consensus | Dedicated recommendation contract | Recommendations should retain normative status and strength rather than become empirical treatment effects. |

The new screening cohort produced **30,720 primary tasks for 16,375 primary papers**, plus 31 guideline tasks for 31 papers. A hypothetical single call per primary paper would reduce primary call count by **46.7%**. That is a call-count calculation, not a prediction of token savings or improved quality: combining domains may increase response size, omissions or truncation. It justifies a controlled architectural experiment.

Some older overview documents still describe secondary domain schemas or guidelines as disabled. The active runners and dedicated v2 contracts establish the current architecture. Experiments must freeze the actual assembled instructions, schema and source, rather than rely on those older descriptions.

## What earlier testing established

| Earlier work | Useful evidence | Limitation for this decision |
|---|---|---|
| June schema audit and extraction pilot | Real source examples informed locators, sample/design fields and domain details; a pilot validated 298 outputs | Formatting and field fit do not establish complete, correctly attributed graph evidence. |
| July review prompt and schema tests | On the original 50 papers, source-assessor ratings improved from 35 to 40, then 42 good representations. A fresh 50 exposed weaker generalization, at 33 good. | Development and fresh-set results must remain separate. |
| July simplified review contract | Removing linked outline structures and adding evidence labels reduced the second cohort from 33 to 26 good representations | Simplification and an explicit evidence-status field have already been tried together and regressed. Repeating that combined redesign is not a new solution. |
| July context-first one-pass reviews | 77/100 good versus 75/100 previously; 100 rather than 158 calls; 24.6% fewer tokens | Eleven papers improved and nine regressed. Broader main-graph selection was an explicitly accepted tradeoff. |
| July meta-analysis normalization | Revising normalization increased represented papers from 215 to 241 and main-graph findings from 626 to 813 using existing extractions | Demonstrates that downstream repairs can recover useful evidence without another model extraction. |
| October matched model comparison | Source-assessor ratings favored Luna: primary 6/8, reviews 19/20, meta-analyses 16/20 adequate | Small, partly challenge-selected samples, one assistant assessor, no independent human gold and no repeated-run measurement. These are not corpus-wide accuracy estimates. |

Sources: [model comparison](gemini_luna_head_to_head_2026-10-16.md), [review controlled comparison](review_relationships_v2_old50_prompt_final_comparison.md), [simplified-contract test](review_relationships_v2_validation50_direct_contract_results.md), [one-pass comparison](review_relationships_v2_context_first_onepass_100_results.md), [meta-analysis normalization assessment](meta_analysis_v2_complete_normalization_assessment.md).

## New offline replay

I replayed **120 saved Luna outputs: 40 primary, 40 review and 40 meta-analysis tasks**, each family containing 20 article-text and 20 abstract inputs. Every saved assembled instruction exactly matches its currently active counterpart. The replay used the current converters and normalizer in an isolated evaluation directory, with the frozen benchmark task identities and source text.

The replay keeps the historical benchmark cohort fixed rather than applying the new production screening exclusions. It diagnoses the old cases; the fresh samples below are selected from the new production task lists.

| Stage | Primary | Review | Meta-analysis |
|---|---:|---:|---:|
| Tasks | 40 | 40 | 40 |
| Items in schema-valid outputs | 91 | 236 | 228 |
| Items accepted by conversion | 91 | 236 | 218 |
| Accepted input items producing any normalized finding | 78 | 126 | 195 |
| Accepted input items producing a main-graph finding | 61 | 88 | 135 |

These are **pipeline coverage counts, not correctness scores**. Some details appropriately stay outside the graph. One input item may expand into multiple normalized findings; the last two rows count distinct original items, avoiding inflation from that expansion. The existing review-specific projection also retains anchors and relationships that the canonical graph projection cannot normalize. A graph omission does not necessarily mean the source information was deleted from the saved bundle.

Four primary tasks returned no scoped finding; their correctness needs source review. One older meta-analysis response failed its schema, excluding five emitted results. That earlier comparison used JSON/schema guidance for meta-analyses; the migrated production path now uses strict native structured output, so this old formatting failure is not a measured failure rate for the new transport.

Current checks flag **0/40 primary, 3/40 review and 12/40 meta-analysis tasks**. A clean automatic check is not a source-correctness judgment. In particular, the primary checks cannot establish correct denominators or completeness merely because all 40 pass.

The historical active release has **25,314 normalization audit rows**, including 12,249 `entity_unmapped` rows and 757 `compound_unmapped` rows. These are historical outputs and policy exclusions, not Luna error counts. They provide a useful challenge pool, with source inspection required before labeling any row a defect.

## Concrete problems and their likely remedies

| Source case | Observation in this investigation | Interpretation and next test |
|---|---|---|
| Psilocybin depression synthesis, DOI `10.1177/02698811241287542` | Luna preserves one SMC of −1.24 with its interval, alongside two reported multilevel I² percentages. Both current multiple-estimate checkers flag the result because the statement has more than one percentage; conversion holds it. | **Confirmed checker false positive.** Heterogeneity components are not extra treatment estimates. Test a checker repair against this case and genuine multi-comparison cases. |
| Ketamine comparator synthesis, DOI `10.1038/s41386-019-0317-8` | The supplied text reports d=0.7 versus midazolam and d=1.8 versus saline. Luna copies both correctly but packs them and both intervals into one estimate object. Another item packs several response rates and contrasts. | **Real structural violation.** The prompt already asks for separate results. Test an explicit analysis record for each comparison/outcome/timepoint, with source wording preserved. Merely repeating the existing instruction may not be enough. |
| Suicidality synthesis abstract, DOI `10.4088/jcp.21r14057` | The abstract gives an SMD range across timepoints. Luna faithfully preserves that range and states that individual timepoint estimates are unavailable. The atomic-estimate converter holds it. | **Source/representation limitation, not fabricated evidence.** Test a summary-only result type or a summary with no scalar estimate. Preserve the range without inventing timepoint assignments. |
| Bayesian network synthesis, DOI `10.1136/bmj-2023-078607` | Source-present estimates and intervals are extracted, but two network-comparison results leave the network-comparison structure empty. Conversion holds them. | **Missing required semantic structure despite valid JSON.** Test explicit treatment/reference fields and conditional validation. Keep reference-trial context attached to each estimate. |
| MDMA pharmacology review abstract, DOI `10.1002/jcph.266` | Luna preserves named harms and cortisol/oxytocin/antidiuretic-hormone release, including several entities in a single anchor. The canonical replay yields two normalized findings, for serotonin syndrome and methamphetamine-like effects; the additional hormone entities are retained in the raw relationship but do not become their own normalized findings. | **Extraction-to-projection mismatch.** Test entity-level anchors and coverage of all supported objects. An isolated projection that preserves all anchors does not prove equivalent query coverage in the canonical graph. |
| Ketamine memory study abstract, DOI `10.1016/j.neuron.2024.06.026` | Luna captures both BLA findings and a VTA-to-BLA dopaminergic projection. BLA normalizes; the circuit label remains unmapped. | **Normalization/ontology candidate.** Test circuit identity and parent relationships; avoid converting a circuit into an interchangeable alias of either endpoint region. |

These are assistant source inspections and deterministic reproductions. They are diagnostic examples, not a fresh independently adjudicated accuracy sample.

Two further risks deserve targeted tests:

- Primary item schemas use free-text sample sizes and statistics, and do not contain verbatim excerpt fields. They preserve readable results, but make automatic checking of subgroup denominators, timepoints and numerical attribution difficult. Test a compact source-evidence field and explicit analysis context before adding many new fields everywhere.
- Luna selects **232/236 review relationships for the main graph** in the saved sample. This continues the previously accepted broader-selection tradeoff. Evaluate the importance of qualifications and background separately; a larger main graph is not itself better or worse.

A synthetic checker test also confirms that a result meeting a stated alpha of 0.10 is still flagged when p=0.06, because the helper hard-codes 0.05. That is a checker-consistency issue, not a measured Luna error. Transformation-aware null values and reported analysis criteria belong in the validator test set.

## Evaluation strategy

### 1. Define the evidence we need to preserve

Start with researcher questions the graph must answer: which compound or complete intervention package is related to which outcome, target, circuit or context; in what population/system and time window; under which comparison; with what result and evidence status; and where the source supports it.

Keep raw scientific wording alongside normalized identities. Measure specific entities and their broader parents separately. An unmapped label is safer than a confident but incorrect merge. Review summaries, hypotheses, recommendations and empirical findings need distinct interpretation even when they share anchors.

### 2. Establish source references before candidate outputs

For each evaluation paper, read the exact supplied source and create a reference inventory of its central eligible findings, required qualifications and meaningful distinctions. Record source spans, eligible domain, compound/package, object, comparator, subgroup/denominator, timepoint, result and evidence status where reported. Record genuine ambiguity and information absent from the supplied source.

Use previous model outputs only to find diagnostic cases. Neither historical Gemini outputs, new Luna outputs nor the existing normalizer can define correctness. For the new samples, create and freeze source references before examining new predictions. The current assistant can provide source-adjudicated references, labeled as such; independent domain review of a calibration subset would strengthen any performance claim. File names containing “manual gold” do not establish human provenance.

Grade candidate outputs with masked version names and randomized order. Resolve substantive disagreements by returning to the source. Record residual ambiguity rather than forcing a convenient correct/incorrect label. Preserve every relationship's evidence strength, especially hypothetical, weak, observational, null and contradictory findings.

### 3. Keep three datasets separate

| Dataset | Purpose | Current preparation |
|---|---|---|
| Existing diagnostic cases | Understand failure mechanisms and prevent regressions | 120 saved Luna task outputs replayed; earlier source assessments retained separately |
| Fresh development | Develop narrowly justified candidates across families, domains and source depths | **96 new papers, 144 tasks**: 48 primary, 20 reviews, 20 meta-analyses, 8 guidelines |
| Fresh held-out validation | Test whether the selected improvement generalizes | **96 different papers, 160 tasks**, same family counts; predictions not run and references not yet annotated |

The new samples exclude the prior 120 extraction-case DOIs and the two earlier review-development cohorts. Membership and task JSON are saved; exact source bytes and requests must be frozen when the reference-annotation phase begins. All selected routes for a primary paper stay together. Reconcile DOI aliases and report/study relationships before the live test so related reports cannot leak across splits.

These are intentionally stratified samples. Report family/domain/depth results separately; their unweighted pooled score is not corpus-wide accuracy. Add an appropriately weighted or simple-random paper sample if a corpus-level estimate is required. Known challenge-case scores remain separate. Once a holdout has influenced a revision, use a new holdout for that revision.

### 4. Measure the full path and attribute each failure

| Measure | What gets checked |
|---|---|
| Source-supported precision | Every asserted finding is supported, with the right relationship and qualifications |
| Central-finding coverage | Reference central findings and conclusion-changing qualifications are captured; equivalent wording is allowed |
| Attribution | Compound/package, population, analyzed denominator, comparator, outcome and timepoint are correctly linked |
| Quantitative fidelity | Sign, value, metric, unit, interval, scale and analysis role match the source; no guessed assignments |
| Normalization fidelity | Correct identities, aliases, subtypes and parents; no false mergers, invented relationships or lost combination context |
| End-to-end coverage | Correct, graph-eligible reference propositions remain retrievable after conversion, normalization and graph admission |
| Operational performance | Valid output, refusals/truncation, token cost, calls per paper, latency and repeatability |

Give each failure an origin: source availability/identity, task routing, extraction wording, schema capacity, conversion, normalization vocabulary/rules, or graph-admission policy. Keep unsupported numerical attribution, causal overstatement and false entity merges prominent rather than hiding them inside a favorable average. Score per paper as well as per finding, so prolific papers and verbose outputs cannot dominate.

Repeat a small fixed subset, approximately 20 tasks, with the unchanged baseline to estimate stochastic variability. Compare candidates on the same papers and sources. Report paired improvements and regressions, uncertainty clustered by paper, and both quality and cost. Automated judges need calibration against source-adjudicated cases; agreement alone is insufficient. This follows the task-specific and stage-specific approach in the [official OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

### 5. Compare controlled candidates

| Candidate | What changes | What the comparison would establish |
|---|---|---|
| A: current baseline | Current prompts, schemas, Luna settings and current normalization | Fresh baseline under the migrated strict-output transport |
| B: instruction changes | Same schemas and downstream code; revise only demonstrated ambiguity or omissions | Whether clarification alone solves the problem |
| C: targeted contract changes | Explicit analysis identity, properly separated estimates/summary-only results, source evidence and entity anchors where needed | Whether missing structure, rather than wording, is the bottleneck |
| D: primary paper-centered experiment | Read one multi-domain primary paper once, return shared study context and typed domain findings | Whether reducing repeated calls improves whole-paper coverage and cost without creating attention or output-size failures |

Start with A versus B. Test C for failures the schema cannot reliably express or validate. Test D on multi-domain papers if the diagnosis supports it; retain separate primary/review/synthesis/recommendation semantics. Avoid changing prompts, schemas and normalization simultaneously without a component comparison.

For downstream repairs, cross the saved outputs with old and repaired conversion/normalization. That comparison requires no new extraction calls and isolates the gain from the repair. Include negative controls so admitting a valid result does not also admit combined estimates or false aliases.

## How to decide the size of the change

| Observed pattern | Appropriate action |
|---|---|
| The source fact fits the schema, but an instruction is unclear or a local omission recurs | Focused prompt revision |
| The model cannot express a meaningful comparison, package, range or entity without packing unrelated values together | Targeted schema revision |
| The saved extraction is faithful but conversion or normalization changes or drops its meaning | Repair that downstream stage; reuse the saved extraction |
| Several domains repeatedly omit or duplicate central findings because each call sees only its assigned scope, and a paper-centered candidate fixes this on fresh papers | Reconsider primary extraction architecture |
| The supplied source lacks the required evidence | Improve source access or retain an explicit limitation; prompt changes cannot supply missing evidence |

Use improvement in paired source-based results and a fresh holdout to choose a candidate. Require no newly observed critical attribution or false-merge errors and examine uncertainty before treating small gains as real. Proposed operating targets, such as 98% supported-claim precision or 90% central-finding coverage, should be agreed as project goals, not presented as measured performance or externally validated standards. A zero-error small sample does not prove a zero error rate.

**Recommended next paid step:** a bounded Luna pilot on the fresh development set with frozen source references and a small repeatability subset, starting with a $5 evaluation cap within the existing $100 allocation. The full production extraction rerun should follow selection of the tested contract. The first downstream correction to assess is the confirmed heterogeneity false positive; the first schema experiment should address distinct estimates and summary-only quantitative evidence.

## Reproducible audit artifacts

The [audit directory](../../data/processed/evaluation/extraction_design_audit_20261017/) contains the read-only diagnostic replay, contract hashes, per-case flags, conversion reports, isolated normalized tables, input-item trace counts, historical normalization examples, source-inspection judgments and both fresh sample manifests. `summary.json` records that the new samples are unannotated and model tests have not run. These artifacts extend the existing evaluation workflow and do not serve as production inputs.
